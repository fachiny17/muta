import base64
import hashlib
import hmac

import pytest

from app import create_app, db, whatsapp
from tests.conftest import make_wav

BASE = "https://example.test"
TOKEN = "tok"


@pytest.fixture
def wa(tmp_path, fake_gateway, monkeypatch):
    app = create_app({"DB_PATH": str(tmp_path / "w.db"), "TESTING": True, "WHATSAPP_ENABLED": True,
                      "TWILIO_AUTH_TOKEN": TOKEN, "TWILIO_ACCOUNT_SID": "AC1", "TWILIO_WHATSAPP_FROM": "whatsapp:+1",
                      "PUBLIC_BASE_URL": BASE, "SECRET_KEY": "salt", "DASHBOARD_KEY": "k", "RATE_LIMIT_PER_HOUR": 5})
    sent = []
    monkeypatch.setattr(whatsapp, "RUN_ASYNC", False)
    monkeypatch.setattr(whatsapp, "send_message", lambda cfg, to, body: sent.append((to, body)))
    wav = make_wav(tmp_path / "v.wav", 2)

    class Resp:
        content = open(wav, "rb").read()
        def raise_for_status(self): pass
    monkeypatch.setattr(whatsapp.httpx, "get", lambda *a, **k: Resp())
    return app.test_client(), sent


def post(client, n=[0], **p):
    n[0] += 1
    params = {"From": "whatsapp:+2348000000001", "MessageSid": f"SM{n[0]}", **p}
    url = BASE + "/whatsapp/webhook"
    sig = base64.b64encode(hmac.new(TOKEN.encode(), (url + "".join(k + params[k] for k in sorted(params))).encode(),
                                    hashlib.sha1).digest()).decode()
    return client.post("/whatsapp/webhook", data=params, headers={"X-Twilio-Signature": sig})


def voice(client, **kw):
    return post(client, Body="", NumMedia="1", MediaContentType0="audio/ogg", MediaUrl0="https://m/1", **kw)


def test_rejects_bad_signature(wa):
    client, _ = wa
    assert client.post("/whatsapp/webhook", data={"From": "x", "Body": "hi"}).status_code == 403


def test_full_conversation(wa):
    client, sent = wa
    assert post(client, Body="hi").status_code == 200
    assert "Reply with a number" in sent[-1][1]
    post(client, Body="2")                                 
    assert "Hausa" in sent[-1][1]
    voice(client)
    assert any("Strain is deformation" in b for _, b in sent)
    post(client, Body="5")
    assert "YES or NO" in sent[-1][1]
    post(client, Body="yes")
    s = db.stats()
    assert s["by_channel"] == {"whatsapp": 1} and s["by_language"] == {"ha": 1}
    assert s["avg_rating"] == 5 and s["task_completion_rate"] == 100.0


def test_phone_number_is_never_stored(wa, tmp_path):
    client, _ = wa
    post(client, Body="1"); post(client, Body="1"); voice(client)
    raw = open(tmp_path / "w.db", "rb").read()
    assert b"2348000000001" not in raw


def test_duplicate_webhook_is_ignored(wa):
    client, sent = wa
    post(client, Body="hi")
    n = len(sent)
    params = {"From": "whatsapp:+2348000000001", "MessageSid": "SMDUP", "Body": "hi"}
    for _ in range(2):
        url = BASE + "/whatsapp/webhook"
        sig = base64.b64encode(hmac.new(TOKEN.encode(), (url + "".join(k + params[k] for k in sorted(params))).encode(),
                                        hashlib.sha1).digest()).decode()
        client.post("/whatsapp/webhook", data=params, headers={"X-Twilio-Signature": sig})
    assert len(sent) == n + 1


def test_voice_before_language_gets_menu(wa):
    client, sent = wa
    voice(client)
    assert "Reply with a number" in sent[-1][1] and db.stats()["total_interactions"] == 0


def test_language_change_and_rate_limit(wa):
    client, sent = wa
    post(client, Body="1"); post(client, Body="1")           # welcome, then English
    post(client, Body="language")
    assert "Reply with a number" in sent[-1][1]
    post(client, Body="3")
    assert "Yoruba" in sent[-1][1]
    for _ in range(5):
        voice(client)
    voice(client)
    assert "hourly limit" in sent[-1][1] and db.stats()["total_interactions"] == 5


def test_web_app_works_without_whatsapp(tmp_path, fake_gateway):
    app = create_app({"DB_PATH": str(tmp_path / "n.db"), "TESTING": True, "WHATSAPP_ENABLED": False})
    assert app.test_client().post("/whatsapp/webhook").status_code == 404
