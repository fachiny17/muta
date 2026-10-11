# Muta

A voice-first academic assistant for Nigerian students, built on **N-ATLAS** (NAIC 2026, PS2: Voice-First Access).

A student speaks a question in Nigerian English, Hausa, Yoruba, or Igbo. N-ATLAS transcribes the audio and generates an academic answer. The student can rate the response and indicate whether it was helpful, while interactions are logged for a validation dashboard.

**Start here:** `docs/WEB_GUIDE.md` — the complete learn-as-you-build guide, from your laptop to a live Render link.

**What changed and why:** `CHANGES.md`.

## Features

- Voice-based academic questions and lesson summaries.
- Manual language selection for Nigerian English, Hausa, Yoruba, and Igbo.
- Speech recognition and academic responses through N-ATLAS.
- Audio conversion and chunking for processing longer recordings.
- Anonymous interaction logging and user feedback.
- Dashboard, CSV export, and evidence reporting.
- Optional WhatsApp integration, disabled by default.
- Local mock gateway for development without a GPU.

## Architecture

```text
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

The Flask application does not load the AI models directly. It sends authenticated requests to the N-ATLAS gateway, which handles speech recognition and language model inference.

The mock gateway is a development substitute for the real model service. It does not run actual N-ATLAS inference.

## Getting Started

### Prerequisites

Install the following:

- Python version supported by the project's dependencies. Python 3.12 is recommended if it matches the repository's requirements.
- Git.
- FFmpeg, if required by the audio-processing setup.
- A code editor such as Visual Studio Code.

### 1. Clone the Repository

Open PowerShell, CMD, or your terminal and run:

```bash
git clone https://github.com/fachiny17/muta.git
cd muta
```

If Git is not installed, download Git for Windows from:

https://git-scm.com/download/win

After installing Git, restart your terminal and verify the installation:

```bash
git --version
```

### 2. Create a Virtual Environment

**Windows (PowerShell):**

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (CMD):**

```bat
py -3.12 -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

If Python 3.12 is unavailable, check the project's dependency requirements before choosing another version.

### 3. Install Dependencies

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install the development dependencies:

```bash
pip install -r requirements-dev.txt
```

If the development requirements file is unavailable, check the repository for the appropriate requirements file.

### 4. Configure Environment Variables

Check for an `.env.example` file in the project root.

Copy it to `.env`:

**Windows (PowerShell):**

```powershell
Copy-Item .env.example .env
```

**Windows (CMD):**

```bat
copy .env.example .env
```

**macOS/Linux:**

```bash
cp .env.example .env
```

Open `.env` in your editor and configure the required settings. The original setup instructions identify these variables:

- `SECRET_KEY`
- `DASHBOARD_KEY`
- `GATEWAY_URL`
- `GATEWAY_KEY`

For local mock development, configure the gateway URL and authentication key according to the mock gateway's implementation and the project's setup guide.

Use `.env.example`, the application configuration, and the documentation to determine the complete set of required variables.

Never commit `.env` or publish real credentials and API keys.

### 5. Run Automated Tests

From the project root, run:

```bash
python -m pytest -q
```

The tests help verify application functionality. Their coverage depends on the tests included in the repository.

## Running Locally Without a GPU

The mock gateway allows you to test the web application without downloading or loading the real N-ATLAS models.

**Important:** Mock mode does not demonstrate the actual speech recognition or AI response quality of the real N-ATLAS models.

### Terminal 1: Start the Mock Gateway

Activate the virtual environment, then run:

```bash
python -m scripts.mock_gateway
```

Keep this terminal running.

### Terminal 2: Start the Flask Application

Open a second terminal in the project directory, activate the virtual environment, and run:

```bash
python run.py
```

### Open the Application

Visit the local address shown in the terminal, typically:

http://localhost:5000

### Terminal 3: Run the Smoke Test

With the application and mock gateway running, execute:

```bash
python -m scripts.smoke_test http://localhost:5000
```

This checks the running application according to the smoke-test script's implementation.

If a command fails, review the error message and verify that the referenced file and required configuration exist.

