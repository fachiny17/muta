"""Web channel + team login + validation dashboard."""
import hmac
import json
import os
import sqlite3
import tempfile
import time

from flask import (Blueprint, Response, abort, current_app, jsonify, make_response, redirect,
                   render_template, request, send_file, session, url_for)

from app import db, natlas_client, pipeline
from app.config import BASE_DIR

EVIDENCE_DIR = BASE_DIR / "evidence"

bp = Blueprint("web", __name__)

SUFFIX = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3",
          "audio/wav": ".wav", "audio/x-wav": ".wav"}

_login_attempts = {}          # ip -> list of failed-attempt timestamps (in memory is enough for a small app)
MAX_ATTEMPTS, WINDOW_S = 5, 15 * 60


# ---------- helpers ----------
def _user_id() -> tuple:
    uid = request.cookies.get("cv_uid")
    if db.valid_user_id(uid):
        return uid, False
    return db.new_user_id(), True


def _with_cookie(resp, uid: str, is_new: bool):
    if is_new:
        resp.set_cookie("cv_uid", uid, max_age=365 * 24 * 3600, httponly=True, samesite="Lax", secure=request.is_secure)
    return resp


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def _is_admin() -> bool:
    """True when this browser has logged in through /login."""
    return session.get("admin") is True


def _dashboard_allowed() -> bool:
    key = current_app.config["DASHBOARD_KEY"]
    if _is_admin() or not key:
        return True
    supplied = request.args.get("key") or request.headers.get("x-dashboard-key") or ""
    return _same(supplied, key)


def _admin_allowed() -> bool:
    """Admin powers: a logged-in team member, or a script sending the x-admin-key header."""
    if _is_admin():
        return True
    key = current_app.config["ADMIN_KEY"]
    return bool(key) and _same(request.headers.get("x-admin-key", ""), key)


def _load_snapshot():
    """The frozen pilot results written by scripts/publish_evidence.py (None until you publish them)."""
    p = EVIDENCE_DIR / "snapshot.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _too_many_attempts(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _login_attempts.get(ip, []) if now - t < WINDOW_S]
    _login_attempts[ip] = recent
    return len(recent) >= MAX_ATTEMPTS


# ---------- public pages ----------
@bp.get("/")
def index():
    return render_template("index.html", langs=current_app.config["LANG_OPTIONS"],
                           demo_url=current_app.config["DEMO_VIDEO_URL"],
                           is_admin=_is_admin(),
                           has_evidence=_load_snapshot() is not None)


@bp.get("/healthz")
def healthz():
    """Cheap liveness check for the hosting platform (does not call the GPU gateway)."""
    return jsonify(ok=True, whatsapp=current_app.config["WHATSAPP_ENABLED"])


@bp.get("/health")
def health():
    out = {"app": "ok", "gateway": None}
    try:
        g = natlas_client.health()
        out["gateway"] = {"ok": True, "detail": g}
    except Exception as e:
        out["gateway"] = {"ok": False, "error": str(e)[:200]}
    return jsonify(out)


@bp.get("/evidence")
def evidence():
    """Public, read-only pilot results, drawn from the frozen snapshot committed to the repo (no live database needed)."""
    return render_template("evidence.html", snap=_load_snapshot(), langs=current_app.config["LANG_OPTIONS"],
                           has_csv=(EVIDENCE_DIR / "validation.csv").exists(), is_admin=_is_admin())


@bp.get("/evidence/validation.csv")
def evidence_csv():
    p = EVIDENCE_DIR / "validation.csv"
    if not p.exists():
        abort(404)
    return send_file(str(p), mimetype="text/csv", as_attachment=True, download_name="muta_validation.csv")


# ---------- team login ----------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if _is_admin():
        return redirect(url_for("web.dashboard"))
    error, status = None, 200
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if _too_many_attempts(ip):
            error, status = "Too many attempts. Please wait 15 minutes and try again.", 429
        elif _same(request.form.get("password", ""), current_app.config["DASHBOARD_KEY"]) and current_app.config["DASHBOARD_KEY"]:
            session.clear()
            session["admin"] = True
            session.permanent = True
            return redirect(url_for("web.dashboard"))
        else:
            _login_attempts.setdefault(ip, []).append(time.time())
            error, status = "Incorrect password.", 401
    return render_template("login.html", error=error), status


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.index"))


