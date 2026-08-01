"""
==========================================
Reference from Waku Agent
==========================================

Study these files before implementing this one:

    waku-agent/waku/gateway/voice.py (wake-word listener, Whisper STT, TTS)

Concepts to learn:

  - wake-word detection
  - speech-to-text
  - text-to-speech

Reason this file exists:

waku's voice gateway (wake word 'waku waku', Whisper STT, TTS via macOS
`say` or Kokoro) is real but genuinely optional infrastructure, not core
to either project's architecture. Listed here so nothing is silently
dropped, but intentionally left as a stub until the core loop/memory/tools
are solid — building voice I/O before the agent itself works well is a
common trap.

How Waku Agent uses this concept:

Wake word 'waku waku' (configurable), Whisper for STT, `say`/Kokoro for
TTS.

How CareerPilot will use this concept differently:

Same shape planned (wake word e.g. 'hey pilot'), but explicitly last on
the roadmap.

==========================================
"""
#
# Purpose
#     (Stub) Hands-free voice access to CareerPilot.
#
# Responsibilities
#     - Listen for a wake word
#     - Transcribe speech to text (e.g. Whisper)
#     - Run the same build_working_memory + run_loop path as cli.py
#     - Speak the reply back (TTS)
#
# Inputs:  microphone audio
# Outputs: spoken reply
#
# Dependencies:   a wake-word/STT/TTS stack — NOT YET CHOSEN
# Related files:  waku/gateway/voice.py (reference), gateway/cli.py
# Design pattern: Gateway
# Difficulty:     advanced
#
# Agentic AI concepts used: harness, multimodal I/O
# Software engineering concepts used: defer building infrastructure until the core is proven
#
# Future implementation notes
#     Build this last, after loop/memory/tools/evals are all working end to end
#     via the CLI.
#
# Common beginner mistakes
#     - Starting here before the core agent works — voice adds real complexity for zero architectural learning at this stage
#

from __future__ import annotations


def main() -> None:
    """TODO: deliberately not started yet — see the doc header above.

    Build this only after cli.py works end to end. When you do, reuse
    build_working_memory + run_loop exactly as cli.py and telegram.py do.
    """
    raise NotImplementedError("voice gateway intentionally deferred — see file header")


if __name__ == "__main__":
    main()
