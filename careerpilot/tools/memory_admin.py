"""
Purpose
    Give the agent tools to correct its own memory instead of memory
    being read-only — manage_memory (forget/correct a note),
    update_profile (a thin wrapper over memory.soul.update_profile),
    and create_skill (writes a new, immediately-loadable SKILL.md via
    the shared skill_writer utility — see that file's docstring for
    why this used to be duplicated logic and no longer is).

Responsibilities
    - manage_memory(action='forget'|'correct', target, new_text=None)
    - update_profile_tool_fn(new_text) — delegates to memory.soul.update_profile
    - create_skill(name, trigger_keywords, instructions) — delegates
      to memory.procedural.skill_writer.write_skill

Dependencies:   memory.semantic.qdrant_store, memory.soul,
                memory.procedural.skill_writer, tools.applications.safe_tool
Related files:  memory/soul.py, memory/semantic/qdrant_store.py,
                memory/procedural/skill_writer.py (REQUIRED — create
                that file before this one will import successfully),
                gateway/dashboard/routers/skills.py (the other caller
                of skill_writer)
Design pattern: Command, reusing the same safe_tool Decorator as
                applications.py/notes.py

Future implementation notes
    Consider requiring an explicit confirmation step before 'forget'
    actually deletes anything. As built: every forget/correct response
    echoes the exact note text affected, so a wrong match is visible
    and correctable, even though it isn't blocked beforehand.

Common beginner mistakes
    - Letting 'forget' silently delete without any confirmation or
      audit trail
    - Matching 'target' by pure embedding similarity alone for a
      destructive action — _find_target_note() below prefers an exact
      textual containment match first
    - Reimplementing skill-file writing here instead of calling the
      shared skill_writer — that duplication is exactly what used to
      exist and exactly what this file no longer does
"""

from __future__ import annotations

from careerpilot.memory.semantic.qdrant_store import (
    search_semantic,
    delete_note,
    upsert_note,
)
from careerpilot.memory.soul import update_profile
from careerpilot.memory.procedural.skill_writer import write_skill
from careerpilot.tools.applications import safe_tool
from careerpilot.tools.registry import Tool

MANAGE_MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["forget", "correct"]},
        "target": {"type": "string", "description": "which fact/note to act on"},
        "new_text": {"type": "string", "description": "required for 'correct'"},
    },
    "required": ["action", "target"],
}


def _find_target_note(target: str) -> dict | None:
    candidates = search_semantic(target, top_k=5)
    if not candidates:
        return None
    target_lower = target.strip().lower()
    for candidate in candidates:
        text_lower = candidate["text"].lower()
        if target_lower in text_lower or text_lower in target_lower:
            return candidate
    return candidates[0]


@safe_tool
def manage_memory(args: dict) -> str:
    action = args["action"]
    target = args["target"]

    note = _find_target_note(target)
    if note is None:
        return f"No stored note matching '{target}' was found — nothing changed."

    if action == "forget":
        delete_note(note["id"])
        return f"Forgot note for {note['company']}: \"{note['text']}\""

    if action == "correct":
        new_text = args["new_text"]
        delete_note(note["id"])
        new_id = upsert_note(note["company"], new_text)
        return (
            f"Corrected note for {note['company']}: "
            f"\"{note['text']}\" -> \"{new_text}\" (id={new_id})"
        )

    return f"error: unknown action '{action}' — expected 'forget' or 'correct'."


UPDATE_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {"new_text": {"type": "string"}},
    "required": ["new_text"],
}


@safe_tool
def update_profile_tool_fn(args: dict) -> str:
    return update_profile(args["new_text"])


CREATE_SKILL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "trigger_keywords": {"type": "array", "items": {"type": "string"}},
        "instructions": {"type": "string"},
    },
    "required": ["name", "instructions"],
}


@safe_tool
def create_skill(args: dict) -> str:
    skill = write_skill(
        name=args["name"],
        instructions=args["instructions"],
        trigger_keywords=args.get("trigger_keywords", []),
    )
    return f"Saved new skill '{skill.name}' -> {skill.path}. It loads on the next message, no restart needed."


manage_memory_tool = Tool(
    name="manage_memory",
    description="Forget or correct a stored fact/note.",
    input_schema=MANAGE_MEMORY_SCHEMA,
    fn=manage_memory,
)

update_profile_tool = Tool(
    name="update_profile",
    description="Save a standing preference to profile.md.",
    input_schema=UPDATE_PROFILE_SCHEMA,
    fn=update_profile_tool_fn,
)

create_skill_tool = Tool(
    name="create_skill",
    description="Save a repeatable workflow as a new skill.",
    input_schema=CREATE_SKILL_SCHEMA,
    fn=create_skill,
)
