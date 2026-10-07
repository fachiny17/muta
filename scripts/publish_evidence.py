"""Freeze the REAL pilot results into evidence/ so the free hosted site can show them without a database.
    python -m scripts.publish_evidence
Then: git add evidence && git commit -m "pilot evidence" && git push   (Render redeploys automatically)
Only metrics are exported (no question/answer text).
"""
import runpy
import shutil

from app.config import BASE_DIR, Config
from app import db

db.init(Config.DB_PATH)
runpy.run_module("scripts.make_report", run_name="__main__")
out = BASE_DIR / "evidence"
out.mkdir(exist_ok=True)
shutil.copy(BASE_DIR / "eval" / "VALIDATION_REPORT.md", out / "VALIDATION_REPORT.md")
(out / "validation.csv").write_text(db.export_csv(include_text=False), encoding="utf-8")
print(f"\nPublished snapshot to {out}. Commit and push it, then open /evidence on your site.")
