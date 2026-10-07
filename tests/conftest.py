import math
import struct
import wave

import pytest

from app import create_app, natlas_client


def make_wav(path, seconds=2.0, sr=16000, gaps=()):
    """Sine-wave test clip. gaps = [(start_s, end_s)] of digital silence."""
    n = int(seconds * sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            silent = any(a <= t < b for a, b in gaps)
            frames += struct.pack("<h", 0 if silent else int(8000 * math.sin(2 * math.pi * 220 * t)))
        w.writeframes(bytes(frames))
    return str(path)


@pytest.fixture
def wav(tmp_path):
    return make_wav(tmp_path / "clip.wav")


@pytest.fixture
def fake_gateway(monkeypatch):
    calls = {"asr": [], "chat": []}
    monkeypatch.setattr(natlas_client, "asr", lambda p, lang: (calls["asr"].append(lang), "what is strain")[1])
    monkeypatch.setattr(natlas_client, "chat", lambda m, **k: (calls["chat"].append(m), "Strain is deformation per unit length.")[1])
    monkeypatch.setattr(natlas_client, "health", lambda: {"ok": True})
    return calls


@pytest.fixture
def app(tmp_path, fake_gateway):
    return create_app({"DB_PATH": str(tmp_path / "t.db"), "TESTING": True, "DASHBOARD_KEY": "k", "WHATSAPP_ENABLED": False})


@pytest.fixture
def client(app):
    return app.test_client()
