# Change log: from Sauti-Tutor to ClassVoice NG (web edition)

## 1. Direction changes
| Before | Now | Why |
|---|---|---|
| Sauti-Tutor: FastAPI + Streamlit + WhatsApp only | ClassVoice NG: Flask + HTML/JS web app (NexLearn base), WhatsApp optional and **paused** | One reliable channel judges can open from a link; reuse your NexLearn work |
| Deepgram (ASR) + Gemini (summaries) in NexLearn | N-ATLAS ASR + N-ATLAS LLM only | The competition requires genuine N-ATLAS integration |
| Socket.IO live streaming | Push-to-talk: record, stop, one POST | N-ATLAS ASR works on chunks; simpler and more robust |
| Language auto-detect idea | Explicit language menu | Reliability for the first release |
| Lesson-upload + retrieval idea | Q&A plus a "Summarize a lesson" mode | Keeps scope achievable; keeps NexLearn's summary idea |

## 2. Architecture and backend
- **Shared pipeline** (`app/pipeline.py`): `transcribe()`, `answer_question()`, `summarize_text()`, `log_interaction()`, `record_feedback()`, orchestrated by `handle_voice()`. All academic logic lives here once.
- **Gateway client** (`app/natlas_client.py`): retries, clear `GatewayError`, no retry on 4xx. The app never loads models.
- **App factory** (`create_app`): configuration, DB init, gateway config, JSON error handlers (413/500 for `/api/*`), reverse-proxy awareness (`ProxyFix`) and Secure cookies on HTTPS.
- **Graceful failure**: every stage failure is caught, shown to the user as a friendly message, and **logged** (so success rates are honest).
- **Rate limit**: 30 interactions per user per hour (`RATE_LIMIT_PER_HOUR`).
- **Prompts module** (`app/prompts.py`): `tutor_system()`, `question_messages()`, `summary_messages()`.

## 3. N-ATLAS gateway (`gateway/gateway.py`)
- Endpoints `/health`, `/v1/asr`, `/v1/chat`, protected by `x-api-key`.
- LLM loaded in 4-bit; ASR models lazy-loaded (max 2 resident); weights pre-downloaded; one GPU job at a time.
- Honest errors: a language whose model fails to load returns 503 with the reason.
- Secrets read from environment / Colab Secrets / Kaggle Secrets; never in code or the browser.
- **Heartbeat**: the notebook re-registers its public URL with the hosted app every minute, so Colab restarts need no manual URL edits.

## 4. Audio (`app/audio.py`)
- Any browser format -> 16 kHz mono WAV via ffmpeg; automatic fallback to a bundled ffmpeg (`imageio-ffmpeg`) so Render needs no Docker.
- Long recordings split at the quietest moment near each 28 s boundary (standard library only; no pydub).
- Recordings are deleted right after processing.

## 5. Database (`app/db.py`)
- Tables: `users`, `interactions` (incl. `input_channel`, `mode`, `asr_ms`, `llm_ms`, `latency_ms`, `audio_bytes`, `rating`, `task_completed`, `error`), `settings`, `wa_seen`.
- Statistics computed from real rows only; "n/a" when empty. Anonymous IDs `USR_XXXXXXXX`.

## 6. Web interface (NexLearn reuse)
- Reused: dark theme and layout, logo, big mic button, recording timer and visualizer, theme toggle, toast pattern, copy/download helpers, lesson-summary idea.
- Removed: starfield animation, Google Fonts, dicebear avatar and placeholder profile, dead buttons, Socket.IO, Deepgram, Gemini.
- Added: consent notice, language picker, Ask/Summarize modes, rating (1-5) and "did it help?" feedback, offline banner with demo-video link, sample questions, favicon, low-bitrate recording (24 kbps) and upload-size display.
- Security fixes carried from NexLearn: no `innerHTML` for model output, no hard-coded secret key, no open CORS, no debug mode.

## 7. Validation and evidence
- `/dashboard` (key-protected) with real metrics; `/export.csv` (metrics only; text needs the admin key).
- `scripts/evaluate_asr.py` (WER per language, latency), `scripts/make_report.py` (real-data report), `scripts/publish_evidence.py` + `/evidence` page (frozen snapshot that works on free hosting).

## 8. Hosting
- `render.yaml` (free plan), `render.paid.example.yaml`, `/healthz`, `/internal/gateway`, `/admin/backup.sqlite`, `gunicorn` start command (1 worker, 4 threads, 180 s timeout).
- `requirements.txt` (server only) vs `requirements-dev.txt` (tests, evaluation).

## 9. Testing (what is proven)
- 29 automated tests (pipeline, routes, audio, privacy, admin, evidence).
- `scripts/smoke_test.py` for any running server (local or Render).
- `tests/frontend/fe_test.js`: real page + real JavaScript driven through consent, language, recording, answer, rating, and database check.
- Verified in a clean virtual environment with only `requirements.txt`, no system ffmpeg, started with the exact Render command.
- **Not verified here:** real N-ATLAS model output (needs your GPU), real browser microphones on phones, real Render deployment, real Twilio.

## 10. Paused
- WhatsApp (`app/whatsapp.py`, `docs/paused/WHATSAPP_AND_PILOT.md`): code and 7 tests remain; disabled by default; the web app does not import it.
