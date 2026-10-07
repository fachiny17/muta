"""Thin client for the N-ATLAS gateway (the GPU host that runs the real models).

The local app never loads N-ATLAS itself. Everything goes through these calls.
"""
import time
import httpx


class GatewayError(Exception):
    pass


_cfg = {"url": "http://127.0.0.1:9000", "key": ""}


def configure(url: str, key: str) -> None:
    _cfg.update(url=url.rstrip("/"), key=key)


def _request(method: str, path: str, retries: int = 2, timeout: float = 120, **kw) -> dict:
    last = None
    for attempt in range(retries + 1):
        try:
            r = httpx.request(method, _cfg["url"] + path, headers={"x-api-key": _cfg["key"]},
                              timeout=timeout, **kw)
            if r.status_code in (400, 401, 403, 422):  # our fault; retrying will not help
                raise GatewayError(f"gateway rejected request ({r.status_code}): {r.text[:200]}")
            r.raise_for_status()
            return r.json()
        except GatewayError:
            raise
        except Exception as e:  # network errors, 5xx, bad JSON
            last = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise GatewayError(f"gateway unreachable or failed: {last}")


def health() -> dict:
    return _request("GET", "/health", retries=0, timeout=10)


def asr(wav_path: str, lang: str) -> str:
    """Send a 16 kHz mono WAV (<= ~28 s) to N-ATLAS ASR and return the transcript."""
    with open(wav_path, "rb") as f:
        data = _request("POST", "/v1/asr", files={"file": ("a.wav", f.read(), "audio/wav")},
                        data={"lang": lang})
    return data.get("text", "")


def chat(messages: list, max_tokens: int = 300, temperature: float = 0.3) -> str:
    data = _request("POST", "/v1/chat", json={"messages": messages, "max_tokens": max_tokens,
                                              "temperature": temperature})
    return data.get("reply", "")
