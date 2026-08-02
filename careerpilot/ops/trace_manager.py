"""The best-effort coordinator for CareerPilot's isolated tracing subsystem."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from .trace_export import exporter_for
from .trace_models import NodeCategory, NodeStatus, Trace, TraceNode
from .trace_storage import JsonlStorage, TraceStorage
from .trace_stream import TraceStream
from .trace_utils import utc_now


class TraceManager:
    """Own trace lifecycles while hiding persistence and publication details.

    All public lifecycle methods are intentionally best-effort: invalid IDs and
    downstream storage/stream failures resolve to ``None`` rather than affecting
    the application operation being observed.
    """

    def __init__(self, storage: TraceStorage | None = None, stream: TraceStream | None = None) -> None:
        self._storage = storage or JsonlStorage()
        self._stream = stream or TraceStream()
        self._traces: dict[str, Trace] = {}
        self._current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)
        self._current_node_id: ContextVar[str | None] = ContextVar("current_node_id", default=None)

    def create_trace(self, name: str = "CareerPilot execution", *, metadata: dict[str, Any] | None = None,
                     tags: set[str] | None = None, session_id: str | None = None,
                     conversation_id: str | None = None, user_id: str | None = None) -> Trace:
        """Create and make current a running execution trace."""
        trace = Trace(name=name, metadata=dict(metadata or {}), tags=set(tags or ()),
                      session_id=session_id, conversation_id=conversation_id, user_id=user_id)
        self._traces[trace.trace_id] = trace
        self._current_trace_id.set(trace.trace_id)
        self._publish_and_persist("trace.created", trace)
        return trace

    def finish_trace(self, trace_id: str | None = None) -> Trace | None:
        """Mark a trace successful unless it has already failed or been cancelled."""
        trace = self._trace(trace_id)
        if trace is None:
            return None
        if trace.status in (NodeStatus.RUNNING, NodeStatus.WAITING):
            trace.status = NodeStatus.SUCCESS
        trace.finished_at = trace.finished_at or utc_now()
        self._publish_and_persist("trace.finished", trace)
        return trace

    def cancel_trace(self, trace_id: str | None = None) -> Trace | None:
        """Mark a trace cancelled and finish any active duration measurement."""
        trace = self._trace(trace_id)
        if trace is None:
            return None
        trace.status, trace.finished_at = NodeStatus.CANCELLED, utc_now()
        self._publish_and_persist("trace.cancelled", trace)
        return trace

    def create_node(self, name: str, category: NodeCategory, *, trace_id: str | None = None,
                    parent_node_id: str | None = None, input: Any = None,
                    metadata: dict[str, Any] | None = None) -> TraceNode | None:
        """Add a waiting node to a trace, defaulting to the current node as parent."""
        trace = self._trace(trace_id)
        if trace is None:
            return None
        parent_id = parent_node_id if parent_node_id is not None else self._current_node_id.get()
        if parent_id is not None and parent_id not in trace.nodes:
            parent_id = None
        node = TraceNode(name=name, category=category, trace_id=trace.trace_id,
                         parent_node_id=parent_id, input=input, metadata=dict(metadata or {}))
        trace.nodes[node.node_id] = node
        if parent_id:
            trace.nodes[parent_id].children.append(node.node_id)
        self._publish_and_persist("node.created", trace, node)
        return node

    def start_node(self, node_id: str, *, trace_id: str | None = None) -> TraceNode | None:
        """Start a node and make it current in this execution context."""
        trace, node = self._node(node_id, trace_id)
        if node is None or trace is None:
            return None
        node.status, node.started_at = NodeStatus.RUNNING, node.started_at or utc_now()
        self._current_node_id.set(node.node_id)
        self._publish_and_persist("node.started", trace, node)
        return node

    def finish_node(self, node_id: str, output: Any = None, *, trace_id: str | None = None) -> TraceNode | None:
        """Mark a node successful and retain its observed output."""
        return self._complete_node(node_id, NodeStatus.SUCCESS, output=output, trace_id=trace_id)

    def fail_node(self, node_id: str, error: Any = None, *, trace_id: str | None = None) -> TraceNode | None:
        """Mark a node failed and retain a safe error representation."""
        return self._complete_node(node_id, NodeStatus.FAILED, error=error, trace_id=trace_id)

    def add_metadata(self, values: dict[str, Any], *, trace_id: str | None = None,
                     node_id: str | None = None) -> Trace | TraceNode | None:
        """Merge metadata into a trace or selected/current node."""
        trace = self._trace(trace_id)
        if trace is None:
            return None
        node = trace.nodes.get(node_id or self._current_node_id.get() or "")
        target: Trace | TraceNode = node or trace
        target.metadata.update(values)
        self._publish_and_persist("metadata.added", trace, node)
        return target

    def add_tag(self, tag: str, *, trace_id: str | None = None) -> Trace | None:
        """Attach a classification tag to a trace."""
        trace = self._trace(trace_id)
        if trace is None:
            return None
        trace.tags.add(tag)
        self._publish_and_persist("tag.added", trace)
        return trace

    def record_error(self, error: Any, *, trace_id: str | None = None,
                     node_id: str | None = None) -> Trace | TraceNode | None:
        """Record an error on a node when available, otherwise on trace metadata."""
        trace = self._trace(trace_id)
        if trace is None:
            return None
        node = trace.nodes.get(node_id or self._current_node_id.get() or "")
        if node:
            node.error, node.status, node.finished_at = error, NodeStatus.FAILED, utc_now()
            self._publish_and_persist("node.failed", trace, node)
            return node
        trace.metadata["error"] = error
        trace.status, trace.finished_at = NodeStatus.FAILED, utc_now()
        self._publish_and_persist("trace.failed", trace)
        return trace

    def current_trace(self) -> Trace | None:
        """Return the trace associated with this context, if one exists."""
        return self._trace(None)

    def current_node(self) -> TraceNode | None:
        """Return the current context node, if it remains part of the trace."""
        trace = self.current_trace()
        return trace.nodes.get(self._current_node_id.get() or "") if trace else None

    def export_trace(self, format_name: str = "json", *, trace_id: str | None = None) -> str | None:
        """Export a trace in a supported format; exporter failures are swallowed."""
        trace, exporter = self._trace(trace_id), exporter_for(format_name)
        if trace is None or exporter is None:
            return None
        try:
            return exporter.export(trace)
        except Exception:
            return None

    def _complete_node(self, node_id: str, status: NodeStatus, *, output: Any = None,
                       error: Any = None, trace_id: str | None = None) -> TraceNode | None:
        trace, node = self._node(node_id, trace_id)
        if trace is None or node is None:
            return None
        node.status, node.finished_at = status, utc_now()
        if output is not None:
            node.output = output
        if error is not None:
            node.error = error
        if self._current_node_id.get() == node.node_id:
            self._current_node_id.set(node.parent_node_id)
        self._publish_and_persist("node.finished" if status is NodeStatus.SUCCESS else "node.failed", trace, node)
        return node

    def _trace(self, trace_id: str | None) -> Trace | None:
        return self._traces.get(trace_id or self._current_trace_id.get() or "")

    def _node(self, node_id: str, trace_id: str | None) -> tuple[Trace | None, TraceNode | None]:
        trace = self._trace(trace_id)
        return trace, trace.nodes.get(node_id) if trace else None

    def _publish_and_persist(self, event: str, trace: Trace, node: TraceNode | None = None) -> None:
        try:
            self._storage.persist_trace(trace)
        except Exception:
            pass
        try:
            payload: dict[str, Any] = {"trace": trace.to_dict()}
            if node:
                payload["node"] = node.to_dict()
            self._stream.publish(event, payload)
        except Exception:
            pass
