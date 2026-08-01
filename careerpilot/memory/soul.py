"""
Purpose
    Load and update profile.md — CareerPilot's standing-preferences
    file. Plays the same role waku's SOUL.md does: durable, human-
    readable preferences the agent can edit via a tool, and the user
    can edit by hand — never buried in embeddings or code.

Responsibilities
    - load_profile() -> str, read fresh for injection into every turn's
      working memory
    - update_profile(new_text) -> append a new preference, skipping
      exact duplicates

Inputs:  profile.md on disk
Outputs: its text content / confirmation of an update

Dependencies:   filesystem only
Related files:  runtime/session.py (should inject this into every
                turn), tools/memory_admin.py (update_profile tool)
Design pattern: Simple file-backed repository
Difficulty:     beginner

Agentic AI concepts used: standing preferences / persona memory
Software engineering concepts used: human-readable state over opaque
  state, idempotency (an exact repeat is detected and skipped, not
  silently appended again)

Future implementation notes
    Keep this file short — it's injected into every single turn's
    prompt, so it costs tokens on every call. The duplicate check below
    is exactly what stands between "keep this short" and "accumulate
    the same preference ten times because the model kept re-stating it".

Common beginner mistakes
    - Letting profile.md grow unbounded (every fact should really go to
      semantic memory, not here — this file is for standing
      preferences, not a general notes dump)
    - Forgetting to reload from disk if the user hand-edited it since
      the process started — load_profile() is deliberately NOT cached,
      for exactly this reason
    - Rewriting the whole file instead of appending — a rewrite risks
      losing something on any bug in the "reconstruct the file"
      logic; appending can't lose existing content
"""

from __future__ import annotations

from pathlib import Path

PROFILE_PATH = Path("profile.md")

_DEFAULT_HEADER = (
    "# CareerPilot profile\n\n"
    "Standing preferences to remember across every session.\n"
)


def load_profile() -> str:
    """Reads profile.md fresh from disk every call — deliberately not
    cached, unlike runtime/session.py's system prompt. That file only
    changes when you hand-edit it; this one can ALSO change from
    inside a conversation (via the update_profile tool), sometimes
    seconds before the next turn needs it — caching here risks reading
    a stale version the same turn it was just updated.
    """
    if PROFILE_PATH.exists():
        return PROFILE_PATH.read_text(encoding="utf-8")
    return ""


def _existing_preference_lines(content: str) -> set[str]:
    """Pulls out the bare text of every bullet already in the file
    (stripping the leading "- "), so update_profile can check for an
    exact repeat before appending another one.
    """
    lines = set()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        if stripped:
            lines.add(stripped)
    return lines


def update_profile(new_text: str) -> str:
    """Appends `new_text` as a new bullet — waku's update_soul does the
    same (append, not rewrite): the user can always tidy/reorganize
    profile.md by hand later, and appending can never lose existing
    content the way a buggy "rewrite the whole file" attempt could.

    Creates the file with a short default header if it doesn't exist
    yet. Skips the write (and says so) if this exact preference is
    already present — profile.md is injected into every single turn's
    prompt, so letting exact repeats accumulate would burn tokens for
    no benefit, forever.
    """
    new_text = new_text.strip()
    if not new_text:
        raise ValueError("Cannot add an empty preference to profile.md.")

    current = load_profile()

    if new_text in _existing_preference_lines(current):
        return f"Already in profile.md — not adding a duplicate: '{new_text}'"

    if not current:
        current = _DEFAULT_HEADER

    updated = current.rstrip("\n") + f"\n- {new_text}\n"
    PROFILE_PATH.write_text(updated, encoding="utf-8")
    return f"Added to profile.md: '{new_text}'"
