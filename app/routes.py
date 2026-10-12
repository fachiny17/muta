"""Web channel + team login + validation dashboard."""
import hmac
import json
import os
import sqlite3
import tempfile
import time

from flask import (Blueprint, Response, abort, current_app, jsonify, make_response, redirect,
                   render_template, request, send_file, session, url_for)

from app import db, natlas_client, pipeline,course_memory, audio
from app.config import BASE_DIR

from app.natlas_client import GatewayError
from werkzeug.utils import secure_filename

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

    live = db.stats()
    cm = course_memory.stats()
    snap = _load_snapshot()

    return render_template(
        "dashboard.html",
        s=live,
        cm=cm,
        snap=snap,
        in_sync=bool(snap) and snap.get("stats") == live,
        langs=current_app.config["LANG_OPTIONS"],
        key=request.args.get("key", ""),
        is_admin=_is_admin(),
    )

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

# ---------- Course Memory and SpeakBack ----------

def _course_owner():
    """Return this browser's existing anonymous ID, if available."""
    uid = request.cookies.get("cv_uid")
    return uid if db.valid_user_id(uid) else None


def _course_not_found():
    return jsonify(ok=False, message="Course not found."), 404


@bp.get("/courses")
def courses_page():
    uid, is_new = _user_id()

    response = make_response(render_template(
        "courses.html",
        langs=current_app.config["LANG_OPTIONS"],
        is_admin=_is_admin(),
    ))
    return _with_cookie(response, uid, is_new)


@bp.get("/api/courses")
def list_student_courses():
    uid, is_new = _user_id()

    response = make_response(jsonify(
        ok=True,
        courses=course_memory.list_courses(uid),
    ))
    return _with_cookie(response, uid, is_new)


@bp.post("/api/courses")
def create_student_course():
    uid = _course_owner()
    if not uid:
        return jsonify(ok=False, message="Reload the Course Memory page and try again."), 403

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    language = str(data.get("language", "")).strip()

    if not name or len(name) > 80:
        return jsonify(ok=False, message="Enter a course name of 1 to 80 characters."), 400

    if language not in current_app.config["LANG_OPTIONS"]:
        return jsonify(ok=False, message="Choose a supported language."), 400

    course = course_memory.create_course(uid, name, language)
    
    course_memory.record_event(
        uid, course["id"], "course_created", language=language
    )
    
    return jsonify(ok=True, course=course)


@bp.post("/api/courses/<int:course_id>/documents")
def upload_course_document(course_id):
    uid = _course_owner()
    if not uid:
        return jsonify(ok=False, message="Reload the Course Memory page and try again."), 403

    if not course_memory.get_course(uid, course_id):
        return _course_not_found()

    uploaded = request.files.get("document")
    if not uploaded or not uploaded.filename:
        return jsonify(ok=False, message="Choose a PDF or TXT file first."), 400

    filename = secure_filename(uploaded.filename)
    try:
        text = course_memory.extract_document(filename, uploaded.stream)
    except ValueError as exc:
        return jsonify(ok=False, message=str(exc)), 400
    except Exception:
        current_app.logger.exception("Could not extract course document")
        return jsonify(
            ok=False,
            message="Could not read this file. Check that it is a valid PDF or TXT file.",
        ), 400

    saved = course_memory.add_document(uid, course_id, filename, text)
    if not saved:
        return _course_not_found()

    course_memory.record_event(
        uid, course_id, "document_uploaded",
        language=course_memory.get_course(uid, course_id)["language"],
    )

    return jsonify(ok=True, message="Notes uploaded and saved.", filename=filename)

@bp.get("/api/courses/<int:course_id>/documents")
def list_course_documents(course_id):
    uid = _course_owner()
    if not uid:
        return jsonify(ok=False, message="Reload the page and try again."), 403

    documents = course_memory.list_documents(uid, course_id)
    if documents is None:
        return _course_not_found()

    return jsonify(ok=True, documents=documents)


@bp.delete("/api/courses/<int:course_id>/documents/<int:document_id>")
def delete_course_document(course_id, document_id):
    uid = _course_owner()
    if not uid:
        return jsonify(ok=False, message="Reload the page and try again."), 403

    course = course_memory.get_course(uid, course_id)
    if not course:
        return _course_not_found()

    deleted = course_memory.delete_document(uid, course_id, document_id)
    if not deleted:
        return jsonify(ok=False, message="Document not found."), 404

    course_memory.record_event(
        uid, course_id, "document_deleted", language=course["language"]
    )

    return jsonify(ok=True, message="Document deleted.")


