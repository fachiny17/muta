# ClassVoice NG: Complete Web Guide (learn as you build, laptop to live link)

How to use this guide: do the steps in order. Every part has **Why** (the idea you are learning), **Do** (commands), and **Check** (how you know it worked). Parts marked **Learn** are short code tours with exercises. Do not skip the checks; they are how you find problems early.

Suggested schedule (deadline Oct 12): **Wed Oct 7** Parts 1 to 6 (run locally, deploy). **Thu Oct 8 to Sat Oct 10** Part 8 (pilot). **Sun Oct 11** Part 9 (evidence, video, submit). Oct 12 is buffer only.

---

## Part 0. The big picture

**What you are building:** a web page where a student speaks a question; the server turns speech into text (ASR), asks the language model (LLM) for an academic answer, shows it, and records feedback.

**The one idea that explains the whole project:** the model is too heavy for normal computers, so the system has **two halves**.

```
 Student's phone/laptop (browser)
        |   1. records voice, sends it
        v
 FLASK APP  (light; runs on your laptop or on Render)
        |   2. cleans the audio, calls the gateway
        v
 N-ATLAS GATEWAY  (heavy; runs on a free GPU in Colab or Kaggle)
        |   3. ASR model -> text   4. LLM -> answer
        v
 back to Flask: 5. save to SQLite  6. show answer  7. student rates it
```

Vocabulary you will use: **ASR** (speech-to-text), **LLM** (the language model that writes answers), **API/endpoint** (a URL the program answers, like `/api/ask`), **gateway** (the small server in front of the models), **tunnel** (a temporary public web address pointing at a program on another machine).

**Check:** you can explain, in your own words, why Render alone cannot run N-ATLAS. (Answer: no free host has a GPU big enough, so the gateway stays on Colab/Kaggle.)

---

## Part 1. Set up your workspace

**Why:** a *virtual environment* keeps this project's Python packages separate from everything else on your computer. A `.env` file keeps secrets out of your code.

