"""
Purpose
    Load procedural 'skills' (markdown playbooks) relevant to the current
    message. Scans skills/ (including skills/community/, since it's a
    subfolder) for SKILL.md-style files, and matches them against a
    message by keyword overlap — no embeddings, no magic, a score you
    could compute by hand.

Responsibilities
    - SkillLoader.refresh() — (re)scan the skill directories
    - SkillLoader.match(message) — return the skills relevant to a message
    - _parse() / _parse_text() — shared validation, also reusable by a
      future create_skill tool or skill-install script, so there's only
      ever one definition of "what counts as a valid skill file"

Inputs:  the skills/ directory tree, the current user message
Outputs: list[Skill] — matched skills, each with name/description/body

Dependencies:   filesystem access, a small hand-rolled frontmatter parser
Related files:  skills/TEMPLATE.md, runtime/session.py, tools/memory_admin.py (create_skill)
Design pattern: Strategy (pluggable matching) + a tiny in-memory cache
                that self-invalidates (the mtime signature check)
Difficulty:     intermediate

Agentic AI concepts used: procedural memory, skills, progressive disclosure
    (frontmatter is always scanned — cheap; a skill's full body only
    enters the prompt once it actually matches)
Software engineering concepts used: convention over configuration
    (frontmatter format), cache invalidation via a cheap signature check

Future implementation notes
    Keep matching keyword-based; only reach for embeddings if this proves
    too brittle in practice. The spec is deliberately: `description` IS
    the trigger — there's no separate `triggers:` field. If you build
    create_skill (tools/memory_admin.py), have it call this module's
    _parse_text() to validate before writing, so a bad skill file can
    never be silently written to disk.

Common beginner mistakes
    - Loading every skill into every prompt regardless of relevance
      (wastes tokens, dilutes focus)
    - Skipping frontmatter validation and silently loading a malformed
      skill file
    - Re-scanning the filesystem on every single call instead of caching
      — or caching forever and never noticing a skill was added/edited
      mid-session (the mtime signature below solves both at once)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKILLS_DIRS = [
    Path("skills")
]  # skills/community/ is picked up too — rglob is recursive


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path


def _parse_text(text: str, path: Path) -> Skill | None:
    """Validates one SKILL.md's content. Returns None (never raises) for
    anything malformed — a broken skill file should be silently skipped
    by the loader, not crash the whole app on startup.

    The regex expects exactly:
        ---
        name: ...
        description: ...
        ---
        (body text)

    front.splitlines() + partition(":") turns each "key: value" line
    into a (key, value) pair — a hand-rolled parser instead of a real
    YAML library, on purpose: skill frontmatter is meant to be simple
    enough that this is genuinely all it needs.
    """
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return None

    front, body = match.groups()
    fields = {
        k.strip(): v.strip().strip("'\"")
        for k, _, v in (
            line.partition(":") for line in front.splitlines() if ":" in line
        )
    }

    # `description` is not optional metadata — it IS the trigger match()
    # uses below, so a skill without one can never be found.
    if "name" not in fields or "description" not in fields:
        return None

    return Skill(fields["name"], fields["description"], body.strip(), path)


def _parse(path: Path) -> Skill | None:
    return _parse_text(path.read_text(encoding="utf-8"), path)


class SkillLoader:
    """Holds the currently-loaded skills in memory and knows when to
    refresh them. A free function couldn't do this cleanly — refresh()
    needs somewhere to keep `self.skills` and the last-seen `self._sig`
    between calls, rather than either re-scanning disk on every match()
    call (slow) or caching forever and missing a skill someone just
    created mid-session (stale).
    """

    def __init__(self, dirs: list[Path] | None = None):
        self.dirs = dirs if dirs is not None else SKILLS_DIRS
        self.skills: list[Skill] = []
        self._sig: tuple = ()
        self.refresh()

    def _scan_sig(self) -> tuple:
        """A cheap fingerprint of every skill file's path + last-modified
        time. Comparing two of these tuples is much cheaper than
        re-reading and re-parsing every file just to check "did anything
        change?" — that's the whole trick behind hot-reloading.
        """
        sig = []
        for d in self.dirs:
            if d.is_dir():
                for f in sorted(d.rglob("*.md")):
                    sig.append((str(f), f.stat().st_mtime))
        return tuple(sig)

    def refresh(self) -> None:
        """Re-scans every configured directory and reloads all valid
        skills. Invalid files are parsed, get None back, and are simply
        left out of self.skills — no exception, no crash.
        """
        self.skills = []
        for d in self.dirs:
            if not d.is_dir():
                continue
            for f in sorted(d.rglob("*.md")):
                skill = _parse(f)
                if skill:
                    self.skills.append(skill)
        self._sig = self._scan_sig()

    def match(self, message: str, max_skills: int = 2) -> list[Skill]:
        """Transparent trigger: keyword overlap between the message and
        each skill's name + description. Requires at least 2 shared
        words (not just 1) so that one generic overlapping word — "the",
        "interview appearing in five different skills — doesn't cause a
        false match on its own.

        Before scoring, checks whether any skill file changed since the
        last refresh() (new file, edited file, deleted file) and reloads
        automatically if so — this is what lets a skill written mid-
        conversation (via a future create_skill tool) become usable on
        the very next turn, without restarting the app.
        """
        if self._scan_sig() != self._sig:
            self.refresh()

        msg_words = set(re.findall(r"[a-z0-9]{3,}", message.lower()))
        scored = []
        for skill in self.skills:
            skill_words = set(
                re.findall(
                    r"[a-z0-9]{3,}", (skill.name + " " + skill.description).lower()
                )
            )
            overlap = len(msg_words & skill_words)
            if overlap >= 2:
                scored.append((overlap, skill))

        scored.sort(key=lambda pair: -pair[0])
        return [skill for _, skill in scored[:max_skills]]
