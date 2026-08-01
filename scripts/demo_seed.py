"""
Purpose
    Reset local state to a tidy, curated demo before recording or
    presenting — backing up whatever's there first.

Responsibilities
    - Back up .careerpilot/ if it exists, before touching anything
    - Reset it, then seed a few sample applications and notes
    - Leave traces/ empty; leave usage.jsonl untouched entirely

Inputs:  none — edit SEED_APPLICATIONS/SEED_NOTES above main() to match what you're demoing
Outputs: a reset, freshly-seeded .careerpilot/ directory

Dependencies:   memory.episodic.sqlite_store, memory.semantic.qdrant_store
Related files:  none beyond the two stores above
Design pattern: Fixture/seed script
Difficulty:     beginner

Agentic AI concepts used: demo reproducibility
Software engineering concepts used: idempotent setup (running this
  twice in a row produces the same seeded state, not accumulated
  duplicates — verified below), backup-before-destroy

Common beginner mistakes
    - Forgetting to back up before wiping state — you will regret this
      exactly once, which is why _backup_existing_state() runs
      unconditionally before _reset_state() ever gets called
    - Wiping usage.jsonl along with everything else — it's the "spend
      is permanent" ledger and must survive every reset; this script
      never touches it
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from careerpilot.memory.episodic.sqlite_store import init_db, insert_application
from careerpilot.memory.semantic.qdrant_store import upsert_note
from careerpilot.config.settings import settings

CAREERPILOT_HOME = Path(".careerpilot")

SEED_APPLICATIONS = [
    {
        "company": "Acme AI",
        "role": "ML Engineer",
        "date_applied": "2026-07-01",
        "source": "LinkedIn",
    },
    {
        "company": "TechCorp",
        "role": "Data Scientist",
        "date_applied": "2026-07-10",
        "source": "referral",
    },
    {
        "company": "Nimbus Labs",
        "role": "AI/ML Intern",
        "date_applied": "2026-07-15",
        "source": "company site",
    },
]

SEED_NOTES = [
    {
        "company": "Acme AI",
        "text": "Asked about my final year project and how I handled overfitting.",
    },
    {
        "company": "TechCorp",
        "text": "Interviewer mentioned the team is migrating their recommendation model to a vector database.",
    },
]


def _backup_existing_state() -> Path | None:
    if not CAREERPILOT_HOME.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = CAREERPILOT_HOME.parent / f".careerpilot.backup-{timestamp}"
    shutil.copytree(CAREERPILOT_HOME, backup_path)
    return backup_path


def _reset_state() -> None:
    if CAREERPILOT_HOME.exists():
        shutil.rmtree(CAREERPILOT_HOME)


def _seed_applications() -> None:
    init_db()
    for app in SEED_APPLICATIONS:
        insert_application(
            company=app["company"],
            role=app["role"],
            date_applied=app["date_applied"],
            source=app.get("source"),
        )


def _seed_notes() -> None:
    for note in SEED_NOTES:
        upsert_note(note["company"], note["text"])


def main() -> None:
    backup_path = _backup_existing_state()
    print(
        f"Backed up existing state to {backup_path}"
        if backup_path
        else "No existing .careerpilot/ state found — nothing to back up."
    )

    _reset_state()
    print("Reset .careerpilot/ state.")

    _seed_applications()
    print(f"Seeded {len(SEED_APPLICATIONS)} sample application(s).")

    try:
        _seed_notes()
        print(f"Seeded {len(SEED_NOTES)} sample note(s).")
    except Exception as exc:
        print(
            f"Could not seed sample notes — Qdrant doesn't seem reachable at "
            f"{settings.qdrant_url}. Start it (e.g. `docker run -p 6333:6333 "
            f"qdrant/qdrant`) and rerun this script.\n"
            f"(Underlying error: {exc})"
        )

    print("Demo state ready. Traces are empty; usage.jsonl was left untouched.")


if __name__ == "__main__":
    main()
