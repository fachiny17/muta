"""The shared academic pipeline. Web and WhatsApp both call handle_voice().

voice -> audio normalisation -> N-ATLAS ASR -> N-ATLAS LLM -> answer -> logged
"""
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass

from app import audio, db, natlas_client, prompts
from app.natlas_client import GatewayError

log = logging.getLogger("classvoice")
SETTINGS = {"max_audio_s": 90, "max_summary_audio_s": 180}

MSG_AUDIO = "Sorry, I could not read that recording. Please try recording again."
MSG_TOO_LONG = "That recording is too long. Please ask one question at a time (under {s} seconds)."
MSG_EMPTY = "I could not hear a clear question. Please speak closer to the phone and try again."
MSG_ASR = "Sorry, I could not process your voice right now. Please try again in a moment."
MSG_LLM = "I understood your question, but I could not generate an answer right now. Please try again."


class PipelineError(Exception):
    pass


@dataclass
class Transcription:
    text: str
    duration_s: float
    asr_ms: int


def transcribe(audio_path: str, lang: str, max_s: int | None = None) -> Transcription:
    """Normalise audio, chunk if needed, and run N-ATLAS ASR on each chunk."""
    workdir = tempfile.mkdtemp(prefix="cv_")
    try:
        wav = audio.to_wav(audio_path, workdir)
        dur = audio.duration_s(wav)
        if dur > (max_s or SETTINGS["max_audio_s"]):
            raise PipelineError("audio_too_long")
        parts = audio.chunk_wav(wav, workdir)
        t0 = time.time()
        texts = [natlas_client.asr(p, lang) for p in parts]
        asr_ms = int((time.time() - t0) * 1000)
        text = " ".join(t.strip() for t in texts if t and t.strip()).strip()
        return Transcription(text, round(dur, 2), asr_ms)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def answer_question(question: str, lang: str, history: list | None = None) -> tuple:
    """Ask the N-ATLAS LLM. Returns (reply, llm_ms)."""
    t0 = time.time()
    reply = natlas_client.chat(prompts.question_messages(question, lang, history)).strip()
    return reply, int((time.time() - t0) * 1000)


def summarize_text(text: str, lang: str) -> tuple:
    """Summarise a lesson transcript with the N-ATLAS LLM. Returns (summary, llm_ms)."""
    t0 = time.time()
    out = natlas_client.chat(prompts.summary_messages(text, lang), max_tokens=350).strip()
    return out, int((time.time() - t0) * 1000)


def log_interaction(**kw) -> int:
    return db.log_interaction(**kw)


def record_feedback(interaction_id: int, user_id: str, rating=None, task_completed=None) -> bool:
    return db.record_feedback(interaction_id, user_id, rating, task_completed)


def handle_voice(audio_path: str, lang: str, user_id: str, channel: str, audio_bytes: int | None = None,
                 mode: str = "question") -> dict:
    """Run the full pipeline, log it (success or failure), return a UI-ready dict."""
    t0 = time.time()
    summary = mode == "summary"
    rec = dict(user_id=user_id, language=lang, input_channel=channel, mode=mode, audio_bytes=audio_bytes,
               audio_duration=None, asr_text=None, reply=None, asr_success=0, llm_success=None,
               asr_ms=None, llm_ms=None, error=None)
    user_msg = None
    try:
        tr = transcribe(audio_path, lang, SETTINGS["max_summary_audio_s"] if summary else None)
        rec.update(audio_duration=tr.duration_s, asr_ms=tr.asr_ms, asr_text=tr.text)
        if not tr.text:
            rec["error"] = "empty_transcript"
            user_msg = MSG_EMPTY
        else:
            rec["asr_success"] = 1
            try:
                reply, llm_ms = (summarize_text if summary else answer_question)(tr.text, lang)
                rec.update(reply=reply, llm_ms=llm_ms, llm_success=1 if reply else 0)
                if not reply:
                    rec["error"] = "empty_reply"
                    user_msg = MSG_LLM
            except GatewayError as e:
                rec.update(llm_success=0, error=f"llm: {e}"[:300])
                user_msg = MSG_LLM
    except PipelineError:
        rec["error"] = "audio_too_long"
        user_msg = MSG_TOO_LONG.format(s=SETTINGS["max_summary_audio_s"] if summary else SETTINGS["max_audio_s"])
    except audio.AudioError as e:
        rec["error"] = f"audio: {e}"[:300]
        user_msg = MSG_AUDIO
    except GatewayError as e:
        rec["error"] = f"asr: {e}"[:300]
        user_msg = MSG_ASR
    except Exception as e:  # never let a request crash the app
        log.exception("unexpected pipeline failure")
        rec["error"] = f"unexpected: {e}"[:300]
        user_msg = MSG_ASR
    rec["latency_ms"] = int((time.time() - t0) * 1000)
    iid = log_interaction(**rec)
    ok = rec["llm_success"] == 1
    return {"interaction_id": iid, "ok": ok, "transcript": rec["asr_text"] or "",
            "answer": rec["reply"] if ok else "", "message": None if ok else user_msg,
            "error": rec["error"], "latency_ms": rec["latency_ms"], "asr_ms": rec["asr_ms"],
            "llm_ms": rec["llm_ms"]}
