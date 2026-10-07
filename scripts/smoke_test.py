"""Quick end-to-end check of a RUNNING server (local or deployed).  Usage:
    python -m scripts.smoke_test http://localhost:5000
    python -m scripts.smoke_test https://your-app.onrender.com [clip.wav language]

With a clip and language it also sends a real voice question through the whole pipeline.
Without one it only checks the pages and the gateway link (safe to run any time).
"""
import sys
import time

import httpx


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000").rstrip("/")
    clip, lang = (sys.argv[2], sys.argv[3]) if len(sys.argv) >= 4 else (None, "en")
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail else ""))
        failures += 0 if ok else 1

    with httpx.Client(base_url=base, timeout=180, follow_redirects=True) as c:
        t = time.time()
        r = c.get("/healthz")  # on Render Free the first call can take about a minute (cold start)
        check("healthz", r.status_code == 200, f"{r.status_code}, {int((time.time()-t)*1000)} ms")
        r = c.get("/")
        check("home page loads", r.status_code == 200 and "Muta" in r.text)
        r = c.get("/static/js/tutor.js")
        check("static files are served", r.status_code == 200)
        g = c.get("/health").json().get("gateway", {})
        check("N-ATLAS gateway reachable from the app", bool(g.get("ok")), str(g)[:120])
        r = c.get("/evidence")
        check("evidence page loads", r.status_code == 200)
        if clip:
            with open(clip, "rb") as f:
                r = c.post("/api/ask", data={"language": lang, "consent": "1", "mode": "question"},
                           files={"audio": ("clip.wav", f.read(), "audio/wav")})
            d = r.json()
            check("voice question -> transcript -> answer", d.get("ok"), f"{d.get('latency_ms')} ms")
            print("      transcript:", (d.get("transcript") or "")[:100])
            print("      answer    :", (d.get("answer") or d.get("message") or "")[:160])
            if d.get("ok"):
                r = c.post("/api/feedback", json={"interaction_id": d["interaction_id"], "rating": 5, "task_completed": True})
                check("feedback saved", r.status_code == 200)
    print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
