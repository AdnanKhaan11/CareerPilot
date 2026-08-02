"""Typed domain models for a complete CareerPilot runtime execution graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .trace_utils import duration_ms, new_id, to_primitive, utc_now


class NodeStatus(str, Enum):
    """Lifecycle states shared by traces and their individual nodes."""

    WAITING = "waiting"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeCategory(str, Enum):
    """Standard execution-graph categories for CareerPilot operations."""

    WORKING_MEMORY = "WorkingMemory"
    PLANNER = "Planner"
    LLM = "LLM"
    TOOL = "Tool"
    RETRIEVER = "Retriever"
    MEMORY = "Memory"
    EMBEDDING = "Embedding"
    RANKING = "Ranking"
    SAFETY = "Safety"
    APPLICATION = "Application"
    SYSTEM = "System"
    CUSTOM = "Custom"


@dataclass(slots=True)
class TraceNode:
    """One operation in a trace graph; children are referenced by node ID."""

    name: str
    category: NodeCategory
    trace_id: str
    node_id: str = field(default_factory=new_id)
    parent_node_id: str | None = None
    status: NodeStatus = NodeStatus.WAITING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Any = None
    children: list[str] = field(default_factory=list)

    @property
    def duration_ms(self) -> float | None:
        return duration_ms(self.started_at, self.finished_at)

    def to_dict(self) -> dict[str, Any]:
        """Return a serialization-safe representation of the node."""
        return {
            "node_id": self.node_id, "parent_node_id": self.parent_node_id,
            "trace_id": self.trace_id, "name": self.name,
            "category": self.category.value, "status": self.status.value,
            "started_at": to_primitive(self.started_at),
            "finished_at": to_primitive(self.finished_at),
            "duration_ms": self.duration_ms, "input": to_primitive(self.input),
            "output": to_primitive(self.output), "metadata": to_primitive(self.metadata),
            "error": to_primitive(self.error), "children": list(self.children),
        }


@dataclass(slots=True)
class Trace:
    """A complete, self-contained execution graph for one AI execution."""

    name: str = "CareerPilot execution"
    trace_id: str = field(default_factory=new_id)
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    status: NodeStatus = NodeStatus.RUNNING
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)
    session_id: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None
    nodes: dict[str, TraceNode] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        return duration_ms(self.started_at, self.finished_at)

    def to_dict(self) -> dict[str, Any]:
        """Return a serialization-safe graph snapshot."""
        return {
            "trace_id": self.trace_id, "name": self.name,
            "started_at": to_primitive(self.started_at),
            "finished_at": to_primitive(self.finished_at),
            "duration_ms": self.duration_ms, "status": self.status.value,
            "metadata": to_primitive(self.metadata), "tags": sorted(self.tags),
            "session_id": self.session_id, "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
        }
