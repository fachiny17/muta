import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Languages the N-ATLAS ASR models cover. Whether each one actually works is
# determined at runtime by the gateway; failures are reported honestly.
LANGS = {"en": "Nigerian English", "ha": "Hausa", "yo": "Yoruba", "ig": "Igbo"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:9000").rstrip("/")
    GATEWAY_KEY = os.getenv("GATEWAY_KEY", "")
    DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "sauti.db"))
    ENABLED_LANGS = [c.strip() for c in os.getenv("ENABLED_LANGS", "en,ha,yo,ig").split(",")
                     if c.strip() in LANGS]
    MAX_AUDIO_S = int(os.getenv("MAX_AUDIO_S", "90"))
    MAX_SUMMARY_AUDIO_S = int(os.getenv("MAX_SUMMARY_AUDIO_S", "180"))
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    DASHBOARD_KEY = os.getenv("DASHBOARD_KEY", "")

    ADMIN_KEY = os.getenv("ADMIN_KEY", "")
    DEMO_VIDEO_URL = os.getenv("DEMO_VIDEO_URL", "")
    RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "30"))
    WHATSAPP_VERIFY_SIGNATURE = os.getenv("WHATSAPP_VERIFY_SIGNATURE", "1") == "1"
    WHATSAPP_ACK = os.getenv("WHATSAPP_ACK", "1") == "1"
    WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "0") == "1"
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
