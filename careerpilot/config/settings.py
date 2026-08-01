"""
Purpose
    Central place to load and validate all environment configuration —
    the ONE file that reads os.environ; every other file imports the
    `settings` instance from here instead.

Responsibilities
    - Load a local .env file automatically, if present
    - Read provider name + API key (Anthropic/OpenAI/Groq/etc.)
    - Read Qdrant connection info + embedding provider/model config
    - Read SQLite path for episodic memory
    - Expose one `Settings` instance the rest of the app imports

"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    # --- LLM provider (loop/models.py) ---
    provider: str
    model: str  # "" is intentional — loop/models.py's Provider
    # table fills in a sensible per-provider default
    # the first time get_client() runs, so this file
    # never has to hardcode a model name per
    # provider itself (that mapping lives in
    # exactly one place: models.py's PROVIDERS dict).
    small_model: str  # same story — filled in by get_client() if empty
    api_key: str
    base_url: str | None  # manual override; usually left None so
    # models.py's PROVIDERS table supplies it

    # --- semantic memory: Qdrant (memory/semantic/qdrant_store.py) ---
    qdrant_url: str
    qdrant_api_key: str | None
    qdrant_collection: str
    embedding_provider: str  # "openai" or "fastembed"
    embedding_model: str
    embedding_api_key: str | None  # separate from api_key — Groq/Anthropic
    # have no embeddings endpoint at all
    sparse_embedding_model: str | None  # set this to turn on hybrid search

    # --- episodic memory: SQLite (memory/episodic/sqlite_store.py) ---
    sqlite_path: str

    # --- loop guardrails (loop/agent.py) ---
    max_iterations: int = 10
    max_tokens: int = 2048

    # --- job search tool (tools/search_jobs.py) ---
    job_search_api_key: str | None = None

    # --- MCP (tools/mcp_loader.py) ---
    mcp_config_path: str = ".careerpilot/mcp.json"

    # --- experimental tools (tools/experimental.py) ---
    experimental_tools_enabled: bool = False

    # --- telegram gateway (gateway/telegram.py) ---
    telegram_bot_token: str | None = None
    telegram_allowed_user: str | None = None

    # --- dashboard gateway (gateway/dashboard/app.py) ---
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 7777

    # --- ops (ops/tracing.py, ops/usage.py) ---
    trace_dir: str = ".careerpilot/traces"
    usage_log_path: str = ".careerpilot/usage.jsonl"


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _load_dotenv_if_present() -> None:
    """Loads a local .env file into os.environ, if python-dotenv is
    installed AND a .env file exists — so a local .env "just works"
    with zero setup, while still letting real exported env vars work
    with no dependency at all if you'd rather do it that way.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return  # python-dotenv not installed — fine, real env vars still work
    load_dotenv()  # no-op if no .env file is found; never raises for that


def load_settings() -> Settings:
    """Loads every setting the app needs, from environment variables
    (optionally via a local .env file).

    A note on validation this deliberately does NOT do: it does not
    raise if api_key is empty. loop/models.py's get_client() already
    validates this, with MORE context than this function has — it
    knows the chosen provider's specific fallback env var (e.g.
    GROQ_API_KEY), so a user who set that directly instead of
    CAREERPILOT_API_KEY is still a valid setup. A blanket "api_key must
    be non-empty" check here would incorrectly reject that. Fail-fast
    still happens — just at the point that actually has enough
    information to fail correctly.
    """
    _load_dotenv_if_present()

    return Settings(
        provider=os.environ.get("CAREERPILOT_PROVIDER", "anthropic"),
        model=os.environ.get("CAREERPILOT_MODEL", ""),
        small_model=os.environ.get("CAREERPILOT_SMALL_MODEL", ""),
        api_key=os.environ.get("CAREERPILOT_API_KEY", ""),
        base_url=os.environ.get("CAREERPILOT_BASE_URL"),
        qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        qdrant_api_key=os.environ.get("QDRANT_API_KEY"),
        qdrant_collection=os.environ.get("QDRANT_COLLECTION", "careerpilot_semantic"),
        embedding_provider=os.environ.get("CAREERPILOT_EMBEDDING_PROVIDER", "openai"),
        embedding_model=os.environ.get(
            "CAREERPILOT_EMBEDDING_MODEL", "text-embedding-3-small"
        ),
        embedding_api_key=os.environ.get("CAREERPILOT_EMBEDDING_API_KEY"),
        sparse_embedding_model=os.environ.get("CAREERPILOT_SPARSE_EMBEDDING_MODEL"),
        sqlite_path=os.environ.get("CAREERPILOT_SQLITE_PATH", ".careerpilot/state.db"),
        max_iterations=int(os.environ.get("CAREERPILOT_MAX_ITERATIONS", "10")),
        max_tokens=int(os.environ.get("CAREERPILOT_MAX_TOKENS", "2048")),
        job_search_api_key=os.environ.get("TAVILY_API_KEY"),
        mcp_config_path=os.environ.get(
            "CAREERPILOT_MCP_CONFIG", ".careerpilot/mcp.json"
        ),
        experimental_tools_enabled=_bool_env("CAREERPILOT_EXPERIMENTAL"),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_user=os.environ.get("TELEGRAM_ALLOWED_USER"),
        dashboard_host=os.environ.get("CAREERPILOT_DASHBOARD_HOST", "127.0.0.1"),
        dashboard_port=int(os.environ.get("CAREERPILOT_DASHBOARD_PORT", "7777")),
        trace_dir=os.environ.get("CAREERPILOT_TRACE_DIR", ".careerpilot/traces"),
        usage_log_path=os.environ.get(
            "CAREERPILOT_USAGE_LOG", ".careerpilot/usage.jsonl"
        ),
    )


settings = load_settings()