**Do:**
1. Unzip `classvoice-ng.zip`. In VS Code: File → Open Folder → the `classvoice` folder.
2. Open the terminal (`` Ctrl+` ``) and run:
   ```bash
   python3 -m venv venv
   source venv/bin/activate          # your prompt now starts with (venv)
   pip install -r requirements-dev.txt
   cp .env.example .env
   ```
3. VS Code: `Ctrl+Shift+P` → "Python: Select Interpreter" → choose the one inside `venv`.
4. Edit `.env` (keep it private; it is git-ignored):
   ```
   SECRET_KEY=type-a-long-random-sentence-here
   DASHBOARD_KEY=pick-a-dashboard-password
   ADMIN_KEY=pick-another-long-secret
   GATEWAY_URL=http://127.0.0.1:9000
   GATEWAY_KEY=anything-for-now
   ```
5. ffmpeg: nothing to install. The project falls back to a bundled copy. (Optional: `sudo apt install ffmpeg`.)

**Check:** `python -c "import flask, httpx; print('ok')"` prints `ok`.

---

## Part 2. Run the automated tests

**Why:** tests are small programs that check your program. When you change code later, they tell you immediately if you broke something.

**Do:** `python -m pytest -q`

**Check:** you should see about `29 passed`. If a test fails, read the first red line; it names the file and the problem.

**Learn (5 min):** open `tests/test_pipeline.py`. Find `test_asr_failure_is_graceful_and_logged`. It uses `monkeypatch` to *pretend* the gateway is broken, then checks that the user gets a friendly message **and** the failure is recorded. Notice the pattern: arrange (fake a failure), act (call the pipeline), assert (check the result).

---

## Part 3. Run the app with the mock gateway

**Why:** you can build and test everything except the AI itself without a GPU. The mock returns fixed text labelled **[MOCK]**. It is not N-ATLAS and must never be used for the demo or the pilot.

**Do:** open three terminals (each with `source venv/bin/activate`):
```bash
python -m scripts.mock_gateway                           # terminal 1
python run.py                                            # terminal 2 -> http://localhost:5000
python -m scripts.smoke_test http://localhost:5000       # terminal 3
```
Open `http://localhost:5000`: agree to the notice, choose a language, tap the mic, speak for 3 seconds, tap again.

**Check:**
- The chip at the top right says **N-ATLAS online** (it is really the mock).
- You see a transcript and an answer starting with `[MOCK`. Rate it.
- Smoke test prints `PASS` lines and "All checks passed."
- `sqlite3 data/sauti.db "select id,language,mode,asr_ms,llm_ms,rating from interactions"` shows your row.
- Dashboard: `http://localhost:5000/dashboard?key=<your DASHBOARD_KEY>` shows 1 interaction.

**Break it on purpose (this is how you learn):** stop terminal 1 and ask again. You should get a friendly message, not a crash, and the dashboard's "failed" counter goes up. Restart the mock afterwards.

---

## Part 4. Learn: a tour of the code

Read in this order, 10 minutes each. Everything lives in `app/`.

| Order | File | The question it answers |
|---|---|---|
| 1 | `routes.py` | What happens when the browser sends a recording? (`/api/ask`) |
| 2 | `pipeline.py` | What are the steps, and what if one fails? (`handle_voice`) |
| 3 | `natlas_client.py` | How does Flask talk to the gateway? |
| 4 | `audio.py` | Why convert to 16 kHz mono, and why chunk at 28 s? |
| 5 | `prompts.py` | How do we tell the model how to behave? |
| 6 | `db.py` | What do we store, and how are the dashboard numbers computed? |
| 7 | `static/js/tutor.js` | How does the browser record and send audio? |

**Key ideas to notice**
- **One pipeline, thin routes.** `routes.py` only handles web details; the thinking is in `pipeline.py`. That is why WhatsApp could be added later without rewriting anything.
- **Log failures too.** Every attempt is saved, including errors, so "ASR success rate" is honest.
- **Privacy by design.** Anonymous ID in a cookie; recording deleted right after processing; the browser never sees any key.
- **Defensive web code.** Uploads are size-limited; the user can only rate their own interactions; admin routes return 404 without the key.

**Exercises**
1. In `app/prompts.py` change "under 120 words" to "under 60 words". Run the tests. Does anything fail? Why or why not?
2. Remove `ig` from `ENABLED_LANGS` in `.env`, restart, and see the menu change. (A config change, no code.)
3. Add a test in `tests/test_routes.py` that posts without a file and expects HTTP 400. Copy the style of `test_requires_consent_and_valid_language`.
4. Find where the 30-per-hour rate limit is applied and temporarily set `RATE_LIMIT_PER_HOUR=2` in `.env`. Ask three times. What does the third response say?

---

## Part 5. Switch to real N-ATLAS (Colab)

You have already done this once; here is the repeatable routine. Full details: `docs/REAL_NATLAS_COLAB.md`.

**Do (each time you start a GPU session):**
1. colab.research.google.com → open your notebook → Runtime → T4 GPU. Secrets (key icon, notebook access ON): `HF_TOKEN`, `GATEWAY_KEY`. After Part 7 also `APP_URL` and `ADMIN_KEY`.
2. Upload the latest `gateway/gateway.py` to `/content`.
3. Run these cells:
   ```python
   !pip install -q -U transformers accelerate bitsandbytes fastapi "uvicorn[standard]" python-multipart soundfile nest_asyncio huggingface_hub
   ```
   ```python
   import sys, importlib; sys.path.insert(0, "/content")
   import gateway; importlib.reload(gateway)
   URL = gateway.start_in_notebook()
   ```
4. Copy the printed `GATEWAY_URL` into your local `.env` (the same `GATEWAY_KEY` as Colab), and restart `python run.py`.

**Check:** `python -m scripts.test_gateway clip.wav ha` prints three PASS lines; the web app now answers without `[MOCK]`. Test every language you plan to show and write down which ones work well.

**Why this step repeats:** free Colab sessions end. Each new session gets a new tunnel URL. In Part 7 the hosted app learns the URL automatically (the heartbeat); your laptop app still needs the manual `.env` edit.

---

## Part 6. Put the project on GitHub

**Why:** Render deploys straight from a GitHub repository. Git also gives you version history, which is a safety net.

**Do (easiest way, in VS Code):**
1. Check `.gitignore` is present. Then in the terminal: `git init && git add . && git status`. Confirm `.env` and `venv/` are **not** listed. If `.env` appears, stop and fix `.gitignore` first.
2. `git commit -m "ClassVoice NG web version"` (if git asks who you are: `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`).
3. Create a GitHub account if needed. In VS Code open the Source Control panel → **Publish Branch** → choose **private repository**. VS Code handles the login for you.

**Check:** on github.com your repo shows `app/`, `templates/`, `render.yaml`, and **no** `.env`.

**Learn:** after every future change, `git add . && git commit -m "what changed" && git push` re-deploys the site automatically (Part 7).

---

## Part 7. Deploy on Render (free)

**Why:** Render gives your Flask app a public https link that you share with judges. The free plan costs nothing and needs no card, but remember its two limits: it sleeps after about 15 minutes idle (about one minute to wake), and **its files are erased on restart**, including the SQLite database. That is why the pilot data is collected on your laptop (Part 8) and Render is the judge-facing demo.

**Do:**
1. render.com → sign up with GitHub.
2. **New → Blueprint** → select your repo. Render reads `render.yaml` and proposes a free web service named `classvoice-ng`.
3. It asks for `GATEWAY_KEY`: enter the **same** secret you put in Colab. Click **Apply**.
4. Wait for the build log to end with "Your service is live". Your link looks like `https://classvoice-ng.onrender.com`.
5. In the service's **Environment** tab, reveal and copy `ADMIN_KEY` and `DASHBOARD_KEY`.
6. In Colab Secrets add `APP_URL` (your Render link, no trailing slash) and `ADMIN_KEY` (copied value). Re-run the gateway cell. You should see `Heartbeat started`.

**Check:**
```bash
python -m scripts.smoke_test https://classvoice-ng.onrender.com
python -m scripts.smoke_test https://classvoice-ng.onrender.com clip.wav ha     # full pipeline with real N-ATLAS
```
The first request may take about a minute (waking up). Then open the link on your phone: the chip should say **N-ATLAS online**; ask a question.

**If something breaks:** Render dashboard → your service → **Logs**. Common causes: wrong `GATEWAY_KEY` (401 errors), Colab not running (the page shows "The AI server is resting"), missing heartbeat secrets.

**Optional:** a free uptime monitor (e.g., UptimeRobot) pinging `/healthz` every few minutes reduces sleeping. Not guaranteed; Render may restart free services anytime.

---

## Part 8. Run the pilot (this produces your evidence)

**Goal:** 100 or more real logged interactions from 15 or more students (the requirement is 50+; extra covers failures). Only real use counts. Never add fake rows.

**Where to run it:** on your **laptop**, where the SQLite file survives.
```bash
python run.py                                         # terminal 1
cloudflared tunnel --url http://localhost:5000        # terminal 2 -> prints https://xxxx.trycloudflare.com
```
Share that link with students. If you restart Colab, update `GATEWAY_URL` in `.env` and restart `python run.py`. Keep the laptop awake and charged. **Do not change `SECRET_KEY`** during the pilot.

**Steps:**
1. Get a teacher's agreement for one class (voluntary, no names or numbers collected). For students under 18 follow the school's rules and get approval.
2. Day 1 session (20 min, in person if possible): students open the link on their phones, agree to the notice, pick their language, ask one practice question.
3. Daily: each student asks 3 or more real homework questions. Example card (translate it with a native speaker):
   > ClassVoice NG: ask your school questions by voice. 1) Open the link. 2) Tap "I understand and agree". 3) Choose your language. 4) Tap the microphone, ask ONE question, tap again. 5) Rate the answer 1 to 5 and say whether it helped.
