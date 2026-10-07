"""Diagnose why WhatsApp is silent.  Usage:  python -m scripts.check_whatsapp
Prints which setting is wrong. Secrets are never printed.
"""
import httpx

from app.config import Config as C


def line(ok, msg):
    print(("PASS  " if ok else "FAIL  ") + msg)
    return ok


def main():
    line(C.WHATSAPP_ENABLED, "WHATSAPP_ENABLED=1 (otherwise the webhook returns 404)")
    line(bool(C.TWILIO_ACCOUNT_SID.startswith("AC")), "TWILIO_ACCOUNT_SID is set and starts with AC")
    line(bool(C.TWILIO_AUTH_TOKEN), "TWILIO_AUTH_TOKEN is set")
    line(C.TWILIO_WHATSAPP_FROM.startswith("whatsapp:+"), f"TWILIO_WHATSAPP_FROM looks right ({C.TWILIO_WHATSAPP_FROM or 'empty'})")
    base = C.PUBLIC_BASE_URL
    line(base.startswith("https://") and not base.endswith("/"), f"PUBLIC_BASE_URL is https with no trailing slash ({base or 'empty'})")
    if C.TWILIO_ACCOUNT_SID and C.TWILIO_AUTH_TOKEN:
        try:
            r = httpx.get(f"https://api.twilio.com/2010-04-01/Accounts/{C.TWILIO_ACCOUNT_SID}.json",
                          auth=(C.TWILIO_ACCOUNT_SID, C.TWILIO_AUTH_TOKEN), timeout=15)
            line(r.status_code == 200, f"Twilio accepts your SID/token (HTTP {r.status_code})")
        except Exception as e:
            line(False, f"could not reach Twilio: {e}")
    if base:
        try:
            r = httpx.get(base + "/healthz", timeout=20)
            line(r.status_code == 200, f"public URL reaches your app: {base}/healthz (HTTP {r.status_code})")
            r = httpx.post(base + "/whatsapp/webhook", data={"From": "x"}, timeout=20)
            expect = {403: "route is live and the signature check is working (good)",
                      404: "route not found: WHATSAPP_ENABLED is not 1 on the running app, or the app was not restarted",
                      503: "signature check is on but TWILIO_AUTH_TOKEN or PUBLIC_BASE_URL is missing on the running app"}
            line(r.status_code == 403, f"unsigned webhook test -> HTTP {r.status_code}: {expect.get(r.status_code, 'unexpected')}")
        except Exception as e:
            line(False, f"public URL not reachable ({e}). Tunnel stopped or URL changed?")
    print("\nThen check Twilio Console -> Monitor -> Logs -> Messaging, and make sure the sandbox webhook URL is exactly "
          f"{base or '<PUBLIC_BASE_URL>'}/whatsapp/webhook (POST), and that your phone has sent the 'join ...' message.")


if __name__ == "__main__":
    main()
