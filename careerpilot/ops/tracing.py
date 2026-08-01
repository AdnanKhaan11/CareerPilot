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

TRACE_DIR = Path(".careerpilot/traces")


def make_observer():
    """Returns a function matching loop.agent.Observer's signature that
    appends each event as one JSON line to today's trace file.

    Best-effort by design: a trace write that fails is swallowed rather
    than raised — losing one trace line is a real but minor loss;
    crashing the user's actual conversation over a logging failure
    would be a much worse trade.
    """
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    def observer(kind: str, event: dict) -> None:
        record = {"ts": datetime.now().isoformat(), "kind": kind, **event}
        trace_file = TRACE_DIR / f"{date.today().isoformat()}.jsonl"
        try:
            with trace_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass  # best-effort — see docstring above

    return observer
