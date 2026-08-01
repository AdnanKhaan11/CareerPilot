"""GET/PATCH /settings, DELETE /settings/api-key, DELETE /settings/embedding-api-key"""

from __future__ import annotations

import json

from fastapi import APIRouter

from careerpilot.gateway.dashboard import runtime_settings
from careerpilot.gateway.dashboard.schemas import (
    SettingsResponse,
    SettingsOut,
    SettingsUpdateRequest,
    SimpleMessageResponse,
)
from careerpilot.tools.search_jobs import JOB_PREFS_PATH, load_job_search_preferences

router = APIRouter(prefix="/settings", tags=["settings"])


def _full_snapshot() -> SettingsOut:
    data = runtime_settings.snapshot()
    prefs = load_job_search_preferences()
    data["job_search_platforms"] = list(prefs.platforms)
    data["job_search_default_location"] = prefs.default_location
    return SettingsOut(**data)


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return SettingsResponse(settings=_full_snapshot())


@router.patch("", response_model=SettingsResponse)
def patch_settings(payload: SettingsUpdateRequest) -> SettingsResponse:
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)

    job_search_fields = {"job_search_platforms", "job_search_default_location"}
    settings_patch = {k: v for k, v in patch.items() if k not in job_search_fields}

    if settings_patch:
        runtime_settings.apply_patch(settings_patch)

    if "job_search_platforms" in patch or "job_search_default_location" in patch:
        current = load_job_search_preferences()
        platforms = patch.get("job_search_platforms", list(current.platforms))
        location = patch.get("job_search_default_location", current.default_location)
        JOB_PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        JOB_PREFS_PATH.write_text(
            json.dumps(
                {"platforms": platforms, "default_location": location}, indent=2
            ),
            encoding="utf-8",
        )

    return SettingsResponse(settings=_full_snapshot())


@router.delete("/api-key", response_model=SimpleMessageResponse)
def delete_api_key() -> SimpleMessageResponse:
    runtime_settings.clear_api_key()
    return SimpleMessageResponse(message="API key removed")


@router.delete("/embedding-api-key", response_model=SimpleMessageResponse)
def delete_embedding_api_key() -> SimpleMessageResponse:
    runtime_settings.clear_embedding_api_key()
    return SimpleMessageResponse(message="Embedding API key removed")