# ---------- student API ----------
@bp.post("/api/ask")
def ask():
    if request.form.get("consent") != "1":
        return jsonify(ok=False, message="Please accept the privacy notice first."), 400
    lang = request.form.get("language", "")
    if lang not in current_app.config["LANG_OPTIONS"]:
        return jsonify(ok=False, message="Unsupported language."), 400
    f = request.files.get("audio")
    if not f:
        return jsonify(ok=False, message="No audio received."), 400

    mode = request.form.get("mode", "question")
    if mode not in ("question", "summary"):
        return jsonify(ok=False, message="Unknown mode."), 400
    uid, is_new = _user_id()
    db.ensure_user(uid, "web", consent=True, language=lang)
    if db.count_recent(uid) >= current_app.config["RATE_LIMIT_PER_HOUR"]:
        return jsonify(ok=False, message="You have reached the hourly limit. Please try again later."), 429
    suffix = SUFFIX.get((f.mimetype or "").split(";")[0], ".bin")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        f.save(tmp.name)
        size = os.path.getsize(tmp.name)
        result = pipeline.handle_voice(tmp.name, lang, uid, "web", audio_bytes=size, mode=mode)
    finally:
        tmp.close()
        if os.path.exists(tmp.name):
            os.remove(tmp.name)  # raw audio is never kept
    return _with_cookie(make_response(jsonify(result)), uid, is_new)


@bp.post("/api/feedback")
def feedback():
    data = request.get_json(silent=True) or {}
    uid = request.cookies.get("cv_uid")
    if not db.valid_user_id(uid):
        return jsonify(ok=False, message="Unknown user."), 403
    rating = data.get("rating")
    task = data.get("task_completed")
    try:
        rating = int(rating) if rating is not None else None
        if task is not None and not isinstance(task, bool):
            raise ValueError
        if rating is None and task is None:
            raise ValueError
        done = pipeline.record_feedback(int(data["interaction_id"]), uid, rating, task)
    except (ValueError, KeyError, TypeError):
        return jsonify(ok=False, message="Invalid feedback."), 400
    if not done:
        return jsonify(ok=False, message="Interaction not found."), 404
    return jsonify(ok=True)


# ---------- team-only: dashboard, exports, admin ----------
@bp.get("/dashboard")
def dashboard():
    if not _dashboard_allowed():
        return redirect(url_for("web.login"))
    live, snap = db.stats(), _load_snapshot()
    return render_template("dashboard.html", s=live, snap=snap, in_sync=bool(snap) and snap.get("stats") == live,
                           langs=current_app.config["LANG_OPTIONS"], key=request.args.get("key", ""), is_admin=_is_admin())


@bp.get("/api/stats")
def api_stats():
    if not _dashboard_allowed():
        abort(403)
    return jsonify(db.stats())


@bp.get("/export.csv")
def export_csv():
    if not _dashboard_allowed():
        abort(403)
    include_text = request.args.get("include_text") == "1"
    if include_text and not _admin_allowed():      # question/answer text is team-only
        abort(403)
    body = db.export_csv(include_text=include_text)
    return Response(body, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=muta_validation.csv"})


@bp.get("/admin/backup.sqlite")
def backup():
    if not _admin_allowed():
        abort(404)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
    tmp.close()
    src, dst = sqlite3.connect(current_app.config["DB_PATH"]), sqlite3.connect(tmp.name)
    with dst:
        src.backup(dst)
    src.close(); dst.close()
    resp = send_file(tmp.name, as_attachment=True, download_name="muta-backup.sqlite")
    resp.call_on_close(lambda: os.path.exists(tmp.name) and os.remove(tmp.name))
    return resp


@bp.post("/internal/gateway")
def register_gateway():
    """The GPU notebook calls this (heartbeat) so the app always knows the current tunnel URL."""
    if not _admin_allowed():
        abort(404)
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip().rstrip("/")
    if not url.startswith("https://") or len(url) > 200:
        return jsonify(ok=False, message="url must be an https URL"), 400
    natlas_client.configure(url, current_app.config["GATEWAY_KEY"])
    db.set_setting("gateway_url", url)
    return jsonify(ok=True)