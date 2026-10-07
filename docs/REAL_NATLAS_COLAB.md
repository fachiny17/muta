# Part 2: Switch to the real N-ATLAS (Google Colab)

You will do three things: (A) get access, (B) start the N-ATLAS gateway on a Colab GPU, (C) point your local app at it and test.
Colab is only a rented GPU computer here. Nothing is trained.

---

## A. Access (10 min, do once)

1. **Hugging Face account** at huggingface.co.
2. Open `https://huggingface.co/NCAIR1/N-ATLaS`, read the terms, and accept them. Approval can be instant or take a while. You cannot load the model until it is approved.
3. Profile → Settings → **Access Tokens** → New token → type **Read** → copy it (starts with `hf_`).
4. Open these four pages in your browser and read the "how to use" part of each:
   `NCAIR1/Hausa-ASR`, `NCAIR1/Yoruba-ASR`, `NCAIR1/Igbo-ASR`, `NCAIR1/NigerianAccentedEnglish`.
   If any name does not exist or is different, you will fix it in Step B6.
5. Make a gateway password on your laptop and copy it:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(24))"
   ```

---

## B. Start the gateway on Colab

**B1. New notebook.** colab.research.google.com → New notebook.
Runtime → Change runtime type → **T4 GPU** → Save. Then run a cell with `!nvidia-smi`. It must list a Tesla T4. If Colab says no GPU is available, try again later or use Kaggle (same files work).

**B2. Add secrets.** Click the **key icon** in the left sidebar → Add new secret:
- `HF_TOKEN` = your Hugging Face token
- `GATEWAY_KEY` = the password from A5

Turn **Notebook access ON** for both. Without this the gateway cannot read them.

**B3. Install packages (Cell 1).**
```python
!pip install -q -U transformers accelerate bitsandbytes fastapi "uvicorn[standard]" python-multipart soundfile nest_asyncio huggingface_hub
```

**B4. Upload the gateway file.** Left sidebar → Files (folder icon) → Upload → choose `muta/gateway/gateway.py`.
It lands in `/content/gateway.py`. (Uploaded files vanish when the runtime resets, so you repeat this each new session.)

**B5. Check that the repos exist (Cell 2).**
```python
from huggingface_hub import HfApi
api = HfApi()
for rid in ["NCAIR1/N-ATLaS", "NCAIR1/Hausa-ASR", "NCAIR1/Yoruba-ASR", "NCAIR1/Igbo-ASR", "NCAIR1/NigerianAccentedEnglish"]:
    try:
        info = api.model_info(rid, files_metadata=True)
        gb = sum((s.size or 0) for s in info.siblings) / 1e9
        print(f"OK   {rid}  ~{gb:.1f} GB")
    except Exception as e:
        print(f"FAIL {rid}: {str(e)[:120]}")
