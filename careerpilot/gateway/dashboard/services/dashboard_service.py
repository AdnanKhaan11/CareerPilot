from __future__ import annotations

from careerpilot.gateway.dashboard import runtime_settings

from careerpilot.gateway.dashboard.schemas import (
    DashboardResponse,
    DashboardStats,
    DashboardRecentApplication,
    DashboardRecentSkill,
)

from careerpilot.memory.episodic.sqlite_store import list_applications
from careerpilot.memory.procedural.skill_loader import SkillLoader
from careerpilot.memory.procedural.skill_writer import SKILLS_DIR


def build_dashboard() -> DashboardResponse:
    settings = runtime_settings.snapshot()

    applications = list_applications()

    loader = SkillLoader(
        dirs=[SKILLS_DIR],
    )

    return DashboardResponse(
        stats=DashboardStats(
            conversations=0,
            applications=len(applications),
            skills=len(loader.skills),
            memories=0,
        ),
        recent_applications=[
            DashboardRecentApplication(
                company=item.get("company", ""),
                role=item.get("role", ""),
                status=item.get("status", ""),
                date_applied=item.get("date_applied", ""),
            )
            for item in applications[:5]
        ],
        recent_skills=[
            DashboardRecentSkill(
                name=skill.name,
                description=skill.description,
            )
            for skill in loader.skills[:5]
        ],
        provider=settings["provider"],
        model=settings["model"],
    )
