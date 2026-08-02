"""Small, dependency-free helpers shared by the runtime tracing subsystem."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def new_id() -> str:
    """Return a collision-resistant identifier for a trace or trace node."""
    return str(uuid4())


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def duration_ms(started_at: datetime | None, finished_at: datetime | None) -> float | None:
    """Return elapsed milliseconds when both timestamps are available."""
    if started_at is None or finished_at is None:
        return None
    return max(0.0, (finished_at - started_at).total_seconds() * 1000)


def to_primitive(value: Any) -> Any:
    """Convert common Python values into JSON-safe values without raising.

    Arbitrary application inputs are deliberately represented by ``repr`` rather
    than allowed to break tracing serialization.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return to_primitive(asdict(value))
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_primitive(item) for item in value]
    try:
        return repr(value)
    except Exception:
        return "<unrepresentable>"
