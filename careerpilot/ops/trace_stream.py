"""Framework-free, in-process publication of trace lifecycle events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Subscriber = Callable[[str, dict[str, Any]], None]


class TraceStream:
    """A best-effort event hub intended for a future dashboard adapter."""

    def __init__(self) -> None:
        self._subscribers: dict[str, Subscriber] = {}

    def subscribe(self, callback: Subscriber) -> str:
        """Register a callback and return its opaque subscription identifier."""
        from .trace_utils import new_id
        subscription_id = new_id()
        self._subscribers[subscription_id] = callback
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscriber if it is still registered."""
        self._subscribers.pop(subscription_id, None)

    def publish(self, event: str, payload: dict[str, Any]) -> None:
        """Notify subscribers; one slow or faulty consumer cannot affect tracing."""
        for callback in tuple(self._subscribers.values()):
            try:
                callback(event, payload)
            except Exception:
                pass
