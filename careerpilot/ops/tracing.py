"""
Purpose
    Append-only JSONL tracing of every loop event, wired in via an
    Observer callback — never by loop/agent.py importing this file
    directly.

Responsibilities
    - make_observer() -> a callable matching loop.agent.Observer

Inputs:  (kind: str, event: dict) from the loop
Outputs: lines appended to .careerpilot/traces/<date>.jsonl

Dependencies:   json, pathlib, datetime (stdlib only)
Related files:  loop/agent.py (Observer type)
Design pattern: Observer
Difficulty:     intermediate

Agentic AI concepts used: tracing
Software engineering concepts used: append-only logs, best-effort
  side effects (a failed trace write is swallowed, never raised — see
  the observer's docstring)

Future implementation notes
    Add an optional OTel exporter later — keep JSONL as the always-on
    default regardless.

Common beginner mistakes
    - Importing this module inside loop/agent.py directly instead of
      passing it in as an observer
    - Blocking the reply path on a slow/failed trace write — this
      catches and swallows any write failure specifically to avoid that
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .trace_manager import TraceManager
from .trace_models import NodeCategory

TRACE_DIR = Path(".careerpilot/traces")


def make_observer():
    """Returns a function matching loop.agent.Observer's signature that
    appends each event as one JSON line to today's trace file.

    Best-effort by design: a trace write that fails is swallowed rather
    than raised — losing one trace line is a real but minor loss;
    crashing the user's actual conversation over a logging failure
    would be a much worse trade.
    """
    manager = TraceManager()
    node_ids: dict[str, str] = {}

    def forward_to_manager(kind: str, event: dict) -> None:
        """Translate passive loop lifecycle events into manager operations."""
        try:
            if kind == "trace.start":
                manager.create_trace(metadata=dict(event))
            elif kind == "llm.start":
                node = manager.create_node("LLM", NodeCategory.LLM, input=dict(event))
                if node:
                    node_ids[event["operation_id"]] = node.node_id
                    manager.start_node(node.node_id)
            elif kind in ("llm.finish", "llm.fail"):
                node_id = node_ids.pop(event["operation_id"], None)
                if node_id:
                    if kind == "llm.finish":
                        manager.finish_node(node_id, dict(event))
                    else:
                        manager.fail_node(node_id, event.get("error"))
            elif kind == "tool.start":
                node = manager.create_node(
                    event.get("tool", "Tool"), NodeCategory.TOOL, input=dict(event)
                )
                if node:
                    node_ids[event["operation_id"]] = node.node_id
                    manager.start_node(node.node_id)
            elif kind in ("tool.finish", "tool.fail"):
                node_id = node_ids.pop(event["operation_id"], None)
                if node_id:
                    if kind == "tool.finish":
                        manager.finish_node(node_id, event.get("output"))
                    else:
                        manager.fail_node(node_id, event.get("error"))
            elif kind == "response.start":
                node = manager.create_node("Final Response", NodeCategory.APPLICATION)
                if node:
                    node_ids["response"] = node.node_id
                    manager.start_node(node.node_id)
            elif kind == "response.finish":
                node_id = node_ids.pop("response", None)
                if node_id:
                    manager.finish_node(node_id, event.get("reply"))
            elif kind == "trace.finish":
                manager.finish_trace()
            elif kind == "trace.fail":
                manager.record_error(event.get("error"))
        except Exception:
            pass

    def observer(kind: str, event: dict) -> None:
        try:
            forward_to_manager(kind, event)
            TRACE_DIR.mkdir(parents=True, exist_ok=True)
            record = {"ts": datetime.now().isoformat(), "kind": kind, **event}
            trace_file = TRACE_DIR / f"{date.today().isoformat()}.jsonl"
            with trace_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass  # best-effort — see docstring above

    return observer
