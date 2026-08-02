"""
Purpose
    The two chat endpoints, both backed by persisted conversations
    (conversations_store) instead of an in-memory-only dict.

Streaming events: start, text, tool, done
    "start" fires first, carrying the conversation object — this lets
    the frontend learn a brand new conversation's id/title while the
    reply is still streaming, instead of only at the end.
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from careerpilot.config.settings import settings
from careerpilot.loop.agent import run_loop
from careerpilot.loop.models import get_client
from careerpilot.ops.tracing import make_observer
from careerpilot.runtime.session import build_working_memory
from careerpilot.tools.registry import build_default_registry
from careerpilot.gateway.dashboard import session_store, conversations_store
from careerpilot.gateway.dashboard.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ConversationOut,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _load_history(conversation_id: str) -> list[dict]:
    history = session_store.get(conversation_id)
    if history:
        return history
    if conversations_store.exists(conversation_id):
        return conversations_store.get_turns_as_messages(conversation_id)
    return []


def _persist_turn(conversation_id: str, user_message: str, reply: str) -> dict:
    conversation = conversations_store.get_or_create(conversation_id, user_message)
    conversations_store.add_turn(conversation_id, "user", user_message)
    conversations_store.add_turn(conversation_id, "assistant", reply)
    return conversations_store.get_conversation(conversation_id) or conversation


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    history = _load_history(conversation_id)

    system_prompt, messages = build_working_memory(payload.message, history)
    client = get_client(settings)
    tools = build_default_registry()

    result = run_loop(
        client=client,
        model=settings.model,
        system=system_prompt,
        messages=messages,
        tools=tools,
        max_iterations=settings.max_iterations,
        observer=make_observer(),
    )

    session_store.set(conversation_id, messages)
    conversation = _persist_turn(conversation_id, payload.message, result.reply)

    return ChatResponse(
        conversation=ConversationOut(**conversation),
        message=ChatMessage(
            id=str(uuid.uuid4()),
            role="assistant",
            content=result.reply,
            created_at=datetime.now(timezone.utc).isoformat(),
        ),
    )


def _run_loop_producer(
    user_message: str, conversation_id: str, event_queue: queue.Queue
) -> None:
    try:
        conversation = conversations_store.get_or_create(conversation_id, user_message)
        event_queue.put(("start", {"conversation": conversation}))

        history = _load_history(conversation_id)
        system_prompt, messages = build_working_memory(user_message, history)
        client = get_client(settings)
        tools = build_default_registry()
        trace_observer = make_observer()

        def observer(kind: str, event: dict) -> None:
            trace_observer(kind, event)
            if kind == "text":
                event_queue.put(("text", {"delta": event["delta"]}))
            elif kind == "tool":
                event_queue.put(
                    (
                        "tool",
                        {
                            "tool": event["tool"],
                            "args": event["args"],
                            "status": "complete",
                            "output": event["output"],
                        },
                    )
                )

        result = run_loop(
            client=client,
            model=settings.model,
            system=system_prompt,
            messages=messages,
            tools=tools,
            max_iterations=settings.max_iterations,
            observer=observer,
            stream=True,
        )

        session_store.set(conversation_id, messages)
        conversations_store.add_turn(conversation_id, "user", user_message)
        conversations_store.add_turn(conversation_id, "assistant", result.reply)
        updated_conversation = conversations_store.get_conversation(conversation_id)

        event_queue.put(
            (
                "done",
                {
                    "conversation": updated_conversation,
                    "message": {
                        "id": str(uuid.uuid4()),
                        "role": "assistant",
                        "content": result.reply,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )
        )
    except Exception as exc:
        event_queue.put(("error", {"message": str(exc)}))
    finally:
        event_queue.put(None)


@router.post("/stream")
def chat_stream(payload: ChatRequest) -> StreamingResponse:
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    event_queue: queue.Queue = queue.Queue()

    thread = threading.Thread(
        target=_run_loop_producer,
        args=(payload.message, conversation_id, event_queue),
        daemon=True,
    )
    thread.start()

    def event_stream():
        while True:
            item = event_queue.get()
            if item is None:
                break
            event_type, data = item
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
