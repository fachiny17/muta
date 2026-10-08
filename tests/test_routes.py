import io
import pytest
from tests.conftest import make_wav


def ask(client, wav, **over):
    data = {"language": "en", "consent": "1", **over}
    with open(wav, "rb") as f:
        data["audio"] = (io.BytesIO(f.read()), "recording.wav", "audio/wav")
    return client.post("/api/ask", data=data, content_type="multipart/form-data")


def test_index_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").get_json()["gateway"]["ok"] is True


def test_requires_consent_and_valid_language(client, wav):
    assert ask(client, wav, consent="0").status_code == 400
    assert ask(client, wav, language="fr").status_code == 400


def test_full_web_flow(client, wav):
    r = ask(client, wav)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["transcript"] and d["answer"]
    assert "cv_uid=USR_" in r.headers.get("Set-Cookie", "")
    fb = client.post("/api/feedback", json={"interaction_id": d["interaction_id"], "rating": 5, "task_completed": True})
    assert fb.status_code == 200
    s = client.get("/api/stats?key=k").get_json()
    assert s["total_interactions"] == 1 and s["participants"] == 1 and s["avg_rating"] == 5
    assert s["by_channel"] == {"web": 1} and s["by_language"] == {"en": 1}


def test_feedback_rejects_bad_input_and_other_users(client, app, wav):
    d = ask(client, wav).get_json()
    assert client.post("/api/feedback", json={"interaction_id": d["interaction_id"], "rating": 9}).status_code == 400
    other = app.test_client()
    ask(other, wav)  # gets its own cookie
    assert other.post("/api/feedback", json={"interaction_id": d["interaction_id"], "rating": 1}).status_code == 404


def test_dashboard_and_export_are_protected_and_anonymous(client, wav):
    ask(client, wav)
    r = client.get("/dashboard")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")   # browsers are sent to the login page
    assert client.get("/export.csv").status_code == 403
    page = client.get("/dashboard?key=k")
    assert page.status_code == 200 and b"Participants" in page.data
    csv_plain = client.get("/export.csv?key=k").get_data(as_text=True)
    assert "USR_" in csv_plain and "what is strain" not in csv_plain
    assert client.get("/export.csv?key=k&include_text=1").status_code == 403       # text needs the admin key
    client.application.config["ADMIN_KEY"] = "adm"
    full = client.get("/export.csv?key=k&include_text=1", headers={"x-admin-key": "adm"})
    assert "what is strain" in full.get_data(as_text=True)


def test_empty_dashboard_shows_na_not_fake_numbers(client):
    html = client.get("/dashboard?key=k").get_data(as_text=True)
    assert "n/a" in html


def test_summary_mode_uses_summary_prompt(client, wav, fake_gateway):
    d = ask(client, wav, mode="summary").get_json()
    assert d["ok"]
    assert "Summarize the lesson" in fake_gateway["chat"][-1][0]["content"]
    assert ask(client, wav, mode="bogus").status_code == 400


def test_static_assets_have_no_external_dependencies(client):
    html = client.get("/").get_data(as_text=True)
    assert "googleapis" not in html and "dicebear" not in html and "socket.io" not in html
    css = client.get("/static/css/nexlearn.css").get_data(as_text=True)
    assert "googleapis" not in css and "Orbitron" not in css


def test_gateway_registration_is_protected_and_persisted(tmp_path, fake_gateway):
    from app import create_app, natlas_client
    cfg = {"DB_PATH": str(tmp_path / "g.db"), "TESTING": True, "ADMIN_KEY": "adm", "GATEWAY_KEY": "gk"}
    app = create_app(cfg)
    c = app.test_client()
    assert c.post("/internal/gateway", json={"url": "https://a.example"}).status_code == 404
    assert c.post("/internal/gateway", json={"url": "http://bad"}, headers={"x-admin-key": "adm"}).status_code == 400
    assert c.post("/internal/gateway", json={"url": "https://a.example/"}, headers={"x-admin-key": "adm"}).status_code == 200
    assert natlas_client._cfg["url"] == "https://a.example"
    create_app(cfg)  # simulated restart: URL comes back from the database
    assert natlas_client._cfg["url"] == "https://a.example"


