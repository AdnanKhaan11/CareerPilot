"""
Purpose
    Decide, per turn, whether memory retrieval is worth doing at all —
    one of waku's two 'hero' design decisions: deciding WHETHER to
    retrieve before deciding WHAT to retrieve saves latency and avoids
    biasing answers with irrelevant memory.

Responsibilities
    - RetrievalGate: the interface any gate strategy implements
    - HeuristicRetrievalGate: the cheap, no-model-call default
    - LLMRetrievalGate: a stub for the "better version" — one small
      model call — only worth building once the heuristic proves
      insufficient
    - should_retrieve(message): thin module-level wrapper, so callers
      don't need to know a class is behind the decision at all

Inputs:  the raw user message string
Outputs: a boolean

Dependencies:   none for the heuristic; a cheap/small LLM client if/when
                LLMRetrievalGate is actually implemented
Related files:  runtime/session.py (the only real caller), memory/semantic/qdrant_store.py,
                memory/episodic/sqlite_store.py (what actually gets queried if this says yes)
Design pattern: Strategy — HeuristicRetrievalGate and LLMRetrievalGate
                are interchangeable behind one interface; swapping which
                one `_default_gate` points to is the only change needed
                anywhere in the codebase
Difficulty:     intermediate

Agentic AI concepts used: retrieval gate, context management
Software engineering concepts used: cheap fast-path before an expensive
  path, Strategy pattern for swappable decision logic

Future implementation notes
    Started with the heuristic, per the file's own original guidance —
    measure whether it's good enough in practice before reaching for
    LLMRetrievalGate. If you do build the LLM version: use the smallest,
    cheapest model your provider offers, and keep the prompt to a single
    yes/no question. If this gate call costs anywhere near what the main
    LLM call costs, it has failed at its one job.

Common beginner mistakes
    - Always returning True 'to be safe' — this defeats the entire
      point of the gate (this file's heuristic can genuinely return
      False, on purpose, for general-knowledge messages)
    - Making the gate itself as expensive as the main LLM call
    - A naive "any capitalized word = a name" heuristic misfires
      constantly on sentence-initial words and weekdays/months — both
      are explicitly filtered out below
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


class RetrievalGate(ABC):
    """Interface every gate implementation follows. runtime/session.py
    only ever calls .should_retrieve(message) — it never knows or cares
    whether a heuristic or a real LLM call is behind it.
    """

    @abstractmethod
    def should_retrieve(self, message: str) -> bool: ...


# Words that suggest the message is asking about something that already
# happened, or something specific to the user's job search — both are
# signals that retrieving stored memory could actually help.
_MEMORY_TRIGGER_WORDS = {
    "remember",
    "recall",
    "remind",
    "reminded",
    "before",
    "previously",
    "again",
    "last",
    "earlier",
    "still",
    "already",
    "mentioned",
    "said",
    "told",
    "company",
    "companies",
    "application",
    "applications",
    "applied",
    "interview",
    "interviews",
    "offer",
    "offers",
    "status",
    "follow",
    "followup",
    "notes",
    "note",
    "resume",
    "cv",
}

# Capitalized words that would otherwise trigger the "probable proper
# noun" check below as false positives — capitalized for grammar reasons
# (sentence start, "I"), not because they're a company/person name.
_CAPITALIZED_FALSE_POSITIVES = {
    "i",
    "i'm",
    "i've",
    "i'll",
    "i'd",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}


def _contains_trigger_word(message: str) -> bool:
    words = set(re.findall(r"[a-z']+", message.lower()))
    return bool(words & _MEMORY_TRIGGER_WORDS)


def _contains_probable_proper_noun(message: str) -> bool:
    """A cheap proxy for "this message names a specific company/person":
    any capitalized word that ISN'T the first word (capitalized purely
    by grammar) and isn't a known false positive.
    """
    tokens = message.split()
    for i, token in enumerate(tokens):
        if i == 0:
            continue
        cleaned = token.strip(".,!?;:\"'()").strip()
        if not cleaned or not cleaned[0].isupper() or not cleaned.isalpha():
            continue
        if cleaned.lower() in _CAPITALIZED_FALSE_POSITIVES:
            continue
        return True
    return False


class HeuristicRetrievalGate(RetrievalGate):
    """Cheapest possible version: no model call at all, just word
    matching — cheap enough that running it on every single turn costs
    nothing worth measuring, which is the whole point of a gate: it must
    be dramatically cheaper than the decision it's protecting.
    """

    def should_retrieve(self, message: str) -> bool:
        return _contains_trigger_word(message) or _contains_probable_proper_noun(
            message
        )


class LLMRetrievalGate(RetrievalGate):
    """Stub for the 'better version': one cheap/small model call that
    answers yes/no. Not implemented yet — try the heuristic above first,
    and only reach for this once it's shown to be insufficient in
    practice.
    """

    def should_retrieve(self, message: str) -> bool:
        raise NotImplementedError(
            "LLM-based gate not built yet — see the class docstring for when to reach for this."
        )


# Module-level default: the heuristic gate, used by anything that just
# wants a yes/no answer without knowing which strategy produced it.
_default_gate: RetrievalGate = HeuristicRetrievalGate()


def should_retrieve(message: str) -> bool:
    """Thin wrapper so runtime/session.py can call should_retrieve(message)
    directly — same convenience pattern as get_store() in qdrant_store.py.
    """
    return _default_gate.should_retrieve(message)
