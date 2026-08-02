"""Portable trace exporters; future formats can implement ``TraceExporter``."""

from __future__ import annotations

import html
import json
from typing import Protocol

from .trace_models import Trace


class TraceExporter(Protocol):
    """A serialization format available through ``TraceManager.export_trace``."""

    def export(self, trace: Trace) -> str:
        """Return the exported trace representation."""


class JsonTraceExporter:
    """Export a trace graph as formatted JSON."""

    def export(self, trace: Trace) -> str:
        return json.dumps(trace.to_dict(), ensure_ascii=False, indent=2, default=repr)


class HtmlTraceExporter:
    """Export a self-contained, inspection-friendly HTML trace snapshot."""

    def export(self, trace: Trace) -> str:
        body = html.escape(JsonTraceExporter().export(trace))
        return ("<!doctype html><html><head><meta charset=\"utf-8\">"
                f"<title>Trace {html.escape(trace.trace_id)}</title></head>"
                f"<body><h1>{html.escape(trace.name)}</h1><pre>{body}</pre></body></html>")


def exporter_for(format_name: str) -> TraceExporter | None:
    """Resolve a built-in exporter, returning ``None`` for unsupported formats."""
    exporters: dict[str, TraceExporter] = {"json": JsonTraceExporter(), "html": HtmlTraceExporter()}
    return exporters.get(format_name.lower())
