"""Course Memory storage and simple retrieval for Muta."""

import re
import secrets
import sqlite3
import time
from contextlib import closing

from pypdf import PdfReader


_DB = {"path": "data/sauti.db"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS course_memory_courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    language TEXT NOT NULL,
    created REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS course_memory_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    created REAL NOT NULL,
    FOREIGN KEY(course_id)
        REFERENCES course_memory_courses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS course_memory_quizzes (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    course_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    context TEXT NOT NULL,
    created REAL NOT NULL,
    FOREIGN KEY(course_id)
        REFERENCES course_memory_courses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cm_courses_owner
    ON course_memory_courses(owner_id);

CREATE INDEX IF NOT EXISTS idx_cm_docs_course
    ON course_memory_documents(course_id);
"""


def init(path=None):
    """Use the same SQLite file as the existing Muta app."""
    if path:
        _DB["path"] = path

    with closing(_connect()) as conn, conn:
        conn.executescript(SCHEMA)


def _connect():
    conn = sqlite3.connect(_DB["path"], timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_course(owner_id, name, language):
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            """
            INSERT INTO course_memory_courses
                (owner_id, name, language, created)
            VALUES (?, ?, ?, ?)
            """,
            (owner_id, name, language, time.time()),
        )
        course_id = cur.lastrowid

    return get_course(owner_id, course_id)


def list_courses(owner_id):
    with closing(_connect()) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.language, c.created,
                   COUNT(d.id) AS document_count
            FROM course_memory_courses AS c
            LEFT JOIN course_memory_documents AS d
                ON d.course_id = c.id
            WHERE c.owner_id = ?
            GROUP BY c.id
            ORDER BY c.created DESC
            """,
            (owner_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_course(owner_id, course_id):
    with closing(_connect()) as conn:
        row = conn.execute(
            """
            SELECT id, owner_id, name, language, created
            FROM course_memory_courses
            WHERE id = ? AND owner_id = ?
            """,
            (course_id, owner_id),
        ).fetchone()

    return dict(row) if row else None


def extract_document(filename, stream):
    """Extract text from a PDF or TXT upload."""
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if extension == "pdf":
        reader = PdfReader(stream)
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)

    elif extension == "txt":
        raw = stream.read()
        if isinstance(raw, bytes):
            text = raw.decode("utf-8-sig", errors="replace")
        else:
            text = raw

    else:
        raise ValueError("Upload a PDF or TXT file.")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if not text:
        raise ValueError(
            "No selectable text was found. Scanned PDFs are not supported yet."
        )

    if len(text) > 600_000:
        raise ValueError(
            "This document is too large. Please upload a shorter document."
        )

    return text


def add_document(owner_id, course_id, filename, content):
    # Confirm that the course belongs to this browser's anonymous user ID.
    if not get_course(owner_id, course_id):
        return False

    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO course_memory_documents
                (course_id, filename, content, created)
            VALUES (?, ?, ?, ?)
            """,
            (course_id, filename, content, time.time()),
        )

    return True


def get_context(owner_id, course_id, question="", max_chars=6000):
    """Return the note sections with the most words in common with the query."""
    if not get_course(owner_id, course_id):
        return ""

    with closing(_connect()) as conn:
        documents = conn.execute(
            """
            SELECT d.filename, d.content
            FROM course_memory_documents AS d
            JOIN course_memory_courses AS c ON c.id = d.course_id
            WHERE c.owner_id = ? AND c.id = ?
            ORDER BY d.created ASC
            """,
            (owner_id, course_id),
        ).fetchall()

    query_words = set(re.findall(r"\w{3,}", question.lower()))
    candidates = []

    # Small overlapping text sections: no embedding model or extra service.
    for document in documents:
        content = document["content"]
        step = 900
        width = 1100

        for start in range(0, len(content), step):
            part = content[start:start + width].strip()
            if not part:
                continue

            part_words = set(re.findall(r"\w{3,}", part.lower()))
            score = len(query_words & part_words)

            candidates.append({
                "filename": document["filename"],
                "text": part,
                "score": score,
            })

    if not candidates:
        return ""

    # Stable sort keeps the original note order when scores are tied.
    if query_words:
        candidates.sort(key=lambda item: item["score"], reverse=True)

    selected = []
    total = 0

    for item in candidates:
        section = f"Source: {item['filename']}\n{item['text']}"
        remaining = max_chars - total

        if remaining <= 0:
            break

        if len(section) > remaining:
            section = section[:remaining]

        selected.append(section)
        total += len(section) + 2

        if total >= max_chars:
            break

        if len(selected) >= 5:
            break

    return "\n\n".join(selected)


def save_quiz(owner_id, course_id, question, context):
    quiz_id = secrets.token_urlsafe(18)

    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO course_memory_quizzes
                (id, owner_id, course_id, question, context, created)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                quiz_id,
                owner_id,
                course_id,
                question,
                context,
                time.time(),
            ),
        )

    return quiz_id


def get_quiz(owner_id, course_id, quiz_id):
    with closing(_connect()) as conn:
        row = conn.execute(
            """
            SELECT id, question, context
            FROM course_memory_quizzes
            WHERE id = ? AND owner_id = ? AND course_id = ?
            """,
            (quiz_id, owner_id, course_id),
        ).fetchone()

    return dict(row) if row else None