"""SQLite storage. Anonymous IDs only; no names, emails or phone numbers are stored."""
import csv
import hashlib
import io
import re
import secrets
import sqlite3
import statistics
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone

_DB = {"path": "data/sauti.db"}
UID_RE = re.compile(r"^USR_[0-9A-F]{8}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    user_id TEXT PRIMARY KEY,
    created REAL NOT NULL,
    channel TEXT NOT NULL,
    language TEXT,
    consent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS interactions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    user_id TEXT NOT NULL,
    language TEXT NOT NULL,
    input_channel TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'question',
    audio_duration REAL,
    audio_bytes INTEGER,
    asr_text TEXT,
    reply TEXT,
    asr_success INTEGER,
    llm_success INTEGER,
    asr_ms INTEGER,
    llm_ms INTEGER,
    latency_ms INTEGER,
    rating INTEGER,
    task_completed INTEGER,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_int_user ON interactions(user_id);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS wa_seen(sid TEXT PRIMARY KEY, ts REAL NOT NULL);
"""


def init(path: str | None = None) -> None:
    if path:
        _DB["path"] = path
    with closing(_conn()) as c, c:
        c.executescript(SCHEMA)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB["path"], timeout=10)
    c.row_factory = sqlite3.Row
    return c


# ---------- users ----------
def new_user_id() -> str:
    return "USR_" + secrets.token_hex(4).upper()


def user_id_from_phone(phone: str, salt: str) -> str:
    """Stable anonymous ID for a WhatsApp number. The number itself is never stored."""
    return "USR_" + hashlib.sha256((salt + phone).encode()).hexdigest()[:8].upper()


def valid_user_id(uid: str | None) -> bool:
    return bool(uid and UID_RE.match(uid))


def ensure_user(user_id: str, channel: str, consent: bool | None = None, language: str | None = None) -> None:
    with closing(_conn()) as c, c:
        c.execute("INSERT OR IGNORE INTO users(user_id, created, channel, consent) VALUES(?,?,?,0)",
                  (user_id, time.time(), channel))
        if consent is not None:
            c.execute("UPDATE users SET consent=? WHERE user_id=?", (1 if consent else 0, user_id))
        if language is not None:
            c.execute("UPDATE users SET language=? WHERE user_id=?", (language or None, user_id))


def get_user(user_id: str):
    with closing(_conn()) as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


# ---------- interactions ----------
FIELDS = ["user_id", "language", "input_channel", "mode", "audio_duration", "audio_bytes", "asr_text", "reply",
          "asr_success", "llm_success", "asr_ms", "llm_ms", "latency_ms", "error"]


def log_interaction(**kw) -> int:
    row = {k: kw.get(k) for k in FIELDS}
    row["mode"] = row["mode"] or "question"
    cols = ",".join(["timestamp"] + FIELDS)
    marks = ",".join("?" * (len(FIELDS) + 1))
    with closing(_conn()) as c, c:
        cur = c.execute(f"INSERT INTO interactions({cols}) VALUES({marks})",
                        [time.time()] + [row[k] for k in FIELDS])
        return cur.lastrowid


def record_feedback(interaction_id: int, user_id: str, rating: int | None = None,
                    task_completed: bool | None = None) -> bool:
    """Attach feedback to an interaction owned by user_id. Returns False if not found/owned."""
    if rating is not None and rating not in (1, 2, 3, 4, 5):
        raise ValueError("rating must be 1-5")
    with closing(_conn()) as c, c:
        row = c.execute("SELECT id FROM interactions WHERE id=? AND user_id=?",
                        (interaction_id, user_id)).fetchone()
        if not row:
            return False
        if rating is not None:
            c.execute("UPDATE interactions SET rating=? WHERE id=?", (rating, interaction_id))
        if task_completed is not None:
            c.execute("UPDATE interactions SET task_completed=? WHERE id=?",
                      (1 if task_completed else 0, interaction_id))
        return True


def last_answered(user_id: str):
    """Most recent successfully answered interaction (used for WhatsApp rating replies)."""
    with closing(_conn()) as c:
        return c.execute("SELECT * FROM interactions WHERE user_id=? AND llm_success=1 "
                         "ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()


def set_setting(key: str, value: str) -> None:
    with closing(_conn()) as c, c:
        c.execute("INSERT INTO settings(key,value,ts) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
                  (key, value, time.time()))


def get_setting(key: str):
    with closing(_conn()) as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def mark_seen(sid: str) -> bool:
    """True the first time a WhatsApp MessageSid is seen, False for provider retries."""
    if not sid:
        return True
    with closing(_conn()) as c, c:
        cur = c.execute("INSERT OR IGNORE INTO wa_seen(sid, ts) VALUES(?,?)", (sid, time.time()))
        return cur.rowcount == 1


def count_recent(user_id: str, seconds: int = 3600) -> int:
    with closing(_conn()) as c:
        return c.execute("SELECT COUNT(*) FROM interactions WHERE user_id=? AND timestamp>?",
                         (user_id, time.time() - seconds)).fetchone()[0]


# ---------- reporting ----------
def _rate(num: int, den: int):
    return round(100.0 * num / den, 1) if den else None


def stats() -> dict:
    with closing(_conn()) as c:
        rows = c.execute("SELECT * FROM interactions").fetchall()
    n = len(rows)
    asr_rows = [r for r in rows if r["asr_success"] is not None]
    llm_rows = [r for r in rows if r["llm_success"] is not None]
    ok_rows = [r for r in rows if r["llm_success"] == 1 and r["latency_ms"] is not None]
    rated = [r["rating"] for r in rows if r["rating"] is not None]
    task = [r["task_completed"] for r in rows if r["task_completed"] is not None]
    lat = [r["latency_ms"] for r in ok_rows]
    return {
        "total_interactions": n,
        "participants": len({r["user_id"] for r in rows}),
        "by_language": dict(Counter(r["language"] for r in rows)),
        "by_channel": dict(Counter(r["input_channel"] for r in rows)),
        "asr_success_rate": _rate(sum(r["asr_success"] for r in asr_rows), len(asr_rows)),
        "llm_success_rate": _rate(sum(r["llm_success"] for r in llm_rows), len(llm_rows)),
        "avg_latency_ms": round(statistics.mean(lat)) if lat else None,
        "median_latency_ms": round(statistics.median(lat)) if lat else None,
        "avg_asr_ms": round(statistics.mean([r["asr_ms"] for r in rows if r["asr_ms"] is not None]))
        if any(r["asr_ms"] is not None for r in rows) else None,
        "avg_llm_ms": round(statistics.mean([r["llm_ms"] for r in rows if r["llm_ms"] is not None]))
        if any(r["llm_ms"] is not None for r in rows) else None,
        "avg_audio_kb": round(statistics.mean([r["audio_bytes"] for r in rows if r["audio_bytes"]]) / 1024, 1)
        if any(r["audio_bytes"] for r in rows) else None,
        "avg_rating": round(statistics.mean(rated), 2) if rated else None,
        "rated_count": len(rated),
        "task_completion_rate": _rate(sum(task), len(task)),
        "task_answered_count": len(task),
        "failed": sum(1 for r in rows if r["error"]),
    }


def export_csv(include_text: bool = False) -> str:
    cols = ["id", "timestamp_utc", "user_id", "language", "input_channel", "mode", "audio_duration", "audio_bytes",
            "asr_success", "llm_success", "asr_ms", "llm_ms", "latency_ms", "rating", "task_completed", "error"]
    if include_text:
        cols += ["asr_text", "reply"]
    with closing(_conn()) as c:
        rows = c.execute("SELECT * FROM interactions ORDER BY id").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        d = dict(r)
        d["timestamp_utc"] = datetime.fromtimestamp(r["timestamp"], timezone.utc).isoformat(timespec="seconds")
        w.writerow([d.get(k) for k in cols])
    return buf.getvalue()