4. Every evening (5 minutes): open `/dashboard?key=...`. Check failures, read the `error` column (`sqlite3 data/sauti.db "select error,count(*) from interactions group by 1"`), fix real bugs, back up: `cp data/sauti.db backup-$(date +%F).db`.
5. Before each session: confirm Colab is running, run `python -m scripts.test_gateway clip.wav ha`.

**Learn:** the dashboard's "ASR success" and "LLM success" measure whether each *stage ran*, not whether the answer was *correct*. Correctness shows up only in ratings. Explain this honestly in your write-up.

---

## Part 9. Evidence and submission (Sun Oct 11)

1. **ASR accuracy:** record 12 or more short clips with native speakers into `eval/clips/`, add rows `file,lang,reference` to `eval/refs.csv`, then `python -m scripts.evaluate_asr`.
2. **Freeze the evidence on your site:**
   ```bash
   python -m scripts.publish_evidence       # report + metrics-only CSV from your REAL database
   git add evidence && git commit -m "pilot evidence" && git push
   ```
   After Render redeploys, `https://<your-app>.onrender.com/evidence` shows the results and a CSV download.
3. **Demo video (3 min):** problem (20 s); a Hausa or Yoruba voice question, transcript, answer, rating; the Ask/Summarize modes; dashboard with real numbers; one sentence on where N-ATLAS ASR and LLM are used. Upload it somewhere public and put the link in Render's `DEMO_VIDEO_URL` environment variable.
4. **Submission text:** judge link (Render URL); evidence link (`/evidence`); a sentence "the AI model runs on a separate GPU server; if the page says it is resting, see the demo video"; honest limitations (manual language choice, measured per-language quality, free hosting sleeps, small sample, hosted demo data resets). Include sample questions for English-speaking judges.
5. **Judging window:** ask the organizers when judging happens; keep Colab running then, and test the live link yourself 10 minutes before.

