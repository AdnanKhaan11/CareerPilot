"""
Purpose
    Periodically distill raw chat history into durable semantic facts
    and one episodic summary — deliberately NOT on the hot path of
    every reply, so it stays cheap and safe to fail.

Responsibilities
    - maybe_consolidate(chat_count_since_last_run) -> bool: pure
      threshold check, no side effects
    - consolidate(recent_turns, client) -> ConsolidationResult: the
      actual work — summarize via an LLM call, then write facts to
      Qdrant and one episode to SQLite

Inputs:  recent chat history (a slice of raw turns, owned and passed in
         by the caller — this module keeps no history of its own)
Outputs: writes to semantic/episodic stores as a side effect; returns
         a ConsolidationResult describing what was written

Dependencies:   memory.semantic.qdrant_store, memory.episodic.sqlite_store,
                an LLM client (injected by the caller, not constructed here)
Related files:  runtime/session.py, config/settings.py
Design pattern: Batch processing / scheduled job. The counter and raw
                turn buffer are owned by the CALLER (the gateway), not
                this module — consolidation.py stays a pure function
                with no hidden state, consistent with the rest of the
                memory pillar.
Difficulty:     advanced

Agentic AI concepts used: memory consolidation, summarization
Software engineering concepts used: loss-safety (a failed run writes
  NOTHING, never something partial), dependency injection (the LLM
  client is passed in, which is what makes this testable without a
  real API key)

A note on the episodic store
    This file's original design assumed episodic/sqlite_store.py already
    had a generic "episode" concept — it didn't; that file only had an
    `applications` table. An `episodes` table + insert_episode()/
    list_episodes() were added to sqlite_store.py alongside this file,
    since "one episode to SQLite" needed somewhere real to go.

Future implementation notes
    If you want true cross-store atomicity (all-or-nothing across
    Qdrant AND SQLite together), that needs a two-phase-commit-style
    approach — genuinely overkill for this project. As built: the LLM
    call and JSON parsing happen entirely in memory FIRST, so the most
    likely failure (a bad response) writes nothing at all. A failure
    partway through the writes themselves (rare — these are simple
    local calls) is a known, accepted edge case, not engineered around.

Common beginner mistakes
    - Running consolidation synchronously on the reply path (adds
      latency the user feels on every single turn)
    - Losing the raw chat log if summarization fails — this is exactly
      why consolidate() raises ConsolidationError instead of silently
      swallowing a failure: the caller sees the exception and knows not
      to reset its counter, so the same batch gets retried, not dropped
    - Writing partial results (e.g. some facts but not the episode) when
      the LLM call itself is what failed — tested below to confirm this
      never happens
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from careerpilot.config.settings import settings
from careerpilot.memory.episodic.sqlite_store import insert_episode
from careerpilot.memory.semantic.qdrant_store import upsert_note

# How many chats to accumulate before running a consolidation pass. The
# CALLER (the gateway) owns the actual counter and the raw turn buffer —
# this module only decides WHEN (maybe_consolidate) and DOES the work
# (consolidate); it holds no state of its own.
N_CHATS_BETWEEN_CONSOLIDATION = 10

SUMMARIZATION_SYSTEM_PROMPT = """You distill a conversation transcript into durable memory.

Read the transcript and respond with ONLY valid JSON, no other text, in
exactly this shape:

{
  "facts": [{"company": "<company name>", "text": "<a standing fact worth remembering>"}],
  "episode_summary": "<one paragraph summarizing what happened in this session>"
}

Only include facts that would still be useful weeks from now (preferences,
things the user was asked, decisions made) — not routine back-and-forth.
If there is nothing worth remembering as a fact, return an empty list for
"facts". Always provide an episode_summary, even a short one."""


class ConsolidationError(Exception):
    """Raised when a consolidation pass fails for any reason — a bad
    LLM response, malformed JSON, a write failure. The caller catching
    this IS the loss-safety contract: on this exception, the caller
    must NOT reset its own chat counter, so the exact same batch of
    turns gets retried on the next attempt instead of silently
    vanishing.
    """


@dataclass
class ConsolidationResult:
    facts_written: int
    episode_written: bool


def maybe_consolidate(chat_count_since_last_run: int) -> bool:
    """Returns True once the threshold is reached. The caller resets
    its own counter to 0 only after consolidate() succeeds.
    """
    return chat_count_since_last_run >= N_CHATS_BETWEEN_CONSOLIDATION


def _transcript_from_turns(turns: list[dict]) -> str:
    """Turns the raw message list into a plain-text transcript for the
    summarizer. Only user/assistant TEXT is included — tool_use/
    tool_result blocks are mechanics, not conversation content, and
    would just add noise to what the summarizer needs to read.
    """
    lines = []
    for turn in turns:
        role = turn["role"]
        content = turn["content"]

        if isinstance(content, str):
            if role == "user":
                lines.append(f"User: {content}")
            continue

        if role == "assistant" and isinstance(content, list):
            text = "".join(
                b.text for b in content if getattr(b, "type", "") == "text" and b.text
            )
            if text:
                lines.append(f"Assistant: {text}")
            continue
        # role="user" with list content is a tool_result turn — skipped.

    return "\n".join(lines)


def consolidate(
    recent_turns: list[dict], client, model: str | None = None
) -> ConsolidationResult:
    """Summarizes `recent_turns` and writes the result. `client` is
    required, not defaulted to a real provider here — that's what
    makes this testable, and lets the caller decide which model runs
    the summarization (settings.small_model is the intended default).

    Loss-safety: the LLM call and JSON parsing happen FIRST, entirely
    in memory. Nothing is written until both have already succeeded —
    a bad response or malformed JSON leaves both stores completely
    untouched and raises ConsolidationError instead.
    """
    transcript = _transcript_from_turns(recent_turns)
    if not transcript.strip():
        return ConsolidationResult(facts_written=0, episode_written=False)

    try:
        response = client.messages.create(
            model=model or settings.small_model,
            system=SUMMARIZATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
            tools=[],
            max_tokens=1024,
        )
        raw_text = "".join(b.text for b in response.content if b.type == "text")
        parsed = json.loads(raw_text)
        facts = parsed["facts"]
        episode_summary = parsed["episode_summary"]
    except Exception as exc:
        raise ConsolidationError(
            f"summarization failed, nothing was written: {exc}"
        ) from exc

    # Writes only happen here, after the LLM call and JSON parsing above
    # have both already succeeded.
    for fact in facts:
        upsert_note(fact["company"], fact["text"])

    episode_written = False
    if episode_summary:
        insert_episode(episode_summary, date.today().isoformat())
        episode_written = True

    return ConsolidationResult(
        facts_written=len(facts), episode_written=episode_written
    )