```
Any `FAIL`? For the LLM, you have not been approved yet or the name is slightly different. For an ASR repo, find the correct name on the Hugging Face org page (`huggingface.co/NCAIR1`) and fix `ASR_IDS` at the top of `gateway.py` (Files panel → double-click to edit, or re-upload).

**B6. Start the gateway (Cell 3).**
```python
import sys; sys.path.insert(0, "/content")
import gateway
URL = gateway.start_in_notebook()
```
What happens, in order: loads the LLM in 4-bit (the first time it downloads about 16 GB, so expect 5 to 15 minutes), downloads the four ASR models to disk, starts the server, opens a public Cloudflare link, and prints:
```
GATEWAY_URL = https://something-random.trycloudflare.com
```
Copy that URL. **Leave this cell running** and keep the Colab tab open.

If it fails:
| Error | Meaning / fix |
|---|---|
| `GATED` / 401 / 403 on `NCAIR1/N-ATLaS` | Terms not accepted or not approved yet, or `HF_TOKEN` secret missing/notebook access off |
| `GATEWAY_KEY secret is missing` | Redo B2 and enable Notebook access, then Runtime → Restart session |
| CUDA out of memory | Runtime → Restart session, run B3–B6 again without opening other GPU notebooks |
| `apply_chat_template ... no chat template` | Open the LLM model card, copy its prompt format, and edit `/v1/chat` in `gateway.py` to build the prompt text by hand |
| cloudflared download blocked | Use ngrok instead: `!pip install pyngrok`, then `from pyngrok import ngrok; ngrok.set_auth_token("...")` and `ngrok.connect(8000)` |

**B7. Warm check inside Colab (Cell 4, optional).** Open a new cell and run:
```python
import requests, os
from google.colab import userdata
h = {"x-api-key": userdata.get("GATEWAY_KEY")}
print(requests.get("http://127.0.0.1:8000/health", headers=h).json())
```
You want `"llm_loaded": true`.

---

## C. Connect your local app

**C1. Edit `.env`** in the VS Code project:
```
GATEWAY_URL=https://something-random.trycloudflare.com
GATEWAY_KEY=the-exact-password-from-A5
SECRET_KEY=any-long-random-text
DASHBOARD_KEY=mypassword
```
No trailing slash. Save the file.

**C2. Get a test recording (16 kHz mono WAV).** Pick one:
```bash
# record 5 seconds from your laptop mic (try `-f alsa` if `pulse` fails)
ffmpeg -f pulse -i default -t 5 -ar 16000 -ac 1 test_ha.wav
# or convert a phone voice note
ffmpeg -i voice.ogg -ar 16000 -ac 1 test_ha.wav
```
Say something simple in the language you are testing (for example a short Hausa sentence you can write down).

**C3. Test the real gateway** (venv active, from the project folder):
```bash
python -m scripts.test_gateway test_ha.wav ha
```
Good output looks like:
```
PASS health (...ms): {...'llm_loaded': True...}
PASS chat (...ms): The first law of thermodynamics states...
PASS asr[ha] (...ms): <your sentence>
```
- The **first** ASR call for a language is slow because the model loads onto the GPU. If it times out, run the command again.
- `FAIL health: gateway unreachable`: wrong URL, or the Colab cell stopped. Look at the Colab cell output.
- `rejected request (401)`: `GATEWAY_KEY` in `.env` differs from the Colab secret.
- ASR text is empty or nonsense: compare with the model card's example. Some Whisper fine-tunes need a language or task setting passed to `generate`. Edit the `ids = m.generate(...)` line in `gateway.py` as the card shows, restart Cell 3. If it is still wrong, paste me the card's snippet and your output.

Repeat C3 for each language (`yo`, `ig`, `en`) with a matching clip. Note honestly which ones work.

**C4. Run the app.**
```bash
python run.py
```
Open `http://localhost:5000`. The chip must say **N-ATLAS online**.

**C5. Full flow check.**
1. Agree to the notice, choose a language, tap the mic, ask one short question, tap to stop.
2. You should get the transcript, an answer in that language, and the rating buttons. No "[MOCK]" text anywhere.
3. Click a rating and Yes/No.
4. Open `http://localhost:5000/dashboard?key=mypassword`. It should show 1 participant, 1 interaction, a real latency, and your rating.
5. Check the database:
   ```bash
   sqlite3 data/sauti.db "select id,language,mode,asr_text,substr(reply,1,60),asr_ms,llm_ms,rating from interactions"
   ```
6. Try "Summarize a lesson" with a 30 to 60 second recording.

**C6. Phone test.** The phone microphone needs https:
```bash
cloudflared tunnel --url http://localhost:5000
```
Open that URL on your phone and repeat C5.

---

## D. Running it day to day (Colab realities)

- Keep the Colab tab open and the cell running. Free Colab disconnects after idle time or a maximum session length, and GPU availability is not guaranteed. Do not rely on one session for the whole pilot.
- **Every restart gives a new URL.** Update `GATEWAY_URL` in `.env` and restart `python run.py`.
- Restart routine (about 2 minutes once models are cached; longer if the disk was reset): Runtime → Connect, re-upload `gateway.py` if missing, run B3, B6, copy the URL.
- Before any student session: run `python -m scripts.test_gateway test_ha.wav ha`, and keep the Colab tab visible on a charged laptop.
- If you hit usage limits on free Colab, a paid Colab plan or the Kaggle GPU (same code) are the fallbacks, and the organizers may offer compute (ask them).

---

## E. Before you call it "validated"

- Record the 12 clips for `eval/clips/` + `eval/refs.csv` and run `python -m scripts.evaluate_asr`.
- Keep your own notes of which languages worked and which did not, and report that honestly.
- Real student sessions are what fill the dashboard. Nothing is pre-filled.
