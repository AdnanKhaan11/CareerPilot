"""
Purpose
    Download a SKILL.md from a URL and install it into
    skills/<name>/SKILL.md — the same directory-per-skill layout
    memory/procedural/skill_loader.py actually scans for.

Responsibilities
    - Turn a GitHub/Gist page URL into its raw-content URL
    - Fetch it, validate its frontmatter, write it into place

Inputs:  a URL (argv[1])
Outputs: a new file under skills/<name>/SKILL.md

Dependencies:   urllib (stdlib only — no extra dependency)
Related files:  skills/TEMPLATE.md, memory/procedural/skill_loader.py
                (its _parse_text is reused directly, not reimplemented)
Design pattern: CLI utility script
Difficulty:     beginner

Agentic AI concepts used: procedural memory distribution/sharing
Software engineering concepts used: validate untrusted input before
  writing it to disk; dependency-injected fetch for testability

Common beginner mistakes
    - Installing a skill without validating its frontmatter, silently
      breaking skill_loader.py's parsing later
    - Writing a flat skills/<name>.md file instead of skills/<name>/SKILL.md
      — the loader only ever looks for files literally named SKILL.md
    - Reimplementing frontmatter validation here instead of reusing
      skill_loader.py's own _parse_text — two copies of that logic
      could silently drift apart
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path
from typing import Callable

from careerpilot.memory.procedural.skill_loader import _parse_text

SKILLS_DIR = Path("skills")


def _raw_url(url: str) -> str:
    if "github.com" in url and "/blob/" in url:
        return url.replace("github.com", "raw.githubusercontent.com").replace(
            "/blob/", "/"
        )
    if "gist.github.com" in url and not url.endswith("/raw"):
        return url.rstrip("/") + "/raw"
    return url


def _fetch(url: str, timeout: float = 15.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def install(url: str, fetch: Callable[[str], str] = _fetch) -> str:
    raw_url = _raw_url(url)
    text = fetch(raw_url)

    skill = _parse_text(text, Path(raw_url))
    if skill is None:
        raise ValueError(
            "Invalid skill: SKILL.md needs YAML frontmatter with `name` and "
            "`description`. See skills/TEMPLATE.md for the expected shape."
        )

    dest = SKILLS_DIR / skill.name / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")

    return (
        f"Installed '{skill.name}' -> {dest}\n"
        f"  {skill.description}\n"
        f"It loads on the next message — no restart needed. Read it first: skills are instructions."
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts/skill_install.py <url-to-SKILL.md>")
        return
    url = sys.argv[1]
    print(f"Fetching {_raw_url(url)}")
    try:
        result = install(url)
    except Exception as exc:
        print(f"error: {exc}")
        return
    print(result)


if __name__ == "__main__":
    main()
