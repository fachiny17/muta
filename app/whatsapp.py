"""OPTIONAL WhatsApp channel (Twilio). Nothing else imports this module unless
WHATSAPP_ENABLED=1, so the web app never depends on Twilio.

Flow: student voice note -> Twilio webhook (this file) -> shared pipeline -> reply via Twilio REST API.
Twilio's webhook times out quickly and N-ATLAS can take several seconds, so the webhook returns an empty
response at once and the real reply is sent afterwards from a background thread.
Conversation state lives in SQLite (language, last answered interaction), not in memory.
"""
import base64
import hashlib
import hmac
import logging
import os
import tempfile
import threading

import httpx
from flask import Blueprint, Response, current_app, request

from app import db, pipeline

log = logging.getLogger("classvoice.whatsapp")
bp = Blueprint("whatsapp", __name__)

RUN_ASYNC = True                      # tests set this to False to run inline
_slots = threading.Semaphore(2)       # at most 2 voice notes processed at once on this server
MAX_MEDIA_BYTES = 5 * 1024 * 1024
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


# ---------- messages ----------
def _menu(cfg) -> dict:
    return {str(i + 1): code for i, code in enumerate(cfg["LANG_OPTIONS"])}


def welcome_text(cfg) -> str:
    lines = "\n".join(f"{n} {cfg['LANG_OPTIONS'][c]}" for n, c in _menu(cfg).items())
    return ("Welcome to ClassVoice NG, a voice study assistant (an AI, not a human teacher). "
            "We store only an anonymous ID, your language, your question text and your ratings, "
            "never your name or phone number. Choosing a language means you agree.\n"
            f"Reply with a number:\n{lines}")


HELP = ("Send a voice note with ONE academic question and I will answer in your language.\n"
        "After an answer, reply 1-5 to rate it (5 = very useful), then YES or NO if it helped.\n"
        "Send 'language' to change language.")


# ---------- Twilio helpers ----------
def valid_signature(url: str, params: dict, signature: str, token: str) -> bool:
    """Twilio request signature check (HMAC-SHA1 over URL + sorted params)."""
    data = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature or "")


def send_message(cfg: dict, to: str, body: str) -> None:
    sid, tok = cfg["TWILIO_ACCOUNT_SID"], cfg["TWILIO_AUTH_TOKEN"]
    if not (sid and tok and cfg["TWILIO_WHATSAPP_FROM"]):
        raise RuntimeError("Twilio credentials are not configured")
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, tok),
                   data={"From": cfg["TWILIO_WHATSAPP_FROM"], "To": to, "Body": body[:1500]}, timeout=30)
    r.raise_for_status()


def _safe_send(cfg, to, body):
    try:
        send_message(cfg, to, body)
    except Exception:
        log.exception("failed to send WhatsApp message")


def _spawn(fn, *args):
    if RUN_ASYNC:
        threading.Thread(target=fn, args=args, daemon=True).start()
    else:
        fn(*args)


# ---------- background work ----------
def _process_voice(cfg: dict, to: str, uid: str, lang: str, media_url: str) -> None:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
    try:
        r = httpx.get(media_url, auth=(cfg["TWILIO_ACCOUNT_SID"], cfg["TWILIO_AUTH_TOKEN"]),
                      follow_redirects=True, timeout=30)
        r.raise_for_status()
        if len(r.content) > MAX_MEDIA_BYTES:
            _safe_send(cfg, to, pipeline.MSG_TOO_LONG.format(s=cfg["MAX_AUDIO_S"]))
            return
        tmp.write(r.content)
        tmp.close()
        with _slots:
            res = pipeline.handle_voice(tmp.name, lang, uid, "whatsapp", audio_bytes=len(r.content))
    except Exception:
        log.exception("whatsapp media handling failed")
        _safe_send(cfg, to, pipeline.MSG_AUDIO)
        return
    finally:
        tmp.close()
        if os.path.exists(tmp.name):
            os.remove(tmp.name)          # raw audio is never kept
    if res["ok"]:
        _safe_send(cfg, to, f"{res['answer']}\n\nRate this answer 1-5 (5 = very useful).")
    else:
        _safe_send(cfg, to, res["message"])


# ---------- webhook ----------
@bp.post("/whatsapp/webhook")
def webhook():
    cfg = current_app.config
    params = request.form.to_dict()
    token, base = cfg["TWILIO_AUTH_TOKEN"], cfg["PUBLIC_BASE_URL"]
    if cfg["WHATSAPP_VERIFY_SIGNATURE"]:
        if not (token and base):
            log.error("signature check is on but TWILIO_AUTH_TOKEN / PUBLIC_BASE_URL are not set")
            return Response("webhook not configured", status=503)
        if not valid_signature(base + "/whatsapp/webhook", params, request.headers.get("X-Twilio-Signature", ""), token):
            log.warning("invalid Twilio signature (is PUBLIC_BASE_URL exactly the URL set in Twilio?)")
            return Response("invalid signature", status=403)

    ok_resp = Response(EMPTY_TWIML, mimetype="text/xml")
    if not db.mark_seen(params.get("MessageSid", "")):      # provider retry: already handled
        return ok_resp

    sender = params.get("From", "")
    body = (params.get("Body") or "").strip().lower()
    uid = db.user_id_from_phone(sender, cfg["SECRET_KEY"])
    db.ensure_user(uid, "whatsapp")
    user = db.get_user(uid)
    conf = dict(cfg)                                          # plain dict for background threads
    menu = _menu(cfg)

    def reply(text):
        _spawn(_safe_send, conf, sender, text)

    # 1) language not chosen yet (or user asked to change it)
    if not user["language"] or body == "language":
        if user["language"] and body == "language":
            db.ensure_user(uid, "whatsapp", language="")      # clear it, show menu
            reply(welcome_text(cfg))
        elif body in menu:
            lang = menu[body]
            db.ensure_user(uid, "whatsapp", consent=True, language=lang)
            reply(f"Language set to {cfg['LANG_OPTIONS'][lang]}. Send a voice note with your academic question.")
        else:
            reply(welcome_text(cfg))
        return ok_resp

    if body in ("help", "?"):
        reply(HELP)
        return ok_resp

    # 2) voice note -> shared pipeline
    is_audio = int(params.get("NumMedia", "0") or 0) > 0 and params.get("MediaContentType0", "").startswith("audio")
    if is_audio:
        if db.count_recent(uid) >= cfg["RATE_LIMIT_PER_HOUR"]:
            reply("You have reached the hourly limit. Please try again later.")
            return ok_resp
        if cfg["WHATSAPP_ACK"]:
            reply("Got it, working on your answer...")
        _spawn(_process_voice, conf, sender, uid, user["language"], params["MediaUrl0"])
        return ok_resp

    # 3) feedback replies
    last = db.last_answered(uid)
    if body in {"1", "2", "3", "4", "5"} and last is not None and last["rating"] is None:
        db.record_feedback(last["id"], uid, rating=int(body))
        reply("Thank you! Did this help you finish your task? Reply YES or NO.")
    elif body in {"yes", "no"} and last is not None and last["task_completed"] is None:
        db.record_feedback(last["id"], uid, task_completed=(body == "yes"))
        reply("Thank you for your feedback. Send another voice note any time.")
    else:
        reply(HELP)
    return ok_resp
