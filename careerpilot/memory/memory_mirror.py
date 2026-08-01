"""
Purpose
    Regenerate a human-readable Markdown mirror of all durable memory
    at .careerpilot/MEMORY.md — always a full overwrite of a disposable
    projection, never a second source of truth.

Responsibilities
    - regenerate_memory_md(notes_limit, applications_limit) — pull
      recent semantic notes + applications, render as Markdown, write

Inputs:  current semantic + episodic store contents
Outputs: .careerpilot/MEMORY.md on disk

Dependencies:   memory.semantic.qdrant_store, memory.episodic.sqlite_store
Related files:  runtime/session.py or the gateway (call this after saving each turn)
Design pattern: Read-model projection (state.db/Qdrant are the write
                side, MEMORY.md is a read-only projection)
Difficulty:     intermediate

Agentic AI concepts used: memory transparency / inspectability
Software engineering concepts used: idempotent regeneration (always
  safe to overwrite), best-effort side effects (a failure here never
  breaks the turn that triggered it — same reasoning as ops/tracing.py
  and ops/usage.py)

A note on qdrant_store.list_recent_notes
    This didn't exist before this file needed it — qdrant_store only
    had search_semantic(query), which needs a query string and can't
    answer "show me everything." A small scroll()-based
    list_recent_notes(limit) was added to qdrant_store.py alongside
    this file, the same way insert_episode/delete_note were added when
    other files needed them.

Common beginner mistakes
    - Trying to hand-edit MEMORY.md and expecting it to persist — it's
      always a regenerated, disposable projection; the next turn
      overwrites it
    - Regenerating from a full table scan once memory grows large —
      notes_limit/applications_limit exist specifically to cap this
    - Letting a Qdrant/SQLite hiccup crash the turn that triggered the
      regeneration — this fails silently on purpose, same as tracing/usage
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from careerpilot.memory.semantic.qdrant_store import list_recent_notes
from careerpilot.memory.episodic.sqlite_store import list_applications

MEMORY_MD_PATH = Path(".careerpilot/MEMORY.md")

DEFAULT_NOTES_LIMIT = 20
DEFAULT_APPLICATIONS_LIMIT = 20


def _render_notes_section(notes: list[dict]) -> str:
    if not notes:
        return "_No notes saved yet._"
    return "\n".join(f"- **{n['company']}**: {n['text']}" for n in notes)


def _render_applications_section(applications: list[dict]) -> str:
    if not applications:
        return "_No applications logged yet._"
    return "\n".join(
        f"{i}. {a['company']} — {a['role']} — {a['status']} (applied {a['date_applied']})"
        for i, a in enumerate(applications, start=1)
    )


def _render_markdown(notes: list[dict], applications: list[dict]) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"# CareerPilot Memory\n\n"
        f"_Last updated: {timestamp}_\n\n"
        f"## Recent notes\n\n"
        f"{_render_notes_section(notes)}\n\n"
        f"## Applications\n\n"
        f"{_render_applications_section(applications)}\n"
    )


def regenerate_memory_md(
    notes_limit: int = DEFAULT_NOTES_LIMIT,
    applications_limit: int = DEFAULT_APPLICATIONS_LIMIT,
) -> None:
    """Regenerates .careerpilot/MEMORY.md from Qdrant + SQLite.
    Call this once per turn, from the gateway after saving the turn —
    never from inside loop/agent.py itself.
    """
    try:
        notes = list_recent_notes(limit=notes_limit)
        applications = list_applications()[:applications_limit]
        rendered = _render_markdown(notes, applications)
        MEMORY_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_MD_PATH.write_text(rendered, encoding="utf-8")
    except Exception:
        pass  # best-effort — see docstring above
