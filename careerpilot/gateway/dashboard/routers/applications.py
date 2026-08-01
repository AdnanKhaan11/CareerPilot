"""GET /applications?status=<optional>"""

from __future__ import annotations

from fastapi import APIRouter, Query

from careerpilot.memory.episodic.sqlite_store import list_applications
from careerpilot.gateway.dashboard.schemas import ApplicationsResponse

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=ApplicationsResponse)
def get_applications(status: str | None = Query(default=None)) -> ApplicationsResponse:
    rows = list_applications(status_filter=status)
    return ApplicationsResponse(applications=rows)
