"""
Purpose
    Let the agent save and later semantically recall notes about
    companies/interviews — self-managed memory, not read-only. This is
    the same "the agent manages its own memory" idea waku documents for
    save_note/manage_memory, applied to CareerPilot's domain.

Responsibilities
    - save_company_note(company, note) — embeds and stores a note,
      skipping it if it's an exact duplicate of one already saved
    - recall_similar_notes(query) — a thin wrapper the LLM can call
      explicitly, on top of the automatic retrieval gate in
      runtime/session.py

Inputs:  {'company': str, 'note': str} / {'query': str}
Outputs: confirmation string / list of similar past notes

Dependencies:   memory.semantic.qdrant_store, tools.applications.safe_tool
Related files:  memory/semantic/qdrant_store.py, memory/retrieval_gate.py,
                tools/applications.py (safe_tool is reused from here,
                not redefined — one error-handling decorator, not two)
Design pattern: Command (each function is one discrete action) + the
                same shared Decorator (safe_tool) used by
                tools/applications.py, rather than a second
                implementation of the same error-handling behavior
Difficulty:     intermediate

Agentic AI concepts used: semantic memory, embeddings, structured output
Software engineering concepts used: idempotency (an exact repeat of a
  note is detected and skipped, not silently duplicated), DRY (safe_tool
  imported, not copy-pasted)

Future implementation notes
    Deduplicates on EXACT text match after a company check, not a
    similarity threshold — see _find_exact_duplicate()'s docstring for
    why a threshold like "cosine similarity > 0.95" is the wrong tool
    here: it would risk silently dropping genuinely different notes
    that just happen to be phrased alike (two different interviewers
    both asking about "your final year project", say).

Common beginner mistakes
    - Embedding every tiny detail as a separate note instead of
      batching related context
    - Forgetting to store the company as payload metadata, so recall
      can't be filtered or deduplicated later — qdrant_store.upsert_note
      already handles this, which is what makes the company check in
      _find_exact_duplicate() possible at all
    - Deduplicating on similarity score instead of exact text — a
      near-duplicate is still new information; only a literal repeat
      should be skipped
"""

from __future__ import annotations

from careerpilot.memory.semantic.qdrant_store import upsert_note, search_semantic
from careerpilot.tools.applications import safe_tool
from careerpilot.tools.registry import Tool

# How many past notes to check when deciding whether a new note is an
# exact duplicate of something already saved.
_DUPLICATE_CHECK_TOP_K = 1

# How many similar notes to return by default when recalling.
_RECALL_TOP_K = 5


SAVE_NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["company", "note"],
}


def _find_exact_duplicate(company: str, note: str) -> dict | None:
    """Cheap dedup check: search for the single closest existing note
    and treat it as a duplicate only if BOTH the company matches AND
    the text is identical (after trimming whitespace).

    Deliberately exact-text, not a similarity threshold — a threshold
    like "similarity above 0.95" would also catch two genuinely
    different notes that happen to be phrased alike, which is exactly
    the context you don't want silently dropped. Exact-text-after-
    trimming only catches the unambiguous case: the literal same note
    being saved twice.
    """
    existing = search_semantic(note, top_k=_DUPLICATE_CHECK_TOP_K)
    if not existing:
        return None

    top_match = existing[0]
    if top_match["company"] == company and top_match["text"].strip() == note.strip():
        return top_match
    return None


@safe_tool
def save_company_note(args: dict) -> str:
    company = args["company"]
    note = args["note"]

    duplicate = _find_exact_duplicate(company, note)
    if duplicate is not None:
        return f"Already saved — not storing a duplicate note for {company} (id={duplicate['id']})."

    note_id = upsert_note(company, note)
    return f"Saved note for {company} (id={note_id})."


RECALL_NOTES_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}


def _format_notes(results: list[dict]) -> str:
    """A compact, numbered, model-readable summary — mirrors
    tools/applications.py's table formatting so recall output reads
    the same way any other tool's list output does.
    """
    if not results:
        return "No related notes found."

    lines = [
        f"{i}. ({r['company']}) {r['text']} [similarity={r['score']:.2f}]"
        for i, r in enumerate(results, start=1)
    ]
    return "\n".join(lines)


@safe_tool
def recall_similar_notes(args: dict) -> str:
    query = args["query"]
    results = search_semantic(query, top_k=_RECALL_TOP_K)
    return _format_notes(results)


save_company_note_tool = Tool(
    name="save_company_note",
    description="Save a note about a company or interview for later recall.",
    input_schema=SAVE_NOTE_SCHEMA,
    fn=save_company_note,
)

recall_similar_notes_tool = Tool(
    name="recall_similar_notes",
    description="Find past notes semantically similar to a query.",
    input_schema=RECALL_NOTES_SCHEMA,
    fn=recall_similar_notes,
)
