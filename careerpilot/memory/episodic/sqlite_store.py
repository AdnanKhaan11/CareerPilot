"""
Purpose
    SQLite-backed storage for structured, dated career events.

Responsibilities
    - init_db() — create tables if missing
    - insert_application(...)
    - update_status(company, role, new_status)
    - list_applications(status_filter=None)
    - search_episodic(query) — simple text/date-based lookup for session.py

Inputs:  structured application/interview data
Outputs: rows / confirmation strings

Dependencies:   sqlite3 (stdlib)
Related files:  tools/applications.py, runtime/session.py
Design pattern: Repository pattern over a single SQLite file
Difficulty:     beginner

Agentic AI concepts used: episodic memory
Software engineering concepts used: schema migrations (even a tiny one), parameterized queries (never string-format SQL)

Future implementation notes
    Add an `interviews` table (company, round, date, interviewer_notes_ref)
    once applications works end to end.

Common beginner mistakes
    - String-formatting SQL instead of using parameterized queries (injection risk + bugs)
    - Not creating an index on company/role if list_applications gets slow
    - Opening a new connection per call without closing it
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from careerpilot.config.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    date_applied TEXT NOT NULL,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'applied',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT NOT NULL,
    occurred_on TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    """Opens one connection for one operation, then the caller closes it
    (we use a `with` block everywhere below, which closes it automatically).

    Why not keep one connection open forever? SQLite connections aren't
    safe to share across threads/requests without care, and opening one
    per call is cheap — SQLite is a local file, not a network database.

    row_factory = sqlite3.Row is the important bit here: by default,
    a query result row looks like a plain tuple, e.g. ('Acme', 'ML
    Engineer', ...) — you'd have to remember that index 0 is the
    company, index 1 is the role, and so on. sqlite3.Row lets you
    access columns by NAME instead, like a dictionary — row["company"]
    — which is what makes `dict(row)` below actually work.
    """
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Creates the applications table if it doesn't exist yet. Safe to
    call every time the app starts — CREATE TABLE IF NOT EXISTS means
    this never wipes existing data, it just makes sure the table is there.
    """
    with _connect() as conn:
        conn.executescript(SCHEMA)


def insert_application(
    company: str,
    role: str,
    date_applied: str,
    source: str | None = None,
    notes: str | None = None,
) -> int:
    """Adds one new application row and returns its auto-generated id.

    The `?` marks in the SQL are placeholders — SQLite fills them in
    safely from the tuple passed as the second argument to execute().
    This is called a "parameterized query". Never build the SQL string
    yourself with an f-string like f"...WHERE company = '{company}'" —
    if company ever contained something like `' OR '1'='1`, you'd have
    just handed an attacker (or a careless user) control over your
    database. Placeholders make that impossible: SQLite always treats
    the values as plain data, never as part of the SQL command itself.

    `status` isn't listed here on purpose — the table schema already
    defaults it to 'applied' for every new row (see SCHEMA above), so a
    brand new application always starts in that state without us having
    to repeat "applied" everywhere we insert one.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO applications (company, role, date_applied, source, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (company, role, date_applied, source, notes),
        )
        # lastrowid is SQLite's way of telling you the id it just
        # generated for the row you inserted (from AUTOINCREMENT).
        return cursor.lastrowid


def update_status(company: str, role: str, new_status: str) -> bool:
    """Changes the status of an existing application (e.g. 'applied' ->
    'interview'). Returns True if a row was actually found and changed,
    False if no application matched that company+role — this lets the
    caller (the tool that the LLM invokes) give a clear "I couldn't find
    that application" message instead of silently doing nothing.

    cursor.rowcount is SQLite telling you how many rows the UPDATE
    actually touched. 0 means "no match", which is exactly what we want
    to detect here.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE applications SET status = ? WHERE company = ? AND role = ?",
            (new_status, company, role),
        )
        return cursor.rowcount > 0


def list_applications(status_filter: str | None = None) -> list[dict]:
    """Returns every application, optionally narrowed to one status
    (e.g. only 'interview' stage ones). Ordered newest-applied-first,
    since that's almost always what you want to see.

    Two different SQL queries are used here (one with a WHERE clause,
    one without) rather than trying to make one query handle both
    cases — that's simpler to read than building a query string
    conditionally, at the cost of a tiny bit of repetition.

    [dict(row) for row in rows] converts each sqlite3.Row into a plain
    Python dict, e.g. {"id": 1, "company": "Acme AI", "role": "ML
    Engineer", ...} — the shape the rest of the app (and eventually the
    LLM-facing tool) actually wants to work with.
    """
    with _connect() as conn:
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY date_applied DESC",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM applications ORDER BY date_applied DESC"
            ).fetchall()
        return [dict(row) for row in rows]


def search_episodic(query: str) -> list[dict]:
    """A simple, cheap text search over company/role/notes — this does
    NOT need to be smart. Semantic similarity (e.g. "companies like
    this one") lives in Qdrant; this just answers "does anything here
    literally mention this word" quickly, for things like session.py
    pulling up "anything about TechCorp" before a turn.

    LIKE '%word%' means "contains word anywhere in the text" — the %
    signs are SQL's wildcard for "anything can go here". We build that
    pattern once (like_pattern) and reuse it across all three columns,
    rather than repeating the string-building three times.
    """
    with _connect() as conn:
        like_pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM applications "
            "WHERE company LIKE ? OR role LIKE ? OR notes LIKE ? "
            "ORDER BY date_applied DESC",
            (like_pattern, like_pattern, like_pattern),
        ).fetchall()
        return [dict(row) for row in rows]


def insert_episode(summary: str, occurred_on: str) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO episodes (summary, occurred_on) VALUES (?, ?)",
            (summary, occurred_on),
        )
        return cursor.lastrowid


def list_episodes() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM episodes ORDER BY occurred_on DESC"
        ).fetchall()
        return [dict(row) for row in rows]
