"""
Purpose
    Holds chat history per conversation_id, in memory, for the current
    process's lifetime — the FULL internal agent-loop message format,
    separate from conversations_store.py's persisted turn history.
"""

from __future__ import annotations

import threading

_conversations: dict[str, list[dict]] = {}
_lock = threading.Lock()


def get(conversation_id: str) -> list[dict]:
    with _lock:
        return list(_conversations.get(conversation_id, []))


def set(conversation_id: str, messages: list[dict]) -> None:
    with _lock:
        _conversations[conversation_id] = messages


def exists(conversation_id: str) -> bool:
    with _lock:
        return conversation_id in _conversations


def delete(conversation_id: str) -> None:
    with _lock:
        _conversations.pop(conversation_id, None)
