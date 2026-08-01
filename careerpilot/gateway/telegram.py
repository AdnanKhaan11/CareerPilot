"""
==========================================
Reference from Waku Agent
==========================================

Study these files before implementing this one:

    waku-agent/waku/gateway/telegram.py

Concepts to learn:

  - a second gateway proving the harness is decoupled from the loop
  - long-polling

Reason this file exists:

This gateway was missing from the first pass. It exists to prove 'one
brain, many doors' — texting the agent from your phone should need zero
changes to the loop.

How Waku Agent uses this concept:

Long-polls Telegram (no public URL/webhook needed); TELEGRAM_ALLOWED_USER
locks it to one user.

How CareerPilot will use this concept differently:

Identical shape, pointed at run_loop with the exact same tools/memory as
the CLI.

==========================================
"""
#
# Purpose
#     Let you message CareerPilot from your phone via a Telegram bot.
#
# Responsibilities
#     - Long-poll Telegram for new messages
#     - For each, build working memory + run_loop, same as cli.py
#     - Reply back via the Telegram API
#     - Optionally restrict to one allowed user ID
#
# Inputs:  Telegram updates (long polling)
# Outputs: Telegram messages sent back
#
# Dependencies:   a Telegram bot library (e.g. python-telegram-bot), TELEGRAM_BOT_TOKEN
# Related files:  waku/gateway/telegram.py (reference), gateway/cli.py (same shape)
# Design pattern: Gateway (same role as cli.py, different channel)
# Difficulty:     intermediate
#
# Agentic AI concepts used: harness, multi-channel access to one agent
# Software engineering concepts used: long-polling vs. webhooks trade-off
#
# Future implementation notes
#     Copy cli.py's message-building/loop-calling logic exactly — the only new
#     code here should be Telegram-specific I/O.
#
# Common beginner mistakes
#     - Duplicating loop/memory logic here instead of reusing exactly what cli.py calls
#

from __future__ import annotations

import os

from careerpilot.config.settings import settings
from careerpilot.loop.agent import run_loop
from careerpilot.loop.models import get_client
from careerpilot.runtime.session import build_working_memory
from careerpilot.tools.registry import build_default_registry

ALLOWED_USER = os.environ.get("TELEGRAM_ALLOWED_USER")


def main() -> None:
    """TODO: implement long-polling against the Telegram Bot API.

    For each incoming message (optionally filtered to ALLOWED_USER):
      1. system_prompt, messages = build_working_memory(text, history)
      2. result = run_loop(client, settings.model, system_prompt, messages, tools)
      3. send result.reply back to the chat

    This should be a thin wrapper — all the real logic already lives in
    runtime/session.py and loop/agent.py, exactly like gateway/cli.py.
    """
    raise NotImplementedError("TODO: wire up a Telegram bot library here")


if __name__ == "__main__":
    main()
