"""
Purpose
    Append-only ledger of every LLM call's token usage — a "spend is
    permanent" record that survives demo_seed.py resets and outlives
    any one session.

Responsibilities
    - record_usage(model, input_tokens, output_tokens) — append one line
    - summarize_usage() — total usage overall, by day, and by model

Inputs:  usage numbers from each loop iteration's LLM response
Outputs: appended lines in .careerpilot/usage.jsonl; a summary dict

Dependencies:   json, pathlib, datetime
Related files:  loop/agent.py (call record_usage on every LLM response)
Design pattern: Append-only event log
Difficulty:     beginner

Agentic AI concepts used: cost observability
Software engineering concepts used: never delete/mutate historical
  records — append only; best-effort writes (same reasoning as
  ops/tracing.py)

Future implementation notes
    Wire per-provider token pricing into summarize_usage() so cost is
    a real dollar estimate, not just a token count.

Common beginner mistakes
    - Resetting/deleting this file on a demo reset — it must survive resets
    - Letting one corrupted line in the ledger fail the entire summary
      instead of just skipping that line
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

USAGE_LOG_PATH = Path(".careerpilot/usage.jsonl")


def record_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """Appends one JSON line for a single LLM call. Best-effort — a
    failed write is swallowed, same reasoning as ops/tracing.py.
    """
    USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(),
        "model": model,
        "in": input_tokens,
        "out": output_tokens,
    }
    try:
        with USAGE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # best-effort — see docstring above


def summarize_usage() -> dict:
    """Totals the entire ledger overall, by day, and by model. A
    corrupted line is skipped, not fatal to the whole summary.
    """
    totals = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "by_day": {},
        "by_model": {},
    }

    if not USAGE_LOG_PATH.exists():
        return totals

    for line in USAGE_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # skip a corrupted line, don't fail the whole summary

        input_tokens = entry.get("in", 0)
        output_tokens = entry.get("out", 0)
        model = entry.get("model", "unknown")
        day = entry.get("ts", "")[:10]

        totals["total_input_tokens"] += input_tokens
        totals["total_output_tokens"] += output_tokens

        day_bucket = totals["by_day"].setdefault(
            day, {"input_tokens": 0, "output_tokens": 0}
        )
        day_bucket["input_tokens"] += input_tokens
        day_bucket["output_tokens"] += output_tokens

        model_bucket = totals["by_model"].setdefault(
            model, {"input_tokens": 0, "output_tokens": 0}
        )
        model_bucket["input_tokens"] += input_tokens
        model_bucket["output_tokens"] += output_tokens

    return totals
