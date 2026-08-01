"""GET/POST /skills — backed by the shared skill_writer util."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from careerpilot.memory.procedural.skill_loader import SkillLoader
from careerpilot.memory.procedural.skill_writer import write_skill, SKILLS_DIR
from careerpilot.gateway.dashboard.schemas import (
    SkillsResponse,
    SkillOut,
    SkillCreateRequest,
    SkillCreateResponse,
)

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=SkillsResponse)
def get_skills() -> SkillsResponse:
    loader = SkillLoader(dirs=[SKILLS_DIR])
    skills = [
        SkillOut(name=s.name, description=s.description, path=str(s.path))
        for s in loader.skills
    ]
    return SkillsResponse(skills=skills, count=len(skills))


@router.post("", response_model=SkillCreateResponse)
def create_skill(payload: SkillCreateRequest) -> SkillCreateResponse:
    try:
        skill = write_skill(
            name=payload.name,
            instructions=payload.instructions,
            trigger_keywords=payload.trigger_keywords,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SkillCreateResponse(
        skill=SkillOut(
            name=skill.name, description=skill.description, path=str(skill.path)
        )
    )
