# Deploying Muta for judges (Render): PAID option

> The default `render.yaml` is now the FREE plan (see `docs/FREE_HOSTING.md` and `docs/WEB_GUIDE.md`). To use this paid Starter + disk setup, copy `render.paid.example.yaml` over `render.yaml`.


## The honest picture first
The app has two halves:
1. **The web app (Flask)**: light, easy to host. Render hosts it and gives you a permanent https link. This also fixes the WhatsApp tunnel problem, because Twilio's webhook URL never changes.
2. **The N-ATLAS model server (gateway)**: an 8-billion-parameter model that needs a GPU. Render cannot run it. It stays on Colab/Kaggle (or another GPU host), and that half is the only fragile part.

So "one link that never crashes" is true for the app, not for the GPU. This guide makes the GPU half as painless as possible: it **registers its own URL** with the hosted app (no manual copying), and the app shows a clear "server resting" page plus your demo video when the GPU is offline instead of breaking.

## Render plan: what to choose
- **Free web service**: sleeps after 15 minutes idle and takes about a minute to wake; its disk is wiped on every restart, redeploy or sleep. That would **delete your SQLite validation data**, and Twilio's webhook would time out on wake-up. Fine for a quick look, **not for the pilot**.
- **Starter web service (about $7/month at the time of writing) + 1 GB persistent disk (about $0.25/GB/month)**: stays awake and keeps the database. Use this from pilot start until judging ends, then you can delete it. Check Render's pricing page for current numbers before you pay.

## Step 1. Put the code on GitHub
```bash
cd classvoice
git init && git add . && git commit -m "ClassVoice NG"
# create an empty PRIVATE repo on github.com, then:
git remote add origin https://github.com/<you>/classvoice-ng.git
git branch -M main && git push -u origin main
```
Before pushing run `git status` and confirm `.env` and `data/*.db` are NOT listed (the `.gitignore` excludes them).

## Step 2. Create the Render service
1. render.com → sign up with GitHub → **New → Blueprint** → choose your repo. Render reads `render.yaml`.
2. Fill the prompted variables: `DASHBOARD_KEY` (a password for the dashboard), `GATEWAY_KEY` (the SAME secret you use in Colab). Leave the Twilio ones empty for now.
3. Confirm the Starter plan and the disk. Click **Apply**. Wait for "Live".
4. Note your URL, e.g. `https://muta.onrender.com`. Test: open `<URL>/healthz` (shows `{"ok":true}`) and `<URL>/` (the page loads; the chip says offline until Step 3).
5. Dashboard → your service → **Environment** → copy the generated value of **ADMIN_KEY**.

## Step 3. Connect the GPU notebook (Colab) to the hosted app
1. Colab → left sidebar key icon → add two more secrets (notebook access ON): `APP_URL` = your Render URL (no trailing slash), `ADMIN_KEY` = the value you copied.
2. Re-upload the updated `gateway/gateway.py` (it now contains the heartbeat) and run your usual cells:
   ```python
   import sys, importlib; sys.path.insert(0, "/content")
   import gateway; importlib.reload(gateway)
   gateway.start_in_notebook()
   ```
3. It prints `Heartbeat started: registering https://... with https://...onrender.com`. Within a minute, open `<URL>/health`: `gateway.ok` should be `true` and the site chip says **N-ATLAS online**.
4. From now on, **every Colab restart fixes itself**: the heartbeat re-registers the new tunnel URL every 60 seconds. You never edit Render's environment again for this.

Test the whole thing from your phone using the Render link (this is also your low-bandwidth mobile test, no tunnel needed).

## Step 4. Turn WhatsApp on (optional channel)
1. Render → Environment: `WHATSAPP_ENABLED=1`, `PUBLIC_BASE_URL=<your Render URL>`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+<sandbox number from your console>`. Save (it redeploys).
2. Twilio Console → WhatsApp Sandbox settings → "When a message comes in": `<Render URL>/whatsapp/webhook`, POST. Set once; it never changes again.
3. Send `hi` from your phone (after `join ...`). If silent, run the diagnostic with the same values in a local `.env`: `python -m scripts.check_whatsapp`.

## Step 5. Daily safety routine during the pilot
- Backup the database (also works if Render ever resets):
  ```bash
  curl -H "x-admin-key: <ADMIN_KEY>" https://<your-app>.onrender.com/admin/backup.sqlite -o backup-$(date +%F).sqlite
  ```
- Dashboard: `<URL>/dashboard?key=<DASHBOARD_KEY>`. Student question/answer text can only be exported with the admin key (header), never from the browser link.
- Keep the Colab tab open during student sessions.

## Step 6. What to give the judges
- **Link:** `https://<your-app>.onrender.com` (works on any phone, no install).
- **Quick-start text (put it in your submission):** "Open the link, tap 'I understand and agree', choose Nigerian English (or Hausa/Yoruba/Igbo), tap the microphone, ask one question such as 'What is the difference between stress and strain?', tap again, read the answer and rate it."
- **Note for judges:** "The N-ATLAS model runs on a separate GPU server. If the page says the AI server is resting, please see the demo video: <link>."
- **Dashboard link + key** only if you want them to see live aggregated numbers (no personal data in it).
- **Evidence pack:** the validation report, CSV, screenshots and the demo video (see `docs/WHATSAPP_AND_PILOT.md`, section 7).
- **WhatsApp:** judges can only use the Twilio sandbox after sending your join code, so present WhatsApp through your video and logs, and offer the join instructions as optional.

## Keeping the GPU alive during judging (decide one)
| Option | Notes |
|---|---|
| Keep Colab running yourself during the judging window | Free. Needs you online; Colab limits session length and does not guarantee GPUs. Ask the organizers when judging happens. |
| Ask NCAIR/ONDI for hosted N-ATLAS API access or compute | Most robust if available. If they give you an endpoint, point `GATEWAY_URL` to it (the API shape may differ; send me their docs and I will adapt `natlas_client.py`). |
| Paid always-on GPU host | Works but costs money; prices vary, check before committing. |
| Fallback | The offline page + demo video + evidence pack, so the submission still stands if the GPU is down. |
