"""
Purpose
    Combine deterministic + judge eval results into one release
    verdict — gated on both independently, never averaged.

Responsibilities
    - run_release_gate(deterministic_pass_rate, judge_score) -> a
      verdict with both a boolean and a human-readable summary

Inputs:  eval suite results (pre-computed numbers)
Outputs: ReleaseVerdict(passed: bool, summary: str)

Dependencies:   none (deliberately — see design pattern note below)
Related files:  evals/deterministic, evals/judge
Design pattern: Facade over two independent eval suites — this file is
                only the decision logic, not a test runner; whatever
                collects the two suites' results computes these
                numbers and calls this
Difficulty:     advanced

Agentic AI concepts used: deterministic eval, LLM-as-judge
Software engineering concepts used: CI gating, fail-closed defaults

Common beginner mistakes
    - Averaging the two scores into one number instead of gating on
      both independently — a great judge score should never paper
      over a real correctness failure, or vice versa
    - Letting the judge score alone decide release readiness without
      the deterministic floor
    - Returning only a boolean with no human-readable explanation of
      WHICH suite failed — the summary field exists specifically for this
"""

from __future__ import annotations

from dataclasses import dataclass

JUDGE_THRESHOLD = 0.8


@dataclass
class ReleaseVerdict:
    passed: bool
    summary: str


def run_release_gate(
    deterministic_pass_rate: float, judge_score: float
) -> ReleaseVerdict:
    """Deterministic must be a full 100% (0/1 tests, no partial
    credit). Judge score must clear JUDGE_THRESHOLD. Both independently
    gate the result — see the module docstring for why.
    """
    deterministic_ok = deterministic_pass_rate >= 1.0
    judge_ok = judge_score >= JUDGE_THRESHOLD
    passed = deterministic_ok and judge_ok

    summary = (
        f"Deterministic: {'PASS' if deterministic_ok else 'FAIL'} "
        f"({deterministic_pass_rate:.0%})\n"
        f"Judge score:   {'PASS' if judge_ok else 'FAIL'} "
        f"({judge_score:.2f} >= {JUDGE_THRESHOLD})\n"
        f"Release gate:  {'PASS' if passed else 'FAIL'}"
    )

    return ReleaseVerdict(passed=passed, summary=summary)