## Connecting to Real N-ATLAS Models

Real speech recognition and language model inference require a reachable GPU-hosted gateway with the required models and dependencies.

Start with these guides if they are present in the repository:

- `docs/REAL_NATLAS_COLAB.md` — real N-ATLAS gateway setup.
- `docs/WEB_GUIDE.md` — application setup and walkthrough.
- `docs/FREE_HOSTING.md` — free hosting guidance.
- `docs/DEPLOY_RENDER.md` — Render deployment guidance.

The web application and GPU gateway are separate services. Running Flask locally does not automatically start the real AI models.

## Project Map

| Path | Purpose |
|---|---|
| `run.py` | Application entry point. |
| `app/__init__.py` | Application factory, configuration, database setup, and service wiring. |
| `app/routes.py` | Web pages, JSON APIs, dashboard, evidence, and administrative routes. |
| `app/pipeline.py` | Shared processing pipeline: transcription, response generation, logging, and feedback. |
| `app/natlas_client.py` | Client responsible for communicating with the gateway. |
| `app/audio.py` | Audio conversion and chunking. |
| `app/prompts.py` | Prompts for tutoring and lesson summaries. |
| `app/db.py` | SQLite schema, interaction logs, statistics, and CSV export. |
| `gateway/gateway.py` | Gateway for running N-ATLAS models on a GPU host. |
| `templates/` | HTML templates, including the main interface. |
| `static/` | Frontend assets, including JavaScript and styles. |
| `scripts/` | Mock gateway, smoke tests, evaluation tools, and reporting utilities. |
| `tests/` | Automated tests. |
| `docs/` | Setup guides, architecture notes, and deployment documentation. |
| `data/` | Project data and related resources. |
| `eval/` | Evaluation resources. |
| `notebook/` | Notebook-based experimentation and analysis. |
| `requirements.txt` | Application dependencies. |
| `requirements-dev.txt` | Development and testing dependencies. |
| `CHANGES.md` | Project change notes. |
| `render.yaml` | Render deployment blueprint. |
| `app/whatsapp.py` | Optional WhatsApp integration; paused and disabled by default. |

Descriptions should be checked against the current repository before publishing.

## API Endpoints

The application documentation identifies routes for question submission, feedback, dashboard access, exports, and evidence.

| Endpoint | Purpose |
|---|---|
| `/api/ask` | Submit a question for processing. |
| `/api/feedback` | Submit feedback for an interaction. |
| `/dashboard` | View dashboard information. |
| `/export.csv` | Export available metrics. |
| `/evidence` | Access evidence-related information. |

Consult `app/routes.py` for the current endpoint definitions, HTTP methods, request formats, and authentication requirements.

## Privacy and Security

- Anonymous IDs use the `USR_XXXXXXXX` format.
- The documented interaction flow does not collect names, email addresses, or phone numbers.
- Audio recordings are intended to be deleted after processing.
- The metrics CSV does not include question text.
- Exporting question text requires the admin key, according to the original project documentation.
- Production secrets should be configured through environment variables.
- Never commit `.env`, private credentials, or sensitive datasets.

Review the current implementation and deployment settings before using real student data.

## Testing and Evaluation

Run the automated test suite:

```bash
python -m pytest -q
```

Run the smoke test against a running local application:

```bash
python -m scripts.smoke_test http://localhost:5000
```

The repository also includes evaluation and reporting utilities, such as `scripts/evaluate_asr`, `scripts/make_report`, and `scripts/publish_evidence`.

Consult the relevant scripts and documentation for their arguments and requirements. Speech recognition quality should be evaluated separately across supported languages.

## Known Limitations

- Language selection is manual; automatic language detection is not currently available.
- Speech recognition quality may vary across languages and accents.
- Audio interaction uses push-to-talk recording rather than continuous live streaming.
- Real inference depends on the availability of the GPU-hosted N-ATLAS gateway.
- Free hosting services may sleep or have ephemeral storage.
- Data stored on an ephemeral filesystem may not survive restarts or redeployments.
- Mock responses do not represent real N-ATLAS inference quality.