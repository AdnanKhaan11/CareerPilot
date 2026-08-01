"""
Purpose
    Scored, LLM-judged checks for reply quality/helpfulness — things
    that aren't 0/1, kept in a separate suite from the deterministic
    tests on purpose.

Responsibilities
    - _judge(...) — sends a scenario + reply + rubric to a judge model,
      returns (score, reasoning)
    - _run_scenario(...) — runs a user message through the real agent
      loop and real tool registry, returns the final reply
    - Three realistic scenarios, each asserting score >= JUDGE_THRESHOLD

Inputs:  scenario prompts + a rubric per scenario
Outputs: a score per scenario, gated against ops/release_gate.JUDGE_THRESHOLD

Dependencies:   a real, configured LLM provider (this suite makes real calls)
Related files:  ops/release_gate.py
Design pattern: LLM-as-judge
Difficulty:     advanced

Agentic AI concepts used: LLM-as-judge evaluation
Software engineering concepts used: keeping judged tests separate from
  unit tests; skipping cleanly (not failing) when prerequisites (a real
  API key) aren't met

Future implementation notes
    Three scenarios to start, per this file's own original guidance —
    scale up once these are solid. JUDGE_THRESHOLD is imported from
    ops/release_gate.py rather than redefined here, so the two files
    can never silently disagree on what "passing" means.

Common beginner mistakes
    - Mixing judged assertions into the deterministic suite
    - Hardcoding a second copy of the judge threshold instead of
      importing the one release_gate.py already defines
    - Letting a missing API key fail the whole test run instead of
      skipping this suite cleanly (pytestmark below handles this)
"""

from __future__ import annotations

import json

import pytest

from careerpilot.config.settings import settings
from careerpilot.loop.agent import run_loop
from careerpilot.loop.models import get_client
from careerpilot.ops.release_gate import JUDGE_THRESHOLD
from careerpilot.tools.registry import build_default_registry

pytestmark = pytest.mark.skipif(
    not settings.api_key,
    reason="evals/judge requires a real configured provider API key",
)

JUDGE_SYSTEM_PROMPT = (
    "You are a strict, fair evaluator of an AI job-search assistant's "
    "replies. Output ONLY valid JSON, nothing else, in exactly this "
    'shape: {"score": <float 0.0-1.0>, "reasoning": "<one sentence>"}.'
)

from pathlib import Path

SYSTEM_PROMPT_PATH = Path("prompts/system_prompt.md")


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return "You are CareerPilot, a job-search co-pilot."


def _judge(
    client,
    model: str,
    scenario: str,
    user_message: str,
    assistant_reply: str,
    rubric: str,
) -> tuple[float, str]:
    judge_prompt = (
        f"Scenario: {scenario}\n\n"
        f"User message: {user_message}\n\n"
        f"Assistant reply: {assistant_reply}\n\n"
        f"Rubric: {rubric}"
    )
    response = client.messages.create(
        model=model,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": judge_prompt}],
        tools=[],
        max_tokens=200,
    )
    raw_text = "".join(b.text for b in response.content if b.type == "text")
    parsed = json.loads(raw_text)
    return float(parsed["score"]), parsed.get("reasoning", "")


def _run_scenario(client, model: str, user_message: str) -> str:
    tools = build_default_registry()
    messages = [{"role": "user", "content": user_message}]
    result = run_loop(
        client=client,
        model=model,
        system=_load_system_prompt(),
        messages=messages,
        tools=tools,
        max_iterations=settings.max_iterations,
    )
    return result.reply


def test_interview_prep_for_a_role_never_logged_before():
    client = get_client(settings)
    reply = _run_scenario(
        client,
        settings.model,
        "I have a system design interview with Acme AI next week — how should I prepare?",
    )
    score, reasoning = _judge(
        client,
        settings.model,
        scenario="Interview prep for an unlogged role",
        user_message="I have a system design interview with Acme AI next week — how should I prepare?",
        assistant_reply=reply,
        rubric=(
            "Score 1.0 if the reply gives genuinely useful, specific system-design "
            "interview prep advice without requiring the user to log the application "
            "first. Score low if it refuses, deflects, or gives only generic filler."
        ),
    )
    assert score >= JUDGE_THRESHOLD, f"score={score}, reasoning={reasoning}"


def test_does_not_fabricate_a_specific_company_for_a_vague_request():
    client = get_client(settings)
    reply = _run_scenario(
        client, settings.model, "find me an internship, I'm open to anything"
    )
    score, reasoning = _judge(
        client,
        settings.model,
        scenario="Vague job search request",
        user_message="find me an internship, I'm open to anything",
        assistant_reply=reply,
        rubric=(
            "Score 1.0 if the reply searches or asks a clarifying question, and "
            "does NOT claim to have logged an application for a vague/placeholder "
            "company name. Score 0.0 if it fabricates or logs a fake company."
        ),
    )
    assert score >= JUDGE_THRESHOLD, f"score={score}, reasoning={reasoning}"


def test_follow_up_email_is_genuinely_usable():
    client = get_client(settings)
    reply = _run_scenario(
        client,
        settings.model,
        "write me a short follow-up email to send after my TechCorp interview",
    )
    score, reasoning = _judge(
        client,
        settings.model,
        scenario="Follow-up email drafting",
        user_message="write me a short follow-up email to send after my TechCorp interview",
        assistant_reply=reply,
        rubric=(
            "Score 1.0 if the reply is a genuinely usable, appropriately short "
            "follow-up email mentioning TechCorp. Score low if it's generic, too "
            "long, or fails to mention the company by name."
        ),
    )
    assert score >= JUDGE_THRESHOLD, f"score={score}, reasoning={reasoning}"
