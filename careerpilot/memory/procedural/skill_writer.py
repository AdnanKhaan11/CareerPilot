"""
Purpose
    The one place that turns (name, trigger_keywords, instructions)
    into a real skills/<slug>/SKILL.md file. Both tools/memory_admin.py's
    create_skill tool and the API's POST /skills endpoint call this,
    instead of each having their own separate copy of the same logic.
"""

from __future__ import annotations

from pathlib import Path

from careerpilot.memory.procedural.skill_loader import Skill

SKILLS_DIR = Path("skills")


def slugify(name: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in name.lower())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def write_skill(
    name: str, instructions: str, trigger_keywords: list[str] | None = None
) -> Skill:
    slug = slugify(name)
    if not slug:
        raise ValueError(f"'{name}' has no usable characters for a skill name.")

    description = name
    if trigger_keywords:
        description = f"{name} ({', '.join(trigger_keywords)})"

    skill_path = SKILLS_DIR / slug / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    body = instructions.strip()
    content = f"---\nname: {slug}\ndescription: {description}\n---\n\n{body}\n"
    skill_path.write_text(content, encoding="utf-8")

    return Skill(name=slug, description=description, body=body, path=skill_path)
