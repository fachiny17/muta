# Muta: WhatsApp, Pilot and Submission Guide

The web app already works. This guide adds the **optional** WhatsApp channel, then runs the pilot that produces your PS2 evidence, then packages the submission. If WhatsApp ever fails, the web app keeps working because `app/whatsapp.py` only loads when `WHATSAPP_ENABLED=1`.

Suggested schedule (deadline Oct 12): **Mon Oct 5** WhatsApp setup and own-phone test, **Tue Oct 6** soft test with 3 to 5 people, **Wed Oct 7 to Sat Oct 10** pilot, **Sun Oct 11** evidence, video and submit. Keep Oct 12 as buffer only.

---

## 1. What the WhatsApp channel does

```
Student voice note -> Twilio -> POST /whatsapp/webhook (Flask) -> returns empty reply at once
                                      |
                           background thread: download audio -> shared pipeline (N-ATLAS ASR -> LLM)
                                      |
                      answer sent back through Twilio -> student replies 1-5, then YES/NO -> SQLite
```
- First message: a language menu. Choosing a number = language + consent.
- Voice note: answered in that language. Reply `1` to `5` rates it, then `YES`/`NO` says whether it helped.
- `language` changes language. `help` shows instructions.
- Phone numbers are never stored, only a salted hash. **Do not change `SECRET_KEY` during the pilot**, or the same student becomes a "new participant".
- Safety built in: Twilio signature check, duplicate-webhook protection, 2 voice notes processed at once, 30 requests per user per hour.

Code: `app/whatsapp.py`, `app/db.py` (`mark_seen`, `count_recent`), `tests/test_whatsapp.py`. Run `python -m pytest -q` first; you should see all tests pass.

---

## 2. Twilio sandbox setup (20 min)

1. Create a free account at twilio.com and verify your email and phone.
2. Console home: copy your **Account SID** and **Auth Token**.
3. Go to **Messaging → Try it out → Send a WhatsApp message**. Note the **sandbox number** and your **join code** (looks like `join word-word`).
4. On your own WhatsApp, send `join word-word` to the sandbox number. You get a confirmation.
5. Twilio's sandbox is for testing: every participant must send the join message once, and sandbox memberships expire after a few days, so a student whose replies stop must send it again. Check the console for the current rules and message limits before pilot day. Each interaction can use 3 to 4 outbound messages; to save messages set `WHATSAPP_ACK=0` in `.env`.

## 3. Configure and run

**3.1 Edit `.env`:**
```
WHATSAPP_ENABLED=1
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886      # use the sandbox number shown in YOUR console
PUBLIC_BASE_URL=                                 # filled in at 3.3
SECRET_KEY=a-long-random-string-you-never-change
```

**3.2 Make the Flask app reachable.** Keep the Colab gateway running, then in VS Code terminals:
```bash
python run.py                                    # terminal 1
cloudflared tunnel --url http://localhost:5000   # terminal 2 -> prints https://xxxx.trycloudflare.com
```
(The phone-mic web test uses this same URL.)

**3.3 Set `PUBLIC_BASE_URL`** in `.env` to that exact URL with no trailing slash, then restart `python run.py`.

**3.4 Tell Twilio where to send messages.** Console → Messaging → Try it out → WhatsApp Sandbox settings:
- "When a message comes in": `https://xxxx.trycloudflare.com/whatsapp/webhook`, method **POST**. Save.

Every time the tunnel URL changes (tunnel restarted), repeat 3.3 and 3.4. A free ngrok static domain avoids this; check ngrok's current free-plan terms.

## 4. Test it yourself (10 min)

From your phone, to the sandbox number:
1. Send `hi` → you get the welcome and language menu.
2. Send `2` (or the number for the language you want) → "Language set to ...".
3. Record a voice note with one academic question → "Got it, working on your answer..." then the answer (usually within seconds to a minute; slower on the first request after Colab starts).
4. Reply `5` → asked YES or NO. Reply `YES`.
5. Check the data:
   ```bash
   sqlite3 data/sauti.db "select id,input_channel,language,asr_text,rating,task_completed,latency_ms,error from interactions order by id desc limit 5"
   ```
   and open `/dashboard?key=...`; the channel table should show **WhatsApp 1**.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| No reply at all | Check the Flask terminal. 403 = `PUBLIC_BASE_URL` does not exactly match the URL in Twilio (check https, no trailing slash, path `/whatsapp/webhook`). 404 = `WHATSAPP_ENABLED` is not `1`. |
