"""Pure, dependency-free metrics derived from an in-memory trace graph."""

from __future__ import annotations

from typing import Any

from .trace_models import NodeCategory, NodeStatus, Trace


def compute_metrics(trace: Trace) -> dict[str, Any]:
    """Summarize latency, failures, counts, and declared token usage for a trace."""
    nodes = list(trace.nodes.values())
    durations = {node.node_id: node.duration_ms for node in nodes if node.duration_ms is not None}
    values = list(durations.values())
    slowest_id = max(durations, key=durations.get) if durations else None
    token_usage = _token_usage(trace)
    return {
        "total_duration_ms": trace.duration_ms,
        "node_durations_ms": durations,
        "slowest_node_id": slowest_id,
        "slowest_node_duration_ms": durations.get(slowest_id) if slowest_id else None,
        "average_latency_ms": sum(values) / len(values) if values else None,
        "failure_count": sum(node.status is NodeStatus.FAILED for node in nodes),
        "token_usage": token_usage,
        "tool_count": _category_count(trace, NodeCategory.TOOL),
        "memory_count": sum(_category_count(trace, category) for category in (NodeCategory.MEMORY, NodeCategory.WORKING_MEMORY)),
        "llm_count": _category_count(trace, NodeCategory.LLM),
    }


def _category_count(trace: Trace, category: NodeCategory) -> int:
    return sum(node.category is category for node in trace.nodes.values())


def _token_usage(trace: Trace) -> dict[str, int]:
    """Aggregate conventional token fields from trace and node metadata."""
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for metadata in [trace.metadata, *(node.metadata for node in trace.nodes.values())]:
        usage = metadata.get("token_usage", metadata) if isinstance(metadata, dict) else {}
        if not isinstance(usage, dict):
            continue
        for target, aliases in {
            "input_tokens": ("input_tokens", "prompt_tokens"),
            "output_tokens": ("output_tokens", "completion_tokens"),
            "total_tokens": ("total_tokens",),
        }.items():
            for alias in aliases:
                value = usage.get(alias)
                if isinstance(value, int) and not isinstance(value, bool):
                    totals[target] += value
                    break
    if not totals["total_tokens"]:
        totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return totals
