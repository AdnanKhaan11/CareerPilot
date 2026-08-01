"""
Purpose
    Persists conversation metadata (id, title, timestamps) and their
    turns to SQLite. Before this, conversations only lived in an
    in-memory dict — no way to list past conversations, and a backend
    restart lost everything.

A note on what this does NOT restore after a restart
    This persists human-readable turns, not loop/agent.py's internal
    message format (tool_use/tool_result blocks). get_turns_as_messages()
    reconstructs plain-text turns so the agent has real conversational
    context again — but tool-call-level detail from before the restart
    is genuinely gone. Accepted, documented limitation, not an oversight.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from careerpilot.config.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

TITLE_MAX_LENGTH = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def _make_title(first_message: str) -> str:
    text = first_message.strip().replace("\n", " ")
    if len(text) <= TITLE_MAX_LENGTH:
        return text
    return text[:TITLE_MAX_LENGTH].rstrip() + "..."


def exists(conversation_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return row is not None


def get_or_create(conversation_id: str, first_message: str) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if row:
            return dict(row)

        now = _now()
        title = _make_title(first_message)
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conversation_id, title, now, now),
        )
        return {"id": conversation_id, "title": title, "created_at": now, "updated_at": now}


def add_turn(conversation_id: str, role: str, content: str) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversation_turns (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now),
        )
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))


def list_conversations() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_conversation(conversation_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return dict(row) if row else None


def get_turns(conversation_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM conversation_turns "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_turns_as_messages(conversation_id: str) -> list[dict]:
    return [{"role": t["role"], "content": t["content"]} for t in get_turns(conversation_id)]


def rename_conversation(conversation_id: str, new_title: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (new_title, _now(), conversation_id),
        )
        return cursor.rowcount > 0


def delete_conversation(conversation_id: str) -> bool:
    with _connect() as conn:
        conn.execute("DELETE FROM conversation_turns WHERE conversation_id = ?", (conversation_id,))
        cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return cursor.rowcount > 0