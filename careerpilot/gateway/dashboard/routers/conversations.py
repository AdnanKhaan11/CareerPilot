"""
Purpose
    Conversation management: list, retrieve, rename, delete.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from careerpilot.gateway.dashboard import conversations_store, session_store
from careerpilot.gateway.dashboard.schemas import (
    ConversationsListResponse,
    ConversationOut,
    ConversationDetailResponse,
    ConversationTurnOut,
    ConversationRenameRequest,
    SimpleMessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationsListResponse)
def list_conversations() -> ConversationsListResponse:
    rows = conversations_store.list_conversations()
    return ConversationsListResponse(conversations=rows, count=len(rows))


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(conversation_id: str) -> ConversationDetailResponse:
    conversation = conversations_store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=404, detail=f"No conversation with id '{conversation_id}'."
        )
    turns = conversations_store.get_turns(conversation_id)
    return ConversationDetailResponse(
        conversation=ConversationOut(**conversation),
        turns=[ConversationTurnOut(**t) for t in turns],
    )


@router.patch("/{conversation_id}", response_model=ConversationDetailResponse)
def rename_conversation(
    conversation_id: str, payload: ConversationRenameRequest
) -> ConversationDetailResponse:
    renamed = conversations_store.rename_conversation(conversation_id, payload.title)
    if not renamed:
        raise HTTPException(
            status_code=404, detail=f"No conversation with id '{conversation_id}'."
        )
    conversation = conversations_store.get_conversation(conversation_id)
    turns = conversations_store.get_turns(conversation_id)
    return ConversationDetailResponse(
        conversation=ConversationOut(**conversation),
        turns=[ConversationTurnOut(**t) for t in turns],
    )


@router.delete("/{conversation_id}", response_model=SimpleMessageResponse)
def delete_conversation(conversation_id: str) -> SimpleMessageResponse:
    deleted = conversations_store.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"No conversation with id '{conversation_id}'."
        )
    session_store.delete(conversation_id)
    return SimpleMessageResponse(message="Conversation deleted")