| Reply says "could not read that recording" | Audio download or ffmpeg failed. Check `ffmpeg -version` and the Flask log. |
| "could not process your voice right now" | Gateway down or Colab URL changed: update `GATEWAY_URL`, restart `run.py`, run `python -m scripts.test_gateway`. |
| Replies stop after some days | Sandbox expired: send the `join ...` message again. |
| Twilio 63016 / 21211 errors in the log | The recipient has not joined the sandbox, or a number format is wrong. |
| Signature errors while debugging | Temporarily set `WHATSAPP_VERIFY_SIGNATURE=0`, find the mismatch, then set it back to `1`. |

---

## 6. Run the pilot (this is what wins PS2 points)

**Target:** 100+ logged interactions from 15+ different students (the requirement is 50+; the extra covers failures). Only real use counts: never add fake rows.

1. **Teacher (today):** ask for one class and 20 minutes. Explain it is voluntary and that no names or numbers are stored. For students under 18, get the teacher or school's approval and a parent notice, following the school's rules. Do not collect names in the process.
2. **Join session (day 1, 20 min, in person if possible):** students send the `join` code, pick a language, ask one practice question. Fix join problems on the spot.
3. **Student card** (translate it into Hausa, Yoruba and Igbo with a native speaker):
   > Muta: ask your school questions by voice.
   > 1) Open WhatsApp and message [sandbox number]. 2) Send: join [code]. 3) Choose your language. 4) Send a voice note with ONE question from today's class. 5) Rate the answer 1 to 5, then reply YES or NO.
   > Try: "What is the difference between stress and strain?", "Explain photosynthesis simply.", "What is a noun?"
4. **Daily homework prompt (days 2 to 4):** each student asks at least 3 questions from real homework. Three students x 5 questions already beats the target, so aim for 20 students x 5.
5. **Each evening (5 min):** open the dashboard. Check interactions, failures and ratings. Read the `error` column for patterns, fix real bugs, and keep notes.
6. **Before every session:** confirm Colab is running, run `python -m scripts.test_gateway test_ha.wav ha`, and confirm the tunnel URL and Twilio webhook match. Keep your laptop awake and charged.
7. **Back up the database** at the end of each day: `cp data/sauti.db backup-$(date +%F).db`.

Ask the web testers to use the web app the same way; the dashboard then shows both channels.

---

## 7. Evidence and submission pack (Sun Oct 11)

1. **ASR accuracy:** record 12+ short clips with native speakers, put them in `eval/clips/`, add `file,lang,reference` rows to `eval/refs.csv` (text typed by a human), then:
   ```bash
   python -m scripts.evaluate_asr
   ```
2. **Validation report (real numbers only):**
   ```bash
   python -m scripts.make_report        # writes eval/VALIDATION_REPORT.md
   ```
3. **Data export:** dashboard → "Anonymized CSV (metrics only)". Add the text version only if you have consent for it.
4. **Screenshots:** dashboard, a WhatsApp conversation (blur anything personal), the web app.
5. **Demo video (3 min):** problem in 20 s; WhatsApp voice note in Hausa or Yoruba -> transcript -> answer -> rating; web version; dashboard with real numbers; one sentence on where N-ATLAS ASR and LLM are used.
6. **Write-up:** use `README.md` and `docs/ARCHITECTURE.md`. Include honest limitations: manual language choice, per-language quality differences you measured, sandbox channel, small sample, Colab hosting. Judges trust measured numbers more than big claims.
7. **Repository hygiene:** `.env` is git-ignored. Make sure no token, Twilio credential or database with text is committed. Rotate the Deepgram/Gemini keys from NexLearn if they were ever public.

## 8. Daily checklist
- [ ] Colab cell running, gateway URL in `.env`
- [ ] `python run.py` and tunnel running; `PUBLIC_BASE_URL` and Twilio webhook match
- [ ] `test_gateway` passes
- [ ] Dashboard counts rising; failures understood
- [ ] Database backed up