**Final checklist**
- [ ] `python -m pytest -q` passes
- [ ] Render link works on a phone, with real N-ATLAS (no `[MOCK]` text)
- [ ] `/evidence` shows your real report and CSV
- [ ] Repo is private or clean: no `.env`, no tokens, no databases
- [ ] Demo video link set
- [ ] You can explain every file in the table in Part 4

---

## Troubleshooting
| Symptom | Likely cause | Fix |
|---|---|---|
| Chip says "N-ATLAS offline" | Gateway not running or URL/key wrong | Check Colab cell; update `GATEWAY_URL`; same `GATEWAY_KEY` both sides |
| "Could not read that recording" | Audio decode failed | Try again; check Flask log; very short clips are rejected |
| Empty transcript | Silence, noise, or ASR model mismatch | Speak closer; compare with the model card; test with `test_gateway` |
| Mic does nothing on phone | Page not on https | Use the Render or tunnel https link |
| Render page very slow at first | Free instance waking up | Wait about a minute; use an uptime monitor |
| Render dashboard shows 0 after a while | Free filesystem was wiped | Expected; pilot data lives on your laptop |
| 401 in Render logs | `GATEWAY_KEY` mismatch | Re-enter in Render and Colab |
| Heartbeat failed in Colab | Wrong `APP_URL`/`ADMIN_KEY` or app asleep | Check secrets; open the Render link once and retry |

## Glossary
**Blueprint** (`render.yaml`): a file describing a Render deployment. **Cold start**: waking a sleeping server. **Cookie**: a small value the browser stores; ours holds an anonymous ID. **Environment variable**: a setting kept outside the code. **Ephemeral**: disappears on restart. **gunicorn**: the production web server that runs Flask. **Heartbeat**: a repeating "I am here at this URL" message. **ProxyFix**: lets Flask know it is behind Render's HTTPS proxy. **SQLite**: a database stored in one file. **WER**: word error rate, how wrong a transcript is.
