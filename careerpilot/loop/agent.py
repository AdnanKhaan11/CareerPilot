"""THE LOOP — observe → reason → act → repeat. This file is the whole trick.

Every agent framework is ultimately this while-loop with more indirection:

    while not done:
        response = llm(messages, tools)          # reason
        if response asks for tools:
            results = run(tool_calls)            # act
            messages += results                  # observe
        else:
            done                                 # reply to the human

End-loop guardrails:
  1. the model stops asking for tools  → natural end of turn
  2. max_iterations reached            → hard stop, never spin forever

This file speaks exactly one dialect (Anthropic's Messages shape) and
never changes based on which provider is actually running underneath —
see loop/models.py for how every provider is made to look like that
one dialect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from careerpilot.tools.registry import ToolRegistry

LoopEvent = dict[str, Any]
Observer = Callable[[str, LoopEvent], None]


@dataclass
class LoopResult:
    reply: str
    tool_calls: list[LoopEvent] = field(default_factory=list)
    iterations: int = 0


def run_loop(
    client,
    model: str,
    system: str,
    messages: list[dict],
    tools: ToolRegistry,
    max_iterations: int = 10,
    max_tokens: int = 2048,
    observer: Observer | None = None,
    stream: bool = False,
) -> LoopResult:
    """Run one agent turn. `messages` is mutated in place — after the call it
    contains the full working memory of the turn (assistant thoughts, tool
    calls, tool results), which is exactly what gets traced.

    stream=True emits the assistant's text as it's generated
    (notify("text", {"delta": ...})), falling back to a single call for
    clients without streaming support.
    """
    notify = observer or (lambda kind, ev: None)
    result = LoopResult(reply="")
    can_stream = stream and hasattr(client.messages, "stream")
    notify("trace.start", {"model": model, "max_iterations": max_iterations})

    for iteration in range(1, max_iterations + 1):
        result.iterations = iteration

        # ---- reason: one LLM call with the current working memory
        response = None
        operation_id = f"llm:{iteration}"
        notify("llm.start", {"operation_id": operation_id, "iteration": iteration})
        if can_stream:
            try:
                with client.messages.stream(
                    model=model,
                    system=system,
                    messages=messages,
                    tools=tools.schemas(),
                    max_tokens=max_tokens,
                ) as s:
                    for delta in s.text_stream:
                        notify("text", {"delta": delta})
                    response = s.get_final_message()
            except Exception:
                response = None  # any streaming hiccup → fall back to one call
        if response is None:
            try:
                response = client.messages.create(
                    model=model,
                    system=system,
                    messages=messages,
                    tools=tools.schemas(),
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                notify("llm.fail", {"operation_id": operation_id, "error": repr(exc)})
                notify("trace.fail", {"error": repr(exc)})
                raise
        notify(
            "llm",
            {
                "iteration": iteration,
                "stop_reason": response.stop_reason,
                "usage": {
                    "in": response.usage.input_tokens,
                    "out": response.usage.output_tokens,
                },
            },
        )
        notify(
            "llm.finish",
            {
                "operation_id": operation_id,
                "iteration": iteration,
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            },
        )

        messages.append({"role": "assistant", "content": response.content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        # ---- guardrail 1: no tool calls → the model is talking to the human
        if not tool_uses:
            result.reply = "".join(b.text for b in response.content if b.type == "text")
            notify("response.start", {})
            notify("response.finish", {"reply": result.reply})
            notify("trace.finish", {})
            return result

        # ---- act: execute each requested tool; observe: feed results back
        tool_results = []
        for call in tool_uses:
            operation_id = f"tool:{iteration}:{call.id}"
            notify(
                "tool.start",
                {"operation_id": operation_id, "tool": call.name, "args": call.input},
            )
            try:
                output = tools.execute(call.name, call.input)
            except Exception as exc:
                notify("tool.fail", {"operation_id": operation_id, "error": repr(exc)})
                notify("trace.fail", {"error": repr(exc)})
                raise
            event = {"tool": call.name, "args": call.input, "output": output}
            result.tool_calls.append(event)
            notify("tool", event)
            notify(
                "tool.finish",
                {"operation_id": operation_id, "tool": call.name, "output": output},
            )
            tool_results.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": output}
            )
        messages.append({"role": "user", "content": tool_results})

    # ---- guardrail 2: ran out of iterations
    result.reply = "(I hit my iteration limit before finishing — try breaking the request into smaller steps.)"
    notify("response.start", {})
    notify("response.finish", {"reply": result.reply})
    notify("trace.finish", {})
    return result
