"""
Purpose
    Search the web for open roles — never hardcoded to one job board.
    Which platforms to search (LinkedIn, Indeed, Glassdoor, or any
    others) and a default location are read from a small config file
    that a future dashboard frontend can write to directly, with no
    restart needed to pick up a change.

Responsibilities
    - load_job_search_preferences(): hot-reloadable platform list +
      default location, meant to be edited by the user (by hand today,
      by a frontend settings panel later)
    - SearchProvider / DuckDuckGoProvider / TavilyProvider: the same
      Strategy shape waku uses for search_web — Tavily if a key is
      configured, DuckDuckGo (keyless) otherwise
    - search_jobs(args): scopes the query to the configured platforms
      and location, searches, and returns a compact summary

Inputs:  {'query': str, 'location': str | None}
Outputs: string summary of matching postings

Dependencies:   ddgs (keyless fallback), tavily-python (optional, needs
                a key), a job_search_prefs.json config file
Related files:  waku/tools/search.py (reference), tools/registry.py, config/settings.py
Design patterns:
    - Strategy: DuckDuckGoProvider/TavilyProvider are interchangeable
      behind one SearchProvider interface — search_jobs() never knows
      or cares which one is actually running
    - Factory: build_search_provider() is the one place that decides
      which concrete provider to construct
Difficulty:     intermediate

Agentic AI concepts used: tool calling, grounding via external retrieval
Software engineering concepts used: graceful degradation (no API key ->
  keyless fallback, no results -> a clean message, provider failure ->
  a clean error string — never a crash), hot-reloadable config (same
  cache-invalidation pattern as runtime/session.py and
  memory/procedural/skill_loader.py)

A note on "never specific to one platform"
    The platform list lives entirely in job_search_prefs.json, read
    fresh (with caching + hot-reload) on every call — never hardcoded
    in this file. An empty platform list degrades to a plain, unscoped
    search rather than breaking. Adding, removing, or reordering
    platforms is a config change, never a code change.

Future implementation notes
    Fall back to a keyless search if no API key is set — done, exactly
    like waku's DuckDuckGo fallback for search_web.

Common beginner mistakes
    - Letting a network timeout crash the whole loop instead of
      returning an error string (search_jobs wraps everything in a
      single try/except for exactly this reason)
    - Returning raw HTML/JSON instead of a compact, model-readable summary
    - Hardcoding "linkedin.com" and "indeed.com" directly in code
      instead of reading them from a config the user (or a frontend)
      can actually change
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from careerpilot.config.settings import settings
from careerpilot.tools.registry import Tool

# ---------------------------------------------------------------------
# Job search preferences: hot-reloadable, frontend-adjustable.
# ---------------------------------------------------------------------

JOB_PREFS_PATH = Path(".careerpilot/job_search_prefs.json")
DEFAULT_PLATFORMS: tuple[str, ...] = ("linkedin.com", "indeed.com", "glassdoor.com")


@dataclass
class JobSearchPreferences:
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS
    default_location: str | None = None


_cached_prefs: JobSearchPreferences | None = None
_cached_mtime: float | None = None


def load_job_search_preferences() -> JobSearchPreferences:
    """Reads .careerpilot/job_search_prefs.json, hot-reloading on
    change. This is the file a future dashboard settings panel writes
    to: the user changes which platforms to search, or sets a default
    location, from the frontend — the very next search_jobs call picks
    it up, no restart required.
    """
    global _cached_prefs, _cached_mtime

    if not JOB_PREFS_PATH.exists():
        return JobSearchPreferences()

    mtime = JOB_PREFS_PATH.stat().st_mtime
    if _cached_prefs is None or mtime != _cached_mtime:
        data = json.loads(JOB_PREFS_PATH.read_text(encoding="utf-8"))
        _cached_prefs = JobSearchPreferences(
            platforms=tuple(data.get("platforms", DEFAULT_PLATFORMS)),
            default_location=data.get("default_location"),
        )
        _cached_mtime = mtime

    return _cached_prefs


# ---------------------------------------------------------------------
# Provider abstraction — same Strategy shape as waku's search_web:
# Tavily if a key is configured, DuckDuckGo (keyless) otherwise.
# ---------------------------------------------------------------------


@dataclass
class JobPosting:
    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int) -> list[JobPosting]: ...


class DuckDuckGoProvider(SearchProvider):
    """Keyless fallback — no API key required, exactly like waku's
    default for search_web.
    """

    def search(self, query: str, max_results: int) -> list[JobPosting]:
        from ddgs import DDGS

        results = DDGS().text(query, max_results=max_results)
        return [
            JobPosting(
                title=r.get("title", "").strip(),
                url=r.get("href", "").strip(),
                snippet=r.get("body", "").strip(),
            )
            for r in results
        ]


class TavilyProvider(SearchProvider):
    """Used when a job-search API key is configured — generally
    higher-quality results than the keyless fallback, same tradeoff
    waku documents for search_web.
    """

    def __init__(self, api_key: str):
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int) -> list[JobPosting]:
        response = self._client.search(query=query, max_results=max_results)
        return [
            JobPosting(
                title=r.get("title", "").strip(),
                url=r.get("url", "").strip(),
                snippet=r.get("content", "").strip(),
            )
            for r in response.get("results", [])
        ]


def build_search_provider() -> SearchProvider:
    """Tavily if settings.job_search_api_key is set, DuckDuckGo
    otherwise — the exact fallback waku's search_web uses, applied to
    job search instead of general web search.
    """
    if settings.job_search_api_key:
        return TavilyProvider(api_key=settings.job_search_api_key)
    return DuckDuckGoProvider()


# ---------------------------------------------------------------------
# The tool itself.
# ---------------------------------------------------------------------

SEARCH_JOBS_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "role + keywords, e.g. 'ML engineer'",
        },
        "location": {
            "type": "string",
            "description": "optional — overrides the configured default location",
        },
    },
    "required": ["query"],
}

MAX_RESULTS = 8


def _scope_query(query: str, location: str | None, prefs: JobSearchPreferences) -> str:
    """Builds the actual search string: the role/keywords, an optional
    location, and an OR'd site: filter across every configured
    platform. This is what makes the tool platform-agnostic — never
    hardcoded to LinkedIn or Indeed specifically; it searches whichever
    platforms are listed in job_search_prefs.json, however many there
    are, and degrades to a plain unscoped search if that list is empty.
    """
    parts = [query]

    effective_location = location or prefs.default_location
    if effective_location:
        parts.append(effective_location)

    if prefs.platforms:
        site_filter = " OR ".join(f"site:{platform}" for platform in prefs.platforms)
        parts.append(f"({site_filter})")

    return " ".join(parts)


def _format_results(postings: list[JobPosting]) -> str:
    """A compact, numbered, model-readable summary — never a raw dump
    of provider JSON/HTML back to the model.
    """
    if not postings:
        return "No matching job postings found."

    lines = [
        f"{i}. {p.title} — {p.url}\n   {p.snippet}"
        for i, p in enumerate(postings, start=1)
    ]
    return "\n".join(lines)


def search_jobs(args: dict) -> str:
    try:
        prefs = load_job_search_preferences()
        query = _scope_query(args["query"], args.get("location"), prefs)
        provider = build_search_provider()
        postings = provider.search(query, max_results=MAX_RESULTS)
        return _format_results(postings)
    except Exception as exc:
        # A network hiccup or provider outage should never crash the
        # whole agent loop — the model reads this back and can react
        # (e.g. tell the user search is temporarily unavailable).
        return f"error: job search failed — {exc}"


search_jobs_tool = Tool(
    name="search_jobs",
    description="Search for open job postings matching a role, optionally scoped to a location.",
    input_schema=SEARCH_JOBS_SCHEMA,
    fn=search_jobs,
)
