from __future__ import annotations

from fastapi import APIRouter

from careerpilot.gateway.dashboard.schemas import DashboardResponse
from careerpilot.gateway.dashboard.services.dashboard_service import build_dashboard

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
)


@router.get("", response_model=DashboardResponse)
def get_dashboard() -> DashboardResponse:
    return build_dashboard()
