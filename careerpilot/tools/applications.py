"""
Purpose
    Tools for tracking job applications: log, update status, list.

Responsibilities
    - log_application(company, role, date, source, notes)
    - update_application_status(company, role, new_status)
    - list_applications(status_filter=None)

Inputs:  tool_input dict from the LLM (validated against JSON schema,
         then re-validated in code — schemas describe shape, they don't
         enforce it)
Outputs: a short string result the LLM can read back

Dependencies:   memory.episodic.sqlite_store
Related files:  memory/episodic/sqlite_store.py, tools/registry.py
Design patterns:
    - Command: each function is one discrete, named action, wrapped as
      a Tool the registry can dispatch to by name
    - Decorator: safe_tool() wraps all three functions with identical
      error-handling behavior, so none of them repeat a try/except block
      (and none can forget one)
Difficulty:     beginner

Agentic AI concepts used: tool calling, structured output
Software engineering concepts used: input validation, single source of
  truth (APPLICATION_STATUSES feeds both the schema and the runtime
  check — nowhere else needs to know the valid statuses), idempotent
  writes where possible

Future implementation notes
    Add a 'reminder' side-effect: flag applications with no update in 14 days.

Common beginner mistakes
    - Doing string-matching on company names instead of a stable ID
    - Returning raw exceptions as tool output instead of a clean error
      string — see safe_tool() below, which exists specifically to
      prevent this
    - Hardcoding the same list of valid statuses in more than one place,
      where they can silently drift apart after an edit to just one of them
"""

from __future__ import annotations

import functools
from datetime import datetime
from typing import Callable

from careerpilot.memory.episodic.sqlite_store import (
    insert_application,
    update_status,
    list_applications as _list_applications,
)
from careerpilot.tools.registry import Tool

# Single source of truth for valid statuses. The JSON schemas below build
# their `enum` list FROM this tuple, and _validate_status() checks
# against this same tuple — so there is exactly one place to edit if a
# status is ever added, renamed, or removed.
APPLICATION_STATUSES: tuple[str, ...] = (
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
)

DATE_FORMAT = "%Y-%m-%d"


def _validate_date(date_str: str) -> None:
    """Raises ValueError with a clear message if `date_str` isn't
    YYYY-MM-DD. A JSON schema can only DESCRIBE the expected shape to
    the model in a description field — it can't enforce it. This is the
    actual enforcement, and it runs before anything touches the database.
    """
    try:
        datetime.strptime(date_str, DATE_FORMAT)
    except ValueError:
        raise ValueError(
            f"'{date_str}' is not a valid date — expected format {DATE_FORMAT} (e.g. 2026-07-01)."
        )


def _validate_status(status: str) -> None:
    """Defense in depth: the schema's `enum` should stop most invalid
    values before they ever get here, but not every provider enforces
    enums equally strictly — so this checks again, in code, regardless.
    """
    if status not in APPLICATION_STATUSES:
        raise ValueError(
            f"'{status}' is not a valid status — choose one of: {', '.join(APPLICATION_STATUSES)}."
        )


def safe_tool(fn: Callable[[dict], str]) -> Callable[[dict], str]:
    """Decorator: catches any exception a tool function raises and turns
    it into a short, clean error string instead of letting it propagate
    and crash the whole agent loop — a tool failing should read to the
    model like "that didn't work, here's why", never a stack trace.

    Applying this once, here, means log_application/
    update_application_status/list_applications don't each need their
    own try/except block — and none of them can accidentally forget one.

    KeyError gets a specific message (a required field was missing from
    the model's tool call) since the bare KeyError repr — just the
    missing key in quotes — isn't a very readable message on its own.
    """

    @functools.wraps(fn)
    def wrapper(args: dict) -> str:
        try:
            return fn(args)
        except KeyError as exc:
            return f"error: missing required field {exc}"
        except Exception as exc:
            return f"error: {exc}"

    return wrapper


def _format_confirmation(company: str, role: str, application_id: int) -> str:
    return f"Logged application: {company} — {role} (id={application_id})."


def _format_applications_table(rows: list[dict]) -> str:
    """Turns a list of application rows into a short, numbered,
    human-readable block — what the LLM actually reads back, not a raw
    dump of dicts it would have to interpret itself.
    """
    if not rows:
        return "No applications found."

    lines = [
        f"{i}. {row['company']} — {row['role']} — {row['status']} (applied {row['date_applied']})"
        for i, row in enumerate(rows, start=1)
    ]
    return "\n".join(lines)


LOG_APPLICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "role": {"type": "string"},
        "date_applied": {
            "type": "string",
            "description": f"Date in {DATE_FORMAT} format, e.g. 2026-07-01",
        },
        "source": {
            "type": "string",
            "description": "e.g. LinkedIn, referral, company site",
        },
        "notes": {"type": "string"},
    },
    "required": ["company", "role", "date_applied"],
}


@safe_tool
def log_application(args: dict) -> str:
    company = args["company"]
    role = args["role"]
    date_applied = args["date_applied"]
    _validate_date(date_applied)

    application_id = insert_application(
        company=company,
        role=role,
        date_applied=date_applied,
        source=args.get("source"),
        notes=args.get("notes"),
    )
    return _format_confirmation(company, role, application_id)


UPDATE_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "role": {"type": "string"},
        # built from APPLICATION_STATUSES, not typed out separately here —
        # this and _validate_status() can never silently drift apart.
        "new_status": {"type": "string", "enum": list(APPLICATION_STATUSES)},
    },
    "required": ["company", "role", "new_status"],
}


@safe_tool
def update_application_status(args: dict) -> str:
    company = args["company"]
    role = args["role"]
    new_status = args["new_status"]
    _validate_status(new_status)

    found = update_status(company, role, new_status)
    if not found:
        return f"No application found for {company} — {role}. Nothing was updated."
    return f"Updated {company} — {role} to status '{new_status}'."


LIST_APPLICATIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "status_filter": {"type": "string", "enum": list(APPLICATION_STATUSES)},
    },
    "required": [],
}


@safe_tool
def list_applications(args: dict) -> str:
    status_filter = args.get("status_filter")
    if status_filter:
        _validate_status(status_filter)

    rows = _list_applications(status_filter=status_filter)
    return _format_applications_table(rows)


log_application_tool = Tool(
    name="log_application",
    description="Record a new job application.",
    input_schema=LOG_APPLICATION_SCHEMA,
    fn=log_application,
)

update_application_status_tool = Tool(
    name="update_application_status",
    description="Update the status of an existing application.",
    input_schema=UPDATE_STATUS_SCHEMA,
    fn=update_application_status,
)

list_applications_tool = Tool(
    name="list_applications",
    description="List tracked applications, optionally filtered by status.",
    input_schema=LIST_APPLICATIONS_SCHEMA,
    fn=list_applications,
)
