import json
import runpy
import shutil
import sys
from datetime import datetime, timezone

from app.config import BASE_DIR, Config
from app import db, course_memory

db.init(Config.DB_PATH)
stats = db.stats()
if stats["total_interactions"] == 0 and "--force" not in sys.argv:
    print("This database has 0 interactions, so there is nothing real to publish yet.\n"
          "Run the pilot first (or add --force if you really want an empty snapshot).")
    sys.exit(1)

ev_path = BASE_DIR / "eval" / "report.json"
ev = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else None

out = BASE_DIR / "evidence"
out.mkdir(exist_ok=True)
snapshot = {
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "database": str(Config.DB_PATH),
    "stats": stats,
    "course_memory": course_memory.stats(),
    "eval": ev,
}
(out / "snapshot.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
(out / "validation.csv").write_text(db.export_csv(include_text=False), encoding="utf-8")

runpy.run_module("scripts.make_report", run_name="__main__")      # also keep a readable text report
shutil.copy(BASE_DIR / "eval" / "VALIDATION_REPORT.md", out / "VALIDATION_REPORT.md")

print(f"\nSnapshot of {stats['total_interactions']} interactions from {stats['participants']} participants saved to {out}.")
print("Next: git add evidence && git commit -m 'pilot evidence' && git push")