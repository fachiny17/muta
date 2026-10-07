# $0 plan: free hosting for Muta

## First, a correction to the idea of "hosting instead of the GPU"
Hosting does **not** replace the GPU. The web app (Flask) is small and can live on a free host. N-ATLAS is an 8-billion-parameter model plus four speech models; no free web host runs that at usable speed, so the model server still runs on Colab or Kaggle (free GPU), or on a hosted API if the organizers give you one. What hosting fixes is the *link*: judges get a stable URL instead of your laptop.

## Free platforms compared (checked October 2026; plans change, re-check before relying on them)
| Platform | Card needed | What happens | Verdict for you |
|---|---|---|---|
| **Render Free** | No | Sleeps after 15 min without traffic (about 1 min to wake). Local files, including SQLite, are lost on restart, redeploy or sleep. May restart at any time. | **Use for the judge demo**, not for storing pilot data |
| Hugging Face Spaces | No | Current docs say Docker/Gradio Spaces need a paid plan to create (free: static only), and disk is not persistent. Older tutorials saying otherwise are outdated. | Not usable for Flask now |
| PythonAnywhere Free | No | Persistent disk, always-on single app. But outbound internet is limited to an allowlist (ngrok-free domains appear on it; Cloudflare quick tunnels did not appear in the part I saw) and CPU is capped at about 100 CPU-seconds/day. | Possible backup, untested and risky |
| Koyeb Free | Yes (reported $29 hold) | Does not sleep | Only if you have a card |
| Google Cloud Run | Yes | Scale-to-zero, no persistent disk | Only if you have a card |
| Railway | No | $5 trial then about $1/month credit | Will run out |
| Fly.io | Yes | No free tier for new users | No |
| Vercel | No | Serverless only; poor fit for Flask audio processing | No |

## Recommended $0 setup
**Two roles, two places:**
1. **Pilot data lives on your laptop** (SQLite in `data/` persists). Run `python run.py` + a Cloudflare tunnel and send students that link, and point the Twilio webhook at it, exactly as in the WhatsApp guide. Do not change `SECRET_KEY` during the pilot.
2. **Judges use Render Free.** It runs the same app against the same Colab GPU. Data created there is demo-only (it resets), and that is fine.
3. **Evidence is published as files, not as a live database.** After the pilot:
   ```bash
   python -m scripts.publish_evidence      # builds the report + metrics-only CSV from your REAL database
   git add evidence && git commit -m "pilot evidence" && git push
   ```
   Render redeploys and your site shows the results at `/evidence` (with a CSV download). Nothing is made up: it is a frozen copy of what your database recorded.

## Deploy on Render Free (about 15 minutes, no card)
1. Push the project to GitHub (private repo is fine; `.env` and `data/*.db` are git-ignored).
2. render.com → sign up with GitHub → **New → Blueprint** → select the repo. `render.yaml` is already set to the free plan.
3. Provide `DASHBOARD_KEY` and `GATEWAY_KEY` (same secret as Colab). Apply. When live, open `<URL>/healthz`.
4. In Render → Environment copy the generated `ADMIN_KEY`.
5. Colab secrets: add `APP_URL` (your Render URL) and `ADMIN_KEY`. Run the gateway cells; you should see "Heartbeat started". Open `<URL>/health` to confirm `gateway.ok`.
6. After any Render restart the registered URL is lost, but the notebook re-registers it within about a minute. Until then the page shows the friendly "server resting" notice.
7. Optional keep-awake: add a free uptime monitor (for example UptimeRobot) that requests `<URL>/healthz` every few minutes. This is not guaranteed because Render may restart free services at any time, and one always-on free service uses most of the 750 free hours, so run only one.

## Reducing the GPU stress
- **Two free GPU hosts, one code:** Colab and Kaggle both run `gateway.py`. If one runs out of quota or disconnects, start the other; the heartbeat re-registers the new URL automatically. Only run one at a time.
- **Judging window:** ask the organizers when judging happens and keep the notebook running then. Send a judge test message yourself 10 minutes before.
- **Ask NCAIR/ONDI** for hosted API access or compute; if they provide an endpoint, send me its docs and I will adapt `natlas_client.py`.
- **Fallback that still scores:** the offline page links your demo video (`DEMO_VIDEO_URL`), and `/evidence` still works with no GPU at all.

## What to write in the submission
- Judge link: your Render URL. Say "the AI model runs on a separate GPU server; if the page says it is resting, see the demo video".
- Evidence link: `<URL>/evidence`.
- Be honest that the hosted demo is a free instance (sleeps and resets), and that the pilot ran on a persistent instance.
