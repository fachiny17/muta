"""Fast, dependency-free checks for the Muta frontend contract."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []


def require(condition, message):
    if not condition:
        errors.append(message)


def read(relative):
    path = ROOT / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Could not read {relative}: {exc}")
        return ""

index = read("templates/index.html")
tutor = read("static/js/tutor.js")
css = read("static/css/style.css")
legacy_css = read("static/css/nexlearn.css")
theme_js = read("static/js/theme.js")
dashboard_js = read("static/js/dashboard.js")
dashboard = read("templates/dashboard.html")
evidence = read("templates/evidence.html")
login = read("templates/login.html")
metrics = read("templates/_metrics.html")

required_ids = [
    "gw", "offline", "consent", "agree", "tutor", "lang", "mode", "mic", "status",
    "recording-status-bar", "recording-status-label", "recording-duration", "out",
    "transcription-text", "word-count", "answer-title", "answer", "copy", "dl-transcript",
    "dl-answer", "fb", "stars", "task", "fb-submit", "fbmsg", "fb-done", "toast-root",
    "theme-toggle",
]
for element_id in required_ids:
    require(re.search(rf'\bid=["\']{re.escape(element_id)}["\']', index) is not None,
            f"index.html is missing required ID: {element_id}")

for marker in ('data-m="question"', 'data-m="summary"', 'data-r="1"', 'data-r="5"', 'data-t="1"', 'data-t="0"'):
    require(marker in index, f"index.html is missing {marker}")
for token in ('"cv_consent"', '"1"', 'AUDIO_BITRATE = 24000', 'channelCount: 1',
              'echoCancellation: true', 'noiseSuppression: true', '"/health"', '"/api/ask"',
              '"/api/feedback"', 'interaction_id:',  'payload.task_completed'):
    require(token in tutor, f"tutor.js is missing contract token: {token}")

required_texts = {
    "templates/index.html": (index, "Survey successfully saved! Thank you.", "Team login", "Pilot evidence"),
    "templates/dashboard.html": (dashboard + metrics, "Participants", "n/a", "Log out", "Home", "match this snapshot exactly", "differ from it"),
    "templates/evidence.html": (evidence, "Results from a real pilot", "will be published here", "validation.csv"),
}
for filename, (source, *needles) in required_texts.items():
    for needle in needles:
        require(needle in source, f"{filename} is missing required text: {needle}")
require('id="fb-done"' in index, 'index.html is missing id="fb-done"')
require("{% from \"_metrics.html\" import metrics %}" in dashboard, "dashboard metrics import changed")
require("{% from \"_metrics.html\" import metrics, pct, num %}" in evidence, "evidence metrics import changed")
require("{% macro metrics(s, langs) %}" in metrics, "metrics macro signature changed")
require("{% macro pct(v) %}" in metrics, "pct macro signature changed")
require("{% macro num(v, unit='') %}" in metrics, "num macro signature changed")
require('name="password"' in login and "url_for('web.login')" in login, "login form contract changed")
require("url_for('web.logout')" in dashboard, "logout endpoint reference changed")

for template_name in ("index.html", "dashboard.html", "evidence.html", "login.html"):
    source = read(f"templates/{template_name}")
    require("filename='css/style.css'" in source, f"{template_name} does not load the consolidated stylesheet")
    require("filename='css/nexlearn.css'" not in source, f"{template_name} still loads nexlearn.css")

for filename, source in (("templates/index.html", index), ("static/css/style.css", css), ("static/css/nexlearn.css", legacy_css)):
    for forbidden in ("googleapis", "dicebear", "socket.io"):
        require(forbidden not in source.lower(), f"{filename} contains forbidden dependency text: {forbidden}")
require("innerHTML" not in tutor, "tutor.js must not write model output through innerHTML")
require("addEventListener" in tutor and "onclick=" not in index.lower(), "unexpected inline event handler")
require("localStorage.setItem(\"muta_theme\"" in theme_js, "theme preference is not persisted")
require("sessionStorage.setItem(\"muta_auto\"" in dashboard_js, "dashboard refresh preference is not preserved")
require(len(css.encode("utf-8")) < 25 * 1024, "consolidated stylesheet exceeds 25 KiB")
require(len(tutor.encode("utf-8")) < 21 * 1024, "tutor.js exceeds 21 KiB")

if errors:
    print("Frontend contract check: FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("Frontend contract check: PASS")
print(f"Verified {len(required_ids)} required home-page IDs, template strings, Jinja macro signatures, API tokens, local-only assets, and size budgets.")
print(f"style.css: {len(css.encode('utf-8')):,} bytes; tutor.js: {len(tutor.encode('utf-8')):,} bytes.")
