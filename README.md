# Muta

A voice-first academic assistant for Nigerian students, built on **N-ATLAS** (NAIC 2026, PS2: Voice-First Access).
A student speaks a question in Nigerian English, Hausa, Yoruba or Igbo, N-ATLAS transcribes it and writes an academic answer,
the student rates it, and every interaction is logged for a validation dashboard.

**Start here:** `docs/WEB_GUIDE.md` (the complete learn-as-you-build guide, from your laptop to a live Render link).
**What changed and why:** `CHANGES.md`.

## Architecture
```
 Browser (static/js/tutor.js, templates/index.html)  --- microphone recording --->  Flask app (app/routes.py)
                                                                                         |
                                                                       shared pipeline (app/pipeline.py)
                                              audio.py: ffmpeg -> 16 kHz mono, chunks <= 28 s
                                                                                         |  HTTPS + x-api-key
                                                               N-ATLAS GATEWAY (gateway/gateway.py on a Colab/Kaggle GPU)
                                                 /v1/asr -> N-ATLAS ASR (4 models)     /v1/chat -> N-ATLAS LLM (NCAIR1/N-ATLaS, 4-bit)
                                                                                         |
                                  answer -> rating + "did it help?" -> SQLite -> /dashboard, /export.csv, /evidence
```
No other ASR or LLM is used anywhere. The Flask app never loads the models; it only calls the gateway.

## Quick start (about 10 minutes, no GPU needed)
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                     # then edit: SECRET_KEY, DASHBOARD_KEY, GATEWAY_URL, GATEWAY_KEY
python -m pytest -q                      # automated tests
python -m scripts.mock_gateway           # terminal 1: stand-in for the GPU server (NOT N-ATLAS)
python run.py                            # terminal 2: http://localhost:5000
python -m scripts.smoke_test http://localhost:5000     # terminal 3: checks the running server
```
For real N-ATLAS see `docs/REAL_NATLAS_COLAB.md`. For hosting see `docs/FREE_HOSTING.md` (free) and `docs/DEPLOY_RENDER.md` (paid).

## Project map
| Path | Purpose |
|---|---|
| `run.py` | Entry point (`gunicorn run:app` in production) |
| `app/__init__.py` | App factory: config, database, gateway client, error handlers |
| `app/routes.py` | Web pages and the JSON API (`/api/ask`, `/api/feedback`, dashboard, evidence, admin) |
| `app/pipeline.py` | The shared brain: transcribe -> answer -> log -> feedback |
| `app/natlas_client.py` | The only code that talks to the gateway |
| `app/audio.py` | ffmpeg conversion and chunking |
| `app/prompts.py` | Tutor and summary prompts (edit here to change behaviour) |
| `app/db.py` | SQLite schema, logging, statistics, CSV export |
| `gateway/gateway.py` | Runs the real N-ATLAS models on a GPU host |
| `templates/`, `static/` | Pages, NexLearn-based styling, recorder script |
| `scripts/` | `mock_gateway`, `test_gateway`, `smoke_test`, `evaluate_asr`, `make_report`, `publish_evidence` |
| `tests/` | Automated tests (`tests/frontend/` is an optional browser-logic test) |
| `render.yaml` | Free Render deployment blueprint |
| `app/whatsapp.py` | **Paused.** Optional WhatsApp channel, off by default (`WHATSAPP_ENABLED=0`) |

## Privacy
Anonymous IDs (`USR_XXXXXXXX`); no names, emails or phone numbers. Recordings are deleted right after processing. The metrics CSV has no question
text; exporting text needs the admin key.

## Known limitations
Manual language choice (no auto-detect); per-language ASR quality varies and must be measured; push-to-talk (not live streaming); free hosting sleeps and
does not keep files; the N-ATLAS model server runs on a free GPU notebook whose session can end.
