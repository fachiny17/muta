"""ASR evaluation on eval/refs.csv (columns: file,lang,reference) with clips in eval/clips/.

Reports real WER per language and overall, clip count, and ASR latency. Also summarises
pipeline latency from the interactions table. If there are no clips it says so; nothing is invented.
    python -m scripts.evaluate_asr
"""
import csv
import json
import re
import shutil
import sqlite3
import tempfile
import time
from collections import defaultdict

import jiwer

from app.config import BASE_DIR, Config
from app import audio, natlas_client

natlas_client.configure(Config.GATEWAY_URL, Config.GATEWAY_KEY)
CLIPS, REFS = BASE_DIR / "eval" / "clips", BASE_DIR / "eval" / "refs.csv"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()  # keeps diacritics


def transcribe(path: str, lang: str):
    work = tempfile.mkdtemp(prefix="ev_")
    try:
        wav = audio.to_wav(path, work)
        t0 = time.time()
        text = " ".join(natlas_client.asr(p, lang) for p in audio.chunk_wav(wav, work))
        return text, int((time.time() - t0) * 1000)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    rows = list(csv.DictReader(open(REFS, encoding="utf-8"))) if REFS.exists() else []
    rows = [r for r in rows if r.get("reference", "").strip() and (CLIPS / r["file"]).exists()]
    report = {"clips": len(rows), "by_language": {}, "overall_wer": None, "failures": []}
    refs, hyps, lat = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        try:
            text, ms = transcribe(str(CLIPS / r["file"]), r["lang"])
        except Exception as e:
            report["failures"].append({"file": r["file"], "error": str(e)[:200]})
            continue
        refs[r["lang"]].append(norm(r["reference"])); hyps[r["lang"]].append(norm(text)); lat[r["lang"]].append(ms)
    all_r, all_h = [], []
    for lang in refs:
        report["by_language"][lang] = {"clips": len(refs[lang]), "wer": round(jiwer.wer(refs[lang], hyps[lang]), 4),
                                       "avg_asr_ms": round(sum(lat[lang]) / len(lat[lang]))}
        all_r += refs[lang]; all_h += hyps[lang]
    if all_r:
        report["overall_wer"] = round(jiwer.wer(all_r, all_h), 4)
    try:
        c = sqlite3.connect(Config.DB_PATH)
        a = c.execute("SELECT AVG(asr_ms), AVG(llm_ms), AVG(latency_ms), COUNT(*) FROM interactions WHERE llm_success=1").fetchone()
        report["pipeline_latency_ms"] = {"asr": a[0], "llm": a[1], "total": a[2], "interactions": a[3]}
    except Exception:
        report["pipeline_latency_ms"] = None
    (BASE_DIR / "eval" / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not rows:
        print("\nNo evaluation clips found. Add clips to eval/clips/ and rows to eval/refs.csv first.")


if __name__ == "__main__":
    main()
