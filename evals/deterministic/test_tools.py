"""
Purpose
    Plain pytest checks for "did the right tool fire / did it do the
    right thing" — 0 or 1, no model judges any of this.

Responsibilities
    - One test per tool-calling correctness guarantee that matters

Inputs:  the real tool functions, against isolated temp storage
Outputs: pytest pass/fail

Dependencies:   pytest, qdrant-client (for the in-memory client)
Related files:  evals/judge/test_reply_quality.py (the other half of the eval split)
Design pattern: Unit testing
Difficulty:     beginner

Agentic AI concepts used: deterministic eval
Software engineering concepts used: pytest, test isolation (a fresh
  temp SQLite file and a fresh in-memory Qdrant collection per test —
  neither test ever touches real .careerpilot/ state)

Future implementation notes
    Add a test the moment you fix a real bug — that's the discipline
    waku-agent's README calls out explicitly. The "Various Companies"
    placeholder-company bug is exactly this kind of case; it's now
    covered structurally by system_prompt.md's rules and by the judge
    suite's dedicated scenario for it, since it's a judgment call
    (reply quality), not a 0/1 mechanical fact this suite can check.

Common beginner mistakes
    - Using the real .careerpilot/state.db or a real Qdrant instance in
      tests instead of a temp/in-memory one — the isolated_stores
      fixture below exists specifically to prevent this
"""

from __future__ import annotations

import pytest

from careerpilot.config.settings import settings
from careerpilot.memory.episodic import sqlite_store
from careerpilot.memory.semantic import qdrant_store
from careerpilot.tools.applications import (
    log_application_tool,
    update_application_status_tool,
    list_applications_tool,
)
from careerpilot.tools.notes import save_company_note_tool, recall_similar_notes_tool
from careerpilot.tools.memory_admin import manage_memory_tool


class _FakeEmbeddingProvider:
    """Deterministic tests must never depend on a real embedding API or
    a downloaded model — that would make this suite slow, costly, and
    non-deterministic. This produces a fixed-size vector from a hash of
    each word, enough for SemanticStore's real upsert/search/delete
    logic to be exercised end to end without any network call.
    """

    DIMENSIONS = 16

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS

    def embed(self, text: str) -> list[float]:
        import hashlib

        vector = [0.0] * self.DIMENSIONS
        for word in set(text.lower().split()):
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIMENSIONS
            vector[idx] += 1.0
        norm = sum(v * v for v in vector) ** 0.5
        return [v / norm for v in vector] if norm else vector


@pytest.fixture(autouse=True)
def isolated_stores(tmp_path, monkeypatch):
    """Points episodic storage at a fresh temp SQLite file and semantic
    storage at a fresh in-memory Qdrant collection, per test.
    """
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "state.db"))
    sqlite_store.init_db()
    monkeypatch.setattr(settings, "qdrant_collection", "test_collection")

    from qdrant_client import QdrantClient

    fresh_client = QdrantClient(location=":memory:")
    fresh_store = qdrant_store.SemanticStore(
        client=fresh_client,
        collection_name="test_collection",
        dense_provider=_FakeEmbeddingProvider(),
    )
    monkeypatch.setattr(qdrant_store, "_client", fresh_client)
    monkeypatch.setattr(qdrant_store, "_store", fresh_store)

    yield


# ---------------------------------------------------------------------
# tools/applications.py
# ---------------------------------------------------------------------


def test_log_application_creates_a_real_row():
    result = log_application_tool.fn(
        {
            "company": "Acme AI",
            "role": "ML Engineer",
            "date_applied": "2026-07-01",
        }
    )
    assert "Logged application: Acme AI" in result

    rows = sqlite_store.list_applications()
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme AI"
    assert rows[0]["status"] == "applied"


def test_log_application_rejects_an_invalid_date_without_writing_a_row():
    result = log_application_tool.fn(
        {
            "company": "TechCorp",
            "role": "Data Scientist",
            "date_applied": "07/10/2026",
        }
    )
    assert result.startswith("error:")
    assert sqlite_store.list_applications() == []


def test_update_status_on_an_unknown_company_does_not_crash():
    result = update_application_status_tool.fn(
        {
            "company": "Nonexistent Co",
            "role": "Role",
            "new_status": "interview",
        }
    )
    assert (
        result == "No application found for Nonexistent Co — Role. Nothing was updated."
    )


def test_update_status_on_a_real_application_actually_changes_it():
    log_application_tool.fn(
        {"company": "Acme AI", "role": "ML Engineer", "date_applied": "2026-07-01"}
    )
    update_application_status_tool.fn(
        {"company": "Acme AI", "role": "ML Engineer", "new_status": "interview"}
    )

    rows = sqlite_store.list_applications()
    assert rows[0]["status"] == "interview"


def test_list_applications_filters_by_status_correctly():
    log_application_tool.fn(
        {"company": "Acme AI", "role": "ML Engineer", "date_applied": "2026-07-01"}
    )
    log_application_tool.fn(
        {"company": "TechCorp", "role": "Data Scientist", "date_applied": "2026-07-10"}
    )
    update_application_status_tool.fn(
        {"company": "Acme AI", "role": "ML Engineer", "new_status": "interview"}
    )

    interview_only = list_applications_tool.fn({"status_filter": "interview"})
    assert "Acme AI" in interview_only
    assert "TechCorp" not in interview_only


# ---------------------------------------------------------------------
# tools/notes.py
# ---------------------------------------------------------------------


def test_save_company_note_creates_a_real_qdrant_point():
    result = save_company_note_tool.fn(
        {"company": "Acme AI", "note": "Asked about my final year project"}
    )
    assert result.startswith("Saved note for Acme AI")

    recalled = recall_similar_notes_tool.fn({"query": "final year project"})
    assert "Acme AI" in recalled


def test_save_company_note_rejects_an_exact_duplicate():
    save_company_note_tool.fn(
        {"company": "Acme AI", "note": "Asked about my final year project"}
    )
    result = save_company_note_tool.fn(
        {"company": "Acme AI", "note": "Asked about my final year project"}
    )
    assert result.startswith("Already saved")


def test_recall_similar_notes_with_nothing_saved_returns_a_clean_message():
    result = recall_similar_notes_tool.fn({"query": "anything"})
    assert result == "No related notes found."


# ---------------------------------------------------------------------
# tools/memory_admin.py
# ---------------------------------------------------------------------


def test_manage_memory_forget_actually_deletes_the_note():
    save_company_note_tool.fn(
        {"company": "Acme AI", "note": "Asked about my final year project"}
    )
    result = manage_memory_tool.fn({"action": "forget", "target": "final year project"})
    assert "Forgot note for Acme AI" in result

    recalled = recall_similar_notes_tool.fn({"query": "final year project"})
    assert recalled == "No related notes found."


def test_manage_memory_forget_with_no_matching_note_does_not_crash():
    result = manage_memory_tool.fn(
        {"action": "forget", "target": "something never saved"}
    )
    assert result.startswith("No stored note matching")
