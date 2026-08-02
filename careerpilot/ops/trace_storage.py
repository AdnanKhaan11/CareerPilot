"""Pluggable, best-effort persistence for runtime trace snapshots."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from .trace_models import NodeCategory, NodeStatus, Trace, TraceNode


class TraceStorage(Protocol):
    """Persistence boundary used exclusively by :class:`TraceManager`."""

    def persist_trace(self, trace: Trace) -> None:
        """Persist a trace snapshot. Implementations must not raise."""

    def list_traces(self) -> list[Trace]:
        """Return the latest available snapshot for every stored trace."""

    def load_trace(self, trace_id: str) -> Trace | None:
        """Return a reconstructed trace snapshot when it exists."""

    def trace_exists(self, trace_id: str) -> bool:
        """Return whether a stored trace snapshot exists."""


class JsonlStorage:
    """Append trace snapshots to daily JSONL files under ``.careerpilot/traces``."""

    def __init__(self, directory: Path | str = ".careerpilot/traces") -> None:
        self.directory = Path(directory)

    def persist_trace(self, trace: Trace) -> None:
        """Append a complete snapshot; silently ignore all I/O/JSON failures."""
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{date.today().isoformat()}.jsonl"
            record = {"record_type": "trace_snapshot", "trace": trace.to_dict()}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=repr) + "\n")
        except Exception:
            pass

    def list_traces(self) -> list[Trace]:
        """Load the newest JSONL snapshot of each trace, newest first."""
        snapshots: dict[str, Trace] = {}
        for trace in self._read_traces():
            snapshots[trace.trace_id] = trace
        return sorted(snapshots.values(), key=lambda trace: trace.started_at, reverse=True)

    def load_trace(self, trace_id: str) -> Trace | None:
        """Load the latest JSONL snapshot for ``trace_id`` without raising."""
        match: Trace | None = None
        for trace in self._read_traces():
            if trace.trace_id == trace_id:
                match = trace
        return match

    def trace_exists(self, trace_id: str) -> bool:
        """Return whether any valid stored snapshot has ``trace_id``."""
        return self.load_trace(trace_id) is not None

    def _read_traces(self) -> list[Trace]:
        """Read valid trace snapshots once, skipping corrupt or legacy records."""
        traces: list[Trace] = []
        try:
            paths = sorted(self.directory.glob("*.jsonl"))
        except OSError:
            return traces

        for path in paths:
            try:
                with path.open(encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            record = json.loads(line)
                            if record.get("record_type") != "trace_snapshot":
                                continue
                            trace = _trace_from_dict(record.get("trace"))
                            if trace is not None:
                                traces.append(trace)
                        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                            continue
            except OSError:
                continue
        return traces


def _trace_from_dict(raw: Any) -> Trace | None:
    """Reconstruct a ``Trace`` graph from one persisted JSON-safe snapshot."""
    if not isinstance(raw, dict):
        return None
    try:
        trace_id = str(raw["trace_id"])
        started_at = _datetime_from_value(raw["started_at"])
        if started_at is None:
            return None
        trace = Trace(
            name=str(raw.get("name", "CareerPilot execution")),
            trace_id=trace_id,
            started_at=started_at,
            finished_at=_datetime_from_value(raw.get("finished_at")),
            status=NodeStatus(raw.get("status", NodeStatus.RUNNING.value)),
            metadata=dict(raw.get("metadata") or {}),
            tags=set(raw.get("tags") or ()),
            session_id=raw.get("session_id"),
            conversation_id=raw.get("conversation_id"),
            user_id=raw.get("user_id"),
        )
        raw_nodes = raw.get("nodes") or {}
        if not isinstance(raw_nodes, dict):
            return None
        for node_id, node_raw in raw_nodes.items():
            node = _node_from_dict(node_raw, trace_id)
            if node is None:
                return None
            trace.nodes[str(node_id)] = node
        return trace
    except (KeyError, TypeError, ValueError):
        return None


def _node_from_dict(raw: Any, trace_id: str) -> TraceNode | None:
    """Reconstruct one node from a persisted trace graph."""
    if not isinstance(raw, dict):
        return None
    try:
        return TraceNode(
            name=str(raw["name"]),
            category=NodeCategory(raw["category"]),
            trace_id=trace_id,
            node_id=str(raw["node_id"]),
            parent_node_id=raw.get("parent_node_id"),
            status=NodeStatus(raw.get("status", NodeStatus.WAITING.value)),
            started_at=_datetime_from_value(raw.get("started_at")),
            finished_at=_datetime_from_value(raw.get("finished_at")),
            input=raw.get("input"),
            output=raw.get("output"),
            metadata=dict(raw.get("metadata") or {}),
            error=raw.get("error"),
            children=list(raw.get("children") or ()),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _datetime_from_value(value: Any) -> datetime | None:
    """Parse persisted ISO-8601 timestamps, accepting absent optional values."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    return datetime.fromisoformat(value)
