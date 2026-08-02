"""Read-only dashboard endpoints for persisted runtime traces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from careerpilot.ops.trace_export import exporter_for
from careerpilot.ops.trace_metrics import compute_metrics
from careerpilot.ops.trace_models import Trace
from careerpilot.ops.trace_storage import JsonlStorage

router = APIRouter(prefix="/traces", tags=["traces"])
_storage = JsonlStorage()


@router.get("")
def list_traces() -> list[dict[str, Any]]:
    """Return lightweight summaries of persisted traces, newest first."""
    return [_summary(trace) for trace in _storage.list_traces()]


@router.get("/{trace_id}")
def get_trace(trace_id: str) -> dict[str, Any]:
    """Return a complete persisted trace graph."""
    return _load_trace(trace_id).to_dict()


@router.get("/{trace_id}/metrics")
def get_trace_metrics(trace_id: str) -> dict[str, Any]:
    """Return metrics calculated by the tracing subsystem."""
    return compute_metrics(_load_trace(trace_id))


@router.get("/{trace_id}/export/json")
def export_trace_json(trace_id: str) -> Response:
    """Return a trace through the registered JSON exporter."""
    return _export_trace(trace_id, "json", "application/json")


@router.get("/{trace_id}/export/html")
def export_trace_html(trace_id: str) -> Response:
    """Return a trace through the registered HTML exporter."""
    return _export_trace(trace_id, "html", "text/html")


def _load_trace(trace_id: str) -> Trace:
    """Load one trace or raise the standard dashboard 404 response."""
    trace = _storage.load_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return trace


def _summary(trace: Trace) -> dict[str, Any]:
    """Return the compact representation used by the traces list endpoint."""
    return {
        "trace_id": trace.trace_id,
        "started_at": trace.started_at.isoformat(),
        "finished_at": trace.finished_at.isoformat() if trace.finished_at else None,
        "duration_ms": trace.duration_ms,
        "status": trace.status.value,
        "node_count": len(trace.nodes),
    }


def _export_trace(trace_id: str, format_name: str, media_type: str) -> Response:
    """Run a registered exporter for a stored trace."""
    exporter = exporter_for(format_name)
    if exporter is None:
        raise HTTPException(status_code=404, detail="trace export format not found")
    return Response(content=exporter.export(_load_trace(trace_id)), media_type=media_type)
