"""Generate eval/VALIDATION_REPORT.md from REAL data only (database + eval/report.json).
    python -m scripts.make_report
Nothing is estimated. Missing data is printed as 'not measured'.
"""
import json
from datetime import datetime, timezone

from app.config import BASE_DIR, Config, LANGS
from app import db

db.init(Config.DB_PATH)
s = db.stats()
ev_path = BASE_DIR / "eval" / "report.json"
ev = json.loads(ev_path.read_text()) if ev_path.exists() else None


def f(v, unit=""):
    return "not measured" if v is None else f"{v}{unit}"


n, users = s["total_interactions"], s["participants"]
ok_n = round(n * (s["llm_success_rate"] or 0) / 100) if n else 0
lines = [
    "# Muta: Validation Report",
    f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from the application database.",
    "",
    "## PS2 evidence",
    f"- Documented interactions: **{n}** (target: 50+) -> {'MET' if n >= 50 else 'NOT YET MET'}",
    f"- Distinct anonymous participants: **{users}**",
    f"- Interactions that produced an answer: {ok_n}",
    f"- Failed interactions: {s['failed']}",
    "",
    "## Usage",
    "| Channel | Interactions |", "|---|---|",
    *[f"| {c} | {s['by_channel'].get(c, 0)} |" for c in ("web", "whatsapp")],
    "",
    "| Language | Interactions |", "|---|---|",
    *[f"| {LANGS[c]} | {s['by_language'].get(c, 0)} |" for c in LANGS],
    "",
    "## Quality and performance (measured)",
    f"- ASR success rate: {f(s['asr_success_rate'], '%')}",
    f"- LLM success rate: {f(s['llm_success_rate'], '%')}",
    f"- Average user rating: {f(s['avg_rating'], '/5')} (from {s['rated_count']} ratings)",
    f"- Task completion: {f(s['task_completion_rate'], '%')} (from {s['task_answered_count']} responses)",
    f"- Latency: average {f(s['avg_latency_ms'], ' ms')}, median {f(s['median_latency_ms'], ' ms')}",
    f"- Average ASR time {f(s['avg_asr_ms'], ' ms')}; average LLM time {f(s['avg_llm_ms'], ' ms')}",
    f"- Average audio upload size: {f(s['avg_audio_kb'], ' KB')}",
    "",
    "## ASR accuracy (word error rate on manually verified clips)",
]
if ev and ev.get("clips"):
    lines += [f"- Clips evaluated: {ev['clips']}; overall WER: {f(ev['overall_wer'])}"]
    lines += [f"- {LANGS.get(k, k)}: WER {v['wer']} on {v['clips']} clips, average ASR {v['avg_asr_ms']} ms"
              for k, v in ev["by_language"].items()]
else:
    lines += ["- Not measured yet. Run `python -m scripts.evaluate_asr` after adding clips to eval/clips/."]
lines += ["", "## Notes", "- Anonymous IDs only; no names, phone numbers or emails are stored.",
          "- Success rates count technical success of each stage, not answer correctness. Correctness is reflected only in user ratings.",
          "- Small samples: treat percentages with caution."]
out = BASE_DIR / "eval" / "VALIDATION_REPORT.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {out}\n"); print("\n".join(lines[:12]))
