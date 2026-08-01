"""
==========================================
Reference from Waku Agent
==========================================

Study these files before implementing this one:

    waku-agent/README.md — 'Connect MCP servers' section
    waku-agent/examples/mcp_demo_server.py

Concepts to learn:

  - Model Context Protocol
  - tool namespacing

Reason this file exists:

waku lets any MCP server's tools appear to the agent, namespaced
`<server>_<tool>`, via a simple JSON config — this whole integration point
was missing from the first pass.

How Waku Agent uses this concept:

.waku/mcp.json lists servers; their tools register into the same
ToolRegistry, namespaced.

How CareerPilot will use this concept differently:

Identical pattern: .careerpilot/mcp.json, tools registered as
mcp_<server>_<tool>.

==========================================
"""
#
# Purpose
#     Load MCP server configs and register their tools into the ToolRegistry,
#     namespaced.
#
# Responsibilities
#     - Read .careerpilot/mcp.json if present
#     - For each server, connect and fetch its tool list
#     - Register each as `mcp_<server>_<tool>` in the registry
#
# Inputs:  .careerpilot/mcp.json
# Outputs: registered Tool objects
#
# Dependencies:   an MCP client library
# Related files:  tools/registry.py, examples/mcp_demo_server.py
# Design pattern: Plugin loading / adapter
# Difficulty:     advanced
#
# Agentic AI concepts used: MCP, tool namespacing to avoid collisions
# Software engineering concepts used: graceful degradation if a server is unreachable
#
# Future implementation notes
#     Start with examples/mcp_demo_server.py locally before pointing at a real
#     third-party MCP server.
#
# Common beginner mistakes
#     - Letting one unreachable MCP server crash startup instead of skipping it with a warning
#

from __future__ import annotations

import json
from pathlib import Path

MCP_CONFIG_PATH = Path(".careerpilot/mcp.json")


def load_mcp_tools(registry) -> None:
    """TODO: if MCP_CONFIG_PATH exists, read {"servers": [...]}, connect
    to each, and registry.register(...) a Tool per remote tool, named
    f"mcp_{server_name}_{tool_name}". Skip (with a warning, not a crash)
    any server that fails to connect.
    """
    if not MCP_CONFIG_PATH.exists():
        return
    config = json.loads(MCP_CONFIG_PATH.read_text())  # noqa: F841 (TODO: use this)
    raise NotImplementedError
