"""Check the real gateway end to end.  Usage:
    python -m scripts.test_gateway [clip.wav lang]
"""
import sys
import time

from app.config import Config
from app import natlas_client as nc

nc.configure(Config.GATEWAY_URL, Config.GATEWAY_KEY)


def step(name, fn):
    t = time.time()
    try:
        out = fn()
        print(f"PASS {name} ({int((time.time()-t)*1000)} ms): {str(out)[:150]}")
        return True
    except Exception as e:
        print(f"FAIL {name}: {e}")
        return False


def main():
    ok = step("health", nc.health)
    ok &= step("chat", lambda: nc.chat([{"role": "user", "content": "What is the first law of thermodynamics? Answer in one sentence."}]))
    if len(sys.argv) == 3:
        ok &= step(f"asr[{sys.argv[2]}]", lambda: nc.asr(sys.argv[1], sys.argv[2]))
    else:
        print("SKIP asr (pass a 16 kHz mono wav and a language code to test it)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
