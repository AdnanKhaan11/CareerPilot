"""
Purpose
    The terminal entry point for talking to CareerPilot — now fully
    wired to tracing, usage recording, memory mirroring, and
    consolidation, none of which were actually connected to anything
    before this.

Responsibilities
    - Read user input from stdin in a loop
    - Build working memory for the turn via runtime/session.py
    - Call loop/agent.py's run_loop with a combined tracing+usage observer
    - Regenerate MEMORY.md after each turn
    - Track a turn counter and trigger consolidation at threshold,
      never resetting the counter on a failed consolidation

Related files:  ops/tracing.py, ops/usage.py, memory/memory_mirror.py,
                memory/consolidation.py — all of these existed and were
                tested in isolation, but nothing called any of them
                until this wiring
Design pattern: Gateway / thin adapter
"""

from __future__ import annotations

from careerpilot.config.settings import settings
from careerpilot.runtime.session import build_working_memory
from careerpilot.loop.agent import run_loop
from careerpilot.loop.models import get_client
from careerpilot.tools.registry import build_default_registry
from careerpilot.ops.tracing import make_observer
from careerpilot.ops.usage import record_usage
from careerpilot.memory.memory_mirror import regenerate_memory_md
from careerpilot.memory.consolidation import (
    maybe_consolidate,
    consolidate,
    ConsolidationError,
)


def _build_observer():
    """Combines tracing and usage recording into one Observer, since
    both need the same "llm" event.
    """
    trace = make_observer()

    def observer(kind: str, event: dict) -> None:
        trace(kind, event)
        if kind == "llm":
            usage = event.get("usage") or {}
            record_usage(
                model=settings.model,
                input_tokens=usage.get("in", 0),
                output_tokens=usage.get("out", 0),
            )

    return observer


def main() -> None:
    print("CareerPilot — your job-search co-pilot. Ctrl+C to quit.\n")

    client = get_client(settings)
    tools = build_default_registry()
    messages: list[dict] = []
    observer = _build_observer()

    chats_since_last_consolidation = 0

    while True:
        try:
            user_input = input("you > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nbye!")
            break

        if not user_input:
            continue

        system_prompt, messages = build_working_memory(user_input, messages)

        result = run_loop(
            client=client,
            model=settings.model,
            system=system_prompt,
            messages=messages,
            tools=tools,
            max_iterations=settings.max_iterations,
            observer=observer,
        )

        print(f"careerpilot > {result.reply}\n")

        regenerate_memory_md()

        chats_since_last_consolidation += 1
        if maybe_consolidate(chats_since_last_consolidation):
            try:
                consolidate(messages, client=client)
                chats_since_last_consolidation = (
                    0  # only reset on success — loss-safety
                )
            except ConsolidationError:
                pass  # same batch gets retried next turn; nothing is lost


if __name__ == "__main__":
    main()