@bp.delete("/api/courses/<int:course_id>")
def delete_student_course(course_id):
    uid = _course_owner()
    if not uid:
        return jsonify(ok=False, message="Reload the page and try again."), 403

    course = course_memory.get_course(uid, course_id)
    if not course:
        return _course_not_found()

    deleted = course_memory.delete_course(uid, course_id)
    if not deleted:
        return _course_not_found()

    course_memory.record_event(
        uid, course_id, "course_deleted", language=course["language"]
    )

    return jsonify(ok=True, message="Course and its notes deleted.")

@bp.post("/api/courses/<int:course_id>/ask")
def ask_course_question(course_id):
    uid = _course_owner()
    if not uid:
        return jsonify(ok=False, message="Reload the Course Memory page and try again."), 403

    course = course_memory.get_course(uid, course_id)
    if not course:
        return _course_not_found()

    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()

    if not question or len(question) > 1500:
        return jsonify(
            ok=False,
            message="Enter a question of 1 to 1,500 characters.",
        ), 400

    context = course_memory.get_context(uid, course_id, question)
    if not context:
        return jsonify(
            ok=False,
            message="Upload course notes before asking questions.",
        ), 400

    language_name = current_app.config["LANG_OPTIONS"][course["language"]]

    messages = [
        {
            "role": "system",
            "content": (
                "You are Muta Course Memory, an academic assistant for Nigerian students. "
                f"Reply only in {language_name}. Answer using only the supplied course notes. "
                "If the notes do not contain enough information, say so clearly. "
                "Do not invent facts or pretend that information came from the notes. "
                "Explain clearly in under 180 words."
            ),
        },
        {
            "role": "user",
            "content": (
                f"COURSE NOTES:\n{context}\n\n"
                f"STUDENT QUESTION:\n{question}"
            ),
        },
    ]

    started = time.perf_counter()

    try:
        answer = natlas_client.chat(
            messages,
            max_tokens=350,
            temperature=0.2,
        ).strip()
    except GatewayError:
        current_app.logger.exception("Course Memory request to N-ATLAS failed")
        course_memory.record_event(
            uid, course_id, "course_question",
            success=False,
            duration_ms=round((time.perf_counter() - started) * 1000),
            language=course["language"],
        )
        return jsonify(
            ok=False,
            message="N-ATLAS is not responding. Check that the model gateway is running.",
        ), 502

    if not answer:
        return jsonify(ok=False, message="Muta could not generate an answer. Try again."), 502

    course_memory.record_event(
        uid, course_id, "course_question",
        success=True,
        duration_ms=round((time.perf_counter() - started) * 1000),
        language=course["language"],
    )

    return jsonify(ok=True, answer=answer)


@bp.post("/api/courses/<int:course_id>/speakback/question")
def create_speakback_question(course_id):
    uid = _course_owner()
    if not uid:
        return jsonify(ok=False, message="Reload the Course Memory page and try again."), 403

    course = course_memory.get_course(uid, course_id)
    if not course:
        return _course_not_found()

    context = course_memory.get_context(uid, course_id, "", max_chars=5000)
    if not context:
        return jsonify(
            ok=False,
            message="Upload course notes before starting SpeakBack.",
        ), 400

    language_name = current_app.config["LANG_OPTIONS"][course["language"]]

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a tutor testing a Nigerian student in {language_name}. "
                "Use only the supplied course notes. Generate exactly ONE clear, "
                "open-ended question that tests understanding. Do not answer it. "
                "Do not add an introduction, a numbered list, or a marking guide."
            ),
        },
        {
            "role": "user",
            "content": f"COURSE NOTES:\n{context}\n\nWrite one oral revision question.",
        },
    ]

    started = time.perf_counter()
    
    try:
        question = natlas_client.chat(
            messages,
            max_tokens=100,
            temperature=0.2,
        ).strip()
    except GatewayError:
        current_app.logger.exception("SpeakBack question generation failed")
        course_memory.record_event(
            uid, course_id, "speakback_question",
            success=False,
            duration_ms=round((time.perf_counter() - started) * 1000),
            language=course["language"],
        )
        return jsonify(
            ok=False,
            message="N-ATLAS is not responding. Check the model gateway.",
        ), 502

    if not question:
        return jsonify(ok=False, message="Could not create a question. Try again."), 502

    quiz_id = course_memory.save_quiz(
        uid,
        course_id,
        question,
        context,
    )

    course_memory.record_event(
        uid, course_id, "speakback_question",
        success=True,
        duration_ms=round((time.perf_counter() - started) * 1000),
        language=course["language"],
    )

    return jsonify(ok=True, quiz_id=quiz_id, question=question)


