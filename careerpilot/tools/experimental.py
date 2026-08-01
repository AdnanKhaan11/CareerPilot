"""
==========================================
Reference from Waku Agent
==========================================

Study these files before implementing this one:

    waku-agent/waku/tools/experimental.py

Concepts to learn:

  - deliberately unfinished features, shipped visibly rather than hidden

Reason this file exists:

waku ships roadmap tools as disabled-by-default skeletons (delegate_task,
run_command, browse_web, schedule_task) so the architecture diagram maps
to something real without overpromising. This file was missing entirely.

How Waku Agent uses this concept:

Off by default; WAKU_EXPERIMENTAL=1 registers them, each just reports
'coming soon'.

How CareerPilot will use this concept differently:

CareerPilot's equivalents: delegate_task (multi-agent, kept out to stay
single-agent/readable), draft_outreach_email (needs a real send
integration + safety review first), auto_apply (needs a real safety review
— auto-submitting applications is a big trust step, deliberately not
built).

==========================================
"""
#
# Purpose
#     Roadmap tools, registered only behind an experimental flag, that currently
#     just report 'coming soon'.
#
# Responsibilities
#     - Define schemas for planned-but-unbuilt tools
#     - Each fn returns a clear 'not implemented yet' message, never crashes
#
# Inputs:  whatever schema each stub declares
# Outputs: a 'coming soon' string
#
# Dependencies:   none yet
# Related files:  tools/registry.py (only registers these if CAREERPILOT_EXPERIMENTAL=1)
# Design pattern: Feature flag / visible skeleton
# Difficulty:     intermediate
#
# Agentic AI concepts used: multi-agent delegation (stubbed), roadmap transparency
# Software engineering concepts used: feature flags, don't ship half-working code as if it were done
#
# Future implementation notes
#     Build delegate_task only after the single-agent core is solid and
#     evaluated — don't reach for multi-agent to solve problems the loop
#     already solves.
#
# Common beginner mistakes
#     - Wiring an experimental tool into the default registry without the flag check
#

from __future__ import annotations

from careerpilot.tools.registry import Tool


def _coming_soon(name: str):
    def _fn(args: dict) -> str:
        return f"{name} is on the roadmap and not implemented yet."
    return _fn


delegate_task_tool = Tool(
    name="delegate_task",
    description="(experimental, disabled by default) Delegate a sub-task to another agent.",
    input_schema={"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]},
    fn=_coming_soon("delegate_task"),
)

draft_outreach_email_tool = Tool(
    name="draft_outreach_email",
    description="(experimental, disabled by default) Draft a cold outreach email to a recruiter/hiring manager.",
    input_schema={"type": "object", "properties": {"company": {"type": "string"}}, "required": ["company"]},
    fn=_coming_soon("draft_outreach_email"),
)

auto_apply_tool = Tool(
    name="auto_apply",
    description="(experimental, disabled by default) Automatically submit an application. Needs a real safety review before ever being enabled.",
    input_schema={"type": "object", "properties": {"job_url": {"type": "string"}}, "required": ["job_url"]},
    fn=_coming_soon("auto_apply"),
)

EXPERIMENTAL_TOOLS = [delegate_task_tool, draft_outreach_email_tool, auto_apply_tool]
