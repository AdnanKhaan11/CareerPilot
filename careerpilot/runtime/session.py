"""
Purpose
    Assembles the ephemeral working memory for one turn: a system
    prompt (with today's date, and relevant memory if the gate says
    so) plus a trimmed, valid message history with the new user
    message appended. Nothing here survives past the turn.

Responsibilities
    - load_system_prompt() — read prompts/system_prompt.md, cached
    - build_working_memory(user_message, history) — the whole assembly:
      gate check, memory merge, date injection, history capping

Inputs:  raw user message text, existing chat history list
Outputs: (system_prompt: str, messages: list[dict])

Dependencies:   memory.retrieval_gate, memory.semantic.qdrant_store, memory.episodic.sqlite_store
Related files:  loop/agent.py (the caller), prompts/system_prompt.md
Design pattern: Builder (assembles a complex object — the turn's full
                working memory — from several independent parts)
Difficulty:     intermediate

Agentic AI concepts used: working memory, context management, retrieval gate
Software engineering concepts used: pure functions (build_working_memory
  returns fresh values every call, never mutates what the caller holds),
  cache invalidation via file-modification-time (same pattern used in
  memory/procedural/skill_loader.py's hot-reload)

Future implementation notes
    Today's date is now injected on every turn — this is exactly the bug
    class waku-agent hit in its own session.py: without it, the model
    has no concept of "now" and can't reason correctly about "due this
    week" or "in 3 days".

Common beginner mistakes
    - Retrieving memory on every turn regardless of the gate's decision
      (tested below: memory functions are genuinely not called when the
      gate says no)
    - Letting this function mutate global state instead of returning
      fresh values
    - Capping chat history by raw message count instead of by complete
      turns — a single turn can span several messages (an assistant
      tool-request, its tool result, the final reply), and cutting
      mid-turn can leave an orphaned tool_use with no matching
      tool_result, which the next API call will reject outright
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from careerpilot.memory.retrieval_gate import should_retrieve
from careerpilot.memory.semantic.qdrant_store import search_semantic
from careerpilot.memory.episodic.sqlite_store import search_episodic
from careerpilot.memory.soul import load_profile

SYSTEM_PROMPT_PATH = Path("prompts/system_prompt.md")
DEFAULT_SYSTEM_PROMPT = "You are CareerPilot, a job-search co-pilot."

# How many complete past turns to keep — older turns are dropped to
# protect the token budget as a conversation grows long.
MAX_HISTORY_TURNS = 20

_cached_prompt: str | None = None
_cached_mtime: float | None = None


def load_system_prompt() -> str:
    """Reads prompts/system_prompt.md, caching the content so a normal
    turn doesn't re-read the file from disk every single time. The
    cache is invalidated by comparing the file's last-modified time
    against what was cached — hand-edit the prompt file, and the very
    next turn picks up the change with no restart needed.
    """
    global _cached_prompt, _cached_mtime

    if not SYSTEM_PROMPT_PATH.exists():
        return DEFAULT_SYSTEM_PROMPT

    mtime = SYSTEM_PROMPT_PATH.stat().st_mtime
    if _cached_prompt is None or mtime != _cached_mtime:
        _cached_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        _cached_mtime = mtime

    return _cached_prompt


def _with_current_date(system_prompt: str) -> str:
    """Appends today's date. Without this, the model has no way to
    correctly reason about "applications due this week" or "the
    interview is in 3 days" — it has no concept of "now" unless
    something explicitly tells it, every single turn.
    """
    today = date.today().isoformat()
    return f"{system_prompt}\n\nToday's date is {today}."


def _format_memory_context(facts: list[dict], episodes: list[dict]) -> str:
    """Turns raw semantic/episodic results into one readable block,
    appended to the system prompt for THIS turn only — never saved
    anywhere. Returns an empty string if there's nothing to show, so
    the caller doesn't need to check emptiness itself.
    """
    if not facts and not episodes:
        return ""

    lines = ["## Relevant memory for this turn"]

    if facts:
        lines.append("\nRelevant notes:")
        lines.extend(f"- ({f['company']}) {f['text']}" for f in facts)

    if episodes:
        lines.append("\nRelevant applications:")
        lines.extend(
            f"- {e['company']} — {e['role']} — {e['status']} (applied {e['date_applied']})"
            for e in episodes
        )

    return "\n".join(lines)


def _cap_history(history: list[dict], max_turns: int) -> list[dict]:
    """Keeps only the last `max_turns` complete turns.

    Can't just slice the last N *messages* — a turn can span several
    (an assistant tool-request, the matching tool result, the final
    reply), and the API requires a tool_use block to be immediately
    followed by its matching tool_result. Naive slicing could cut a
    turn in half and leave an orphaned tool_use, which the next API
    call would reject.

    Instead, this finds where each *complete* turn starts — a
    role="user" message whose content is a plain string (never a list
    of tool_result blocks, which share the same role but are produced
    mid-turn by the loop) — and only ever cuts on one of those
    boundaries, never in the middle of a turn.
    """
    turn_start_indices = [
        i
        for i, m in enumerate(history)
        if m["role"] == "user" and isinstance(m["content"], str)
    ]
    if len(turn_start_indices) <= max_turns:
        return history

    cutoff = turn_start_indices[-max_turns]
    return history[cutoff:]


def build_working_memory(
    user_message: str, history: list[dict]
) -> tuple[str, list[dict]]:
    """Assembles everything the loop needs for one turn: a system
    prompt (dated, and carrying relevant memory if the gate says so)
    plus a trimmed, valid message history with the new user message
    appended.

    Returns fresh values every call — the caller's original `history`
    list is never mutated, only read.
    """
    system_prompt = _with_current_date(load_system_prompt())
    profile = load_profile()
    if profile.strip():
        system_prompt = f"{system_prompt}\n\n{profile}"

    if should_retrieve(user_message):
        facts = search_semantic(user_message)
        episodes = search_episodic(user_message)
        memory_context = _format_memory_context(facts, episodes)
        if memory_context:
            system_prompt = f"{system_prompt}\n\n{memory_context}"

    trimmed_history = _cap_history(history, MAX_HISTORY_TURNS)
    messages = trimmed_history + [{"role": "user", "content": user_message}]
    return system_prompt, messages
