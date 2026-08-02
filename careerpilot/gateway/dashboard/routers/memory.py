"""GET /memory/notes, GET/PUT /memory/profile"""

from __future__ import annotations

from fastapi import APIRouter, Query

from careerpilot.memory.semantic.qdrant_store import search_semantic
from careerpilot.memory.soul import load_profile, PROFILE_PATH
from careerpilot.gateway.dashboard.schemas import (
    NotesResponse,
    ProfileResponse,
    ProfileUpdateRequest,
)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/notes", response_model=NotesResponse)
def get_notes(query: str = Query(default="")) -> NotesResponse:
    results = search_semantic(query, top_k=20) if query else []

    return NotesResponse(
        notes=results,
        count=len(results),
    )


@router.get("/profile", response_model=ProfileResponse)
def get_profile() -> ProfileResponse:
    return ProfileResponse(content=load_profile())


@router.put("/profile", response_model=ProfileResponse)
def put_profile(payload: ProfileUpdateRequest) -> ProfileResponse:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(payload.content, encoding="utf-8")
    return ProfileResponse(content=payload.content)
