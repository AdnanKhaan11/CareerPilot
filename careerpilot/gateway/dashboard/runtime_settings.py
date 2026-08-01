"""
Purpose
    Makes config/settings.py's Settings object runtime-mutable from the
    Settings page, without requiring a restart. .env still supplies the
    defaults; this file layers the user's live overrides on top and
    persists them to disk.

A note on storing API keys in a plain JSON file
    Deliberate, acceptable for a local-first, BYOK, single-user tool —
    no server, no other user, no network boundary to protect. Don't
    copy this pattern into a multi-user or hosted deployment without
    adding real secret storage. .careerpilot/ must stay out of git.

Common beginner mistakes
    - Mutating a COPY of `settings` instead of the shared instance
      every other module already imported
    - Echoing the real api_key value back in a response
"""

from __future__ import annotations

import json
from pathlib import Path

from careerpilot.config.settings import settings

RUNTIME_CONFIG_PATH = Path(".careerpilot/runtime_config.json")

EDITABLE_FIELDS = {
    "provider",
    "model",
    "api_key",
    "base_url",
    "embedding_provider",
    "embedding_model",
    "embedding_api_key",
    "job_search_api_key",
    "experimental_tools_enabled",
}


def load_overlay() -> None:
    if not RUNTIME_CONFIG_PATH.exists():
        return
    try:
        overrides = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    for key, value in overrides.items():
        if key in EDITABLE_FIELDS:
            setattr(settings, key, value)


def _persist() -> None:
    RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = {field: getattr(settings, field) for field in EDITABLE_FIELDS}
    RUNTIME_CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")


def apply_patch(patch: dict) -> None:
    for key, value in patch.items():
        if key in EDITABLE_FIELDS and value is not None:
            setattr(settings, key, value)
    _persist()


def clear_api_key() -> None:
    settings.api_key = ""
    _persist()


def clear_embedding_api_key() -> None:
    settings.embedding_api_key = None
    _persist()


def snapshot() -> dict:
    return {
        "provider": settings.provider,
        "model": settings.model,
        "has_api_key": bool(settings.api_key),
        "base_url": settings.base_url,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "has_embedding_api_key": bool(settings.embedding_api_key),
        "job_search_platforms": [],
        "job_search_default_location": None,
        "experimental_tools_enabled": settings.experimental_tools_enabled,
    }
