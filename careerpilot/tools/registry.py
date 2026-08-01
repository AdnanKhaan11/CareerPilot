"""
==========================================
Reference from Waku Agent
==========================================

Study these files before implementing this one:

    waku-agent/waku/tools/registry.py

Concepts to learn:

  - tool calling schemas
  - dispatch/registry pattern
  - dependency injection

Reason this file exists:

The loop calls tools.schemas() and tools.execute(name, input) without
knowing what tools exist — this file is the dispatcher that makes tools
pluggable.

How Waku Agent uses this concept:

waku registers create_event, list_events, search_web, save_note, etc.
behind one registry.

How CareerPilot will use this concept differently:

CareerPilot registers log_application, update_status, search_jobs,
save_note instead.

==========================================
"""

#
# Purpose
#     Central registry: holds every tool's schema and how to execute it.
#
# Responsibilities
#     - Store a mapping of tool name -> (schema, callable)
#     - Expose schemas() for the LLM call
#     - Expose execute(name, args) for the loop to call
#
# Inputs:  tool registrations (name, JSON schema, function)
# Outputs: list of schemas; tool execution results (strings)
#
# Dependencies:   none beyond stdlib for the registry itself
# Related files:  tools/applications.py, tools/search_jobs.py, tools/notes.py, loop/agent.py
# Design pattern: Registry / Command dispatch
# Difficulty:     intermediate
#
# Agentic AI concepts used: function calling, JSON schema, structured output
# Software engineering concepts used: dependency injection, open/closed principle
#
# Future implementation notes
#     Add MCP-namespaced tools later (e.g. `mcp_<server>_<tool>`) without
#     changing this class's interface.
#
# Common beginner mistakes
#     - Hardcoding tool dispatch with if/elif chains in agent.py instead of a registry
#     - Forgetting to validate tool_input against the schema before executing
#

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict  # JSON schema — what arguments does this tool need?
    fn: Callable[[dict], str]


class ToolRegistry:
    def __init__(self) -> None:
        # maps tool name -> Tool object
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:

        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()  # give me only the values, ignore the keys
        ]

    def execute(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            # error string, not a raised exception — the model can read
            # this and react (e.g. try a different tool name), rather
            # than the whole loop crashing.
            return f"error: unknown tool '{name}'"
        return tool.fn(args)


def build_default_registry() -> ToolRegistry:
    """Registers every core tool. Experimental and MCP tools are added
    only if enabled/configured, matching waku's feature-flag pattern.

    TODO: each import below will fail until its tool module's functions
    are implemented (they currently raise NotImplementedError) — that's
    expected while you're working through the roadmap. Comment out
    what you haven't built yet rather than deleting the registration,
    so the TODO stays visible.
    """
    from careerpilot.config.settings import settings
    from careerpilot.tools.applications import (
        log_application_tool,
        update_application_status_tool,
        list_applications_tool,
    )
    from careerpilot.tools.search_jobs import search_jobs_tool
    from careerpilot.tools.notes import (
        save_company_note_tool,
        recall_similar_notes_tool,
    )
    from careerpilot.tools.memory_admin import (
        manage_memory_tool,
        update_profile_tool,
        create_skill_tool,
    )

    registry = ToolRegistry()

    # core domain tools
    registry.register(log_application_tool)
    registry.register(update_application_status_tool)
    registry.register(list_applications_tool)
    registry.register(search_jobs_tool)
    registry.register(save_company_note_tool)
    registry.register(recall_similar_notes_tool)

    # self-managed memory tools (see tools/memory_admin.py)
    registry.register(manage_memory_tool)
    registry.register(update_profile_tool)
    registry.register(create_skill_tool)

    # roadmap tools, off by default (see tools/experimental.py)
    if settings.experimental_tools_enabled:
        from careerpilot.tools.experimental import EXPERIMENTAL_TOOLS

        for tool in EXPERIMENTAL_TOOLS:
            registry.register(tool)

    # MCP server tools, only if .careerpilot/mcp.json exists (see tools/mcp_loader.py)
    from careerpilot.tools.mcp_loader import load_mcp_tools

    load_mcp_tools(registry)

    return registry
