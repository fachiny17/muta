# Muta architecture

```
 Student phone / laptop
   |  Web: browser mic (static/js/tutor.js)       WhatsApp voice note (optional, Twilio)
   v                                              v
 Flask app (app/routes.py)                     app/whatsapp.py  (only loaded if WHATSAPP_ENABLED=1)
   \____________________  shared pipeline  ______________________/
                    app/pipeline.py  handle_voice()
                    audio.py -> ffmpeg 16 kHz mono, chunks <= 28 s
                                |  HTTPS + x-api-key
                      N-ATLAS GATEWAY  (gateway/gateway.py on a Colab/Kaggle GPU)
                      /v1/asr  -> N-ATLAS ASR (Hausa, Yoruba, Igbo, Nigerian English)
                      /v1/chat -> N-ATLAS LLM (NCAIR1/N-ATLaS, 4-bit)
                                |
                  answer -> student -> rating / task feedback
                                |
                 SQLite (data/sauti.db): users, interactions, wa_seen
                                |
                 /dashboard, /export.csv, scripts/make_report.py
```

## Where N-ATLAS is used
| Stage | Component | Code |
|---|---|---|
| Speech to text | N-ATLAS ASR, one model per language | `gateway.py:/v1/asr`, called by `pipeline.transcribe()` |
| Academic answer / lesson summary | N-ATLAS LLM | `gateway.py:/v1/chat`, called by `pipeline.answer_question()` / `summarize_text()` |
No other ASR or LLM service is called anywhere. The Flask app never loads the models.

## Design decisions
- One pipeline, two channels: `handle_voice(audio, lang, user, channel)` is the only place academic logic lives.
- Explicit language selection (no auto-detect) for reliability.
- Every attempt is logged, including failures, so success rates are honest.
- Privacy: anonymous IDs, salted hash for WhatsApp numbers, recordings deleted after processing.