def test_healthz_and_backup(client, app):
    assert client.get("/healthz").get_json()["ok"] is True
    assert client.get("/admin/backup.sqlite").status_code == 404      # ADMIN_KEY not set in this fixture
    app.config["ADMIN_KEY"] = "adm"
    r = client.get("/admin/backup.sqlite", headers={"x-admin-key": "adm"})
    assert r.status_code == 200 and r.data[:6] == b"SQLite"


def test_ffmpeg_fallback_to_bundled_binary(monkeypatch, tmp_path):
    from app import audio
    from tests.conftest import make_wav
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    assert audio._ffmpeg() and "imageio" in audio._ffmpeg().lower() or audio._ffmpeg()
    out = audio.to_wav(make_wav(tmp_path / "x.wav", 1), str(tmp_path))
    assert audio.duration_s(out) > 0.9


def test_evidence_page_placeholder_and_snapshot(client, monkeypatch, tmp_path):
    from app import routes
    assert b"will be published here" in client.get("/evidence").data
    assert client.get("/evidence/validation.csv").status_code == 404
    (tmp_path / "VALIDATION_REPORT.md").write_text("# Report\n- Documented interactions: 7")
    (tmp_path / "validation.csv").write_text("id\n1\n")
    monkeypatch.setattr(routes, "EVIDENCE_DIR", tmp_path)
    page = client.get("/evidence").get_data(as_text=True)
    assert "Documented interactions: 7" in page and "validation.csv" in page
    assert client.get("/evidence/validation.csv").status_code == 200


@pytest.fixture(autouse=True)
def _isolate_tests(tmp_path, monkeypatch):
    """Runs before EVERY test in this file, so results never depend on your own project's state."""
    from app import routes
    routes._login_attempts.clear()                        # the failed-login counter starts empty each time
    empty = tmp_path / "no_evidence"
    empty.mkdir()
    monkeypatch.setattr(routes, "EVIDENCE_DIR", empty)    # ignore any real evidence/ folder in your project


def test_team_login_flow(client, wav):
    ask(client, wav)
    assert client.get("/login").status_code == 200
    assert client.post("/login", data={"password": "wrong"}).status_code == 401
    r = client.post("/login", data={"password": "k"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    page = client.get("/dashboard")                       # no ?key= needed any more: the session cookie is enough
    assert page.status_code == 200 and b"Log out" in page.data and b"Home" in page.data
    assert client.get("/api/stats").status_code == 200
    assert client.get("/export.csv?include_text=1").status_code == 200     # text export is allowed for a logged-in team member
    assert client.get("/admin/backup.sqlite").status_code == 200
    client.post("/logout")
    assert client.get("/dashboard").status_code == 302                    # logged out again


def test_login_is_rate_limited(client):
    for _ in range(5):
        assert client.post("/login", data={"password": "nope"}).status_code == 401
    assert client.post("/login", data={"password": "k"}).status_code == 429   # even the right password waits


def test_students_cannot_reach_team_pages(client):
    assert client.get("/api/stats").status_code == 403
    assert client.get("/admin/backup.sqlite").status_code == 404
    assert client.get("/export.csv").status_code == 403


def test_homepage_links_and_evidence_link_visibility(client, monkeypatch, tmp_path):
    from app import routes
    home = client.get("/").get_data(as_text=True)
    assert "Team login" in home and "Pilot evidence" not in home          # hidden until evidence exists
    (tmp_path / "VALIDATION_REPORT.md").write_text("# r")
    monkeypatch.setattr(routes, "EVIDENCE_DIR", tmp_path)
    assert "Pilot evidence" in client.get("/").get_data(as_text=True)
    client.post("/login", data={"password": "k"})
    assert ">Dashboard<" in client.get("/").get_data(as_text=True)


def test_survey_markup_present(client):
    html = client.get("/").get_data(as_text=True)
    assert "Survey successfully saved! Thank you." in html and 'id="fb-done"' in html