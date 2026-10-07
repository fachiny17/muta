import pytest
from app import db, natlas_client, pipeline
from app.natlas_client import GatewayError
from tests.conftest import make_wav


@pytest.fixture(autouse=True)
def _db(tmp_path):
    db.init(str(tmp_path / "p.db"))


def rows():
    return db.export_csv().strip().splitlines()


def test_success_path_logs_everything(wav, fake_gateway):
    r = pipeline.handle_voice(wav, "en", "USR_AAAAAAAA", "web", 1234)
    assert r["ok"] and r["transcript"] == "what is strain" and "Strain" in r["answer"]
    assert fake_gateway["asr"] == ["en"]
    sys_msg = fake_gateway["chat"][0][0]["content"]
    assert "Nigerian English" in sys_msg
    s = db.stats()
    assert s["total_interactions"] == 1 and s["asr_success_rate"] == 100.0 and s["llm_success_rate"] == 100.0


def test_asr_failure_is_graceful_and_logged(wav, monkeypatch):
    def boom(p, lang): raise GatewayError("down")
    monkeypatch.setattr(natlas_client, "asr", boom)
    r = pipeline.handle_voice(wav, "ha", "USR_AAAAAAAA", "web")
    assert not r["ok"] and r["message"] == pipeline.MSG_ASR
    s = db.stats()
    assert s["asr_success_rate"] == 0.0 and s["failed"] == 1


def test_empty_transcript(wav, monkeypatch):
    monkeypatch.setattr(natlas_client, "asr", lambda p, l: "   ")
    r = pipeline.handle_voice(wav, "yo", "USR_AAAAAAAA", "web")
    assert not r["ok"] and r["error"] == "empty_transcript" and r["message"] == pipeline.MSG_EMPTY


def test_llm_failure_keeps_transcript(wav, monkeypatch, fake_gateway):
    def boom(m, **k): raise GatewayError("llm down")
    monkeypatch.setattr(natlas_client, "chat", boom)
    r = pipeline.handle_voice(wav, "ig", "USR_AAAAAAAA", "web")
    assert not r["ok"] and r["transcript"] == "what is strain" and r["message"] == pipeline.MSG_LLM
    s = db.stats()
    assert s["asr_success_rate"] == 100.0 and s["llm_success_rate"] == 0.0


def test_bad_audio(tmp_path, fake_gateway):
    junk = tmp_path / "x.webm"; junk.write_bytes(b"not audio")
    r = pipeline.handle_voice(str(junk), "en", "USR_AAAAAAAA", "web")
    assert not r["ok"] and r["message"] == pipeline.MSG_AUDIO


def test_too_long(tmp_path, fake_gateway, monkeypatch):
    monkeypatch.setitem(pipeline.SETTINGS, "max_audio_s", 3)
    r = pipeline.handle_voice(make_wav(tmp_path / "l.wav", 5), "en", "USR_AAAAAAAA", "web")
    assert r["error"] == "audio_too_long"


def test_long_audio_is_chunked(tmp_path, fake_gateway, monkeypatch):
    monkeypatch.setitem(pipeline.SETTINGS, "max_audio_s", 120)
    clip = make_wav(tmp_path / "long.wav", 70, gaps=[(27, 27.5), (55, 55.5)])
    r = pipeline.handle_voice(clip, "en", "USR_AAAAAAAA", "web")
    assert r["ok"] and len(fake_gateway["asr"]) == 3  # 70 s -> 3 chunks of <= 28 s


def test_feedback_ownership(wav, fake_gateway):
    r = pipeline.handle_voice(wav, "en", "USR_AAAAAAAA", "web")
    assert not pipeline.record_feedback(r["interaction_id"], "USR_BBBBBBBB", 5)
    assert pipeline.record_feedback(r["interaction_id"], "USR_AAAAAAAA", 4, True)
    s = db.stats()
    assert s["avg_rating"] == 4 and s["task_completion_rate"] == 100.0
    with pytest.raises(ValueError):
        pipeline.record_feedback(r["interaction_id"], "USR_AAAAAAAA", 9)