@bp.post("/api/courses/<int:course_id>/speakback/answer")
def submit_speakback_answer(course_id):
    uid = _course_owner()
    if not uid:
        return jsonify(ok=False, message="Reload the Course Memory page and try again."), 403

    course = course_memory.get_course(uid, course_id)
    if not course:
        return _course_not_found()

    quiz_id = request.form.get("quiz_id", "").strip()
    quiz = course_memory.get_quiz(uid, course_id, quiz_id)

    if not quiz:
        current_app.logger.warning(
            "SpeakBack lookup failed: quiz_id_present=%s, "
            "course_id=%s",
            bool(quiz_id),
            course_id,
        )
    
        return jsonify(
            ok=False,
            message="Question not found. Generate a new SpeakBack question.",
        ), 404
        
    started = time.perf_counter()
    
    uploaded = request.files.get("audio")
    if not uploaded:
        return jsonify(ok=False, message="No recording was received."), 400

    mime = (uploaded.mimetype or "").split(";")[0]
    suffix = SUFFIX.get(mime, ".webm")

    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temporary_path = temporary.name
    temporary.close()

    try:
        uploaded.save(temporary_path)

        # Reuse Muta's existing audio conversion and N-ATLAS transcription.
        transcript = pipeline.transcribe(
            temporary_path,
            course["language"],
            max_s=current_app.config["MAX_AUDIO_S"],
        ).text.strip()

        if not transcript:
            return jsonify(
                ok=False,
                message="Muta could not hear a clear answer. Please record again.",
            ), 400

        language_name = current_app.config["LANG_OPTIONS"][course["language"]]

        messages = [
            {
                "role": "system",
                "content": (
                    f"You are Muta, an academic tutor replying in {language_name}. "
                    "Assess the student's spoken answer using only the supplied course notes. "
                    "Be fair and encouraging. Focus on academic understanding, not grammar "
                    "or accent. Give a score out of 5, explain what the student got right, "
                    "identify any important missing point, and provide a short improved answer. "
                    "If the notes do not support a judgement, say so."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"COURSE NOTES:\n{quiz['context']}\n\n"
                    f"QUESTION:\n{quiz['question']}\n\n"
                    f"STUDENT'S TRANSCRIBED ANSWER:\n{transcript}"
                ),
            },
        ]

        feedback = natlas_client.chat(
            messages,
            max_tokens=250,
            temperature=0.2,
        ).strip()

        if not feedback:
            return jsonify(
                ok=False,
                message="The answer was transcribed, but feedback could not be generated.",
            ), 502

        course_memory.record_event(
            uid, course_id, "speakback_answer",
            success=True,
            duration_ms=round((time.perf_counter() - started) * 1000),
            language=course["language"],
        )

        return jsonify(
            ok=True,
            transcript=transcript,
            feedback=feedback,
        )

    except pipeline.PipelineError:
        return jsonify(
            ok=False,
            message="That recording is too long. Please record a shorter answer.",
        ), 400
    except audio.AudioError:
        return jsonify(
            ok=False,
            message="Muta could not process that recording. Try recording again.",
        ), 400
    except GatewayError:
        current_app.logger.exception("SpeakBack N-ATLAS request failed")
        course_memory.record_event(
            uid, course_id, "speakback_answer",
            success=False,
            duration_ms=round((time.perf_counter() - started) * 1000),
            language=course["language"],
        )
        return jsonify(
            ok=False,
            message="N-ATLAS is not responding. Check the model gateway.",
        ), 502
    except Exception:
        current_app.logger.exception("Unexpected SpeakBack failure")
        return jsonify(
            ok=False,
            message="Something went wrong while checking your answer. Please try again.",
        ), 500
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)