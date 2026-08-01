# CareerPilot

**An AI job-search co-pilot that tracks your applications, remembers your interview notes, and searches for roles — built as a from-scratch study of production agent architecture, not a framework demo.**

CareerPilot is a single-user, bring-your-own-key (BYOK) AI agent for people actively job hunting. It logs and tracks applications, remembers company- and interview-specific notes with real semantic search, searches the web for open roles scoped to whatever platforms and location you configure, and exposes all of it through a tested FastAPI backend designed to be paired with a React frontend.

It was built by studying [waku-agent](https://github.com/ShenSeanChen/waku-agent) — a reference implementation of agent architecture by ShenSeanChen — line by line, then re-implementing its core ideas from scratch for a different domain, rather than copying it. See [Acknowledgments](#acknowledgments--reference) for exactly what was learned from it and what was deliberately built differently.

---

## Why this exists

Most "build an AI agent" tutorials wrap a chat loop around a framework and call it done. CareerPilot is the opposite: the entire agent loop, tool-calling, memory system, and provider abstraction are hand-written, framework-free, and independently tested — because the point of building it was to actually understand what an agent framework is hiding, not to hide it again one layer down.

Every non-trivial piece of this codebase was built the same way: implement it, then prove it works against real dependencies (a real in-memory Qdrant instance, a real temp SQLite file, a real FastAPI `TestClient`, even a real network fetch against `raw.githubusercontent.com`) before considering it done — not just "it looks right."

---

## Architecture: four pillars

CareerPilot follows the same architectural split waku-agent uses, because it's a genuinely good decomposition for any agent system, not because it's the only way to build one:

| Pillar | What it is | Where it lives |
|---|---|---|
| **Harness** | The thin entry points that turn human input into messages and replies back into output — a CLI, and a FastAPI backend for a future React frontend | `gateway/` |
| **Loop** | The actual agent: reason → act → observe, with two hard exits (no more tool calls, or hit the iteration limit) — ~95 lines, no LangGraph/CrewAI/AutoGen | `loop/` |
| **Memory** | Semantic (Qdrant, vector search), episodic (SQLite, structured job-application data + conversations), and procedural (Markdown `SKILL.md` playbooks) — plus a retrieval gate that decides *whether* to retrieve before deciding *what* to retrieve | `memory/` |
| **LLM-Ops** | Tracing, token/cost usage tracking, deterministic evals, and an LLM-as-judge eval suite, gated together — never conflated into one soft score | `ops/`, `evals/` |

The loop itself speaks exactly one dialect (Anthropic's Messages shape — system/messages/tools in, typed content blocks out) regardless of which real provider is behind it. `loop/models.py` is the only file that knows any other wire format exists; adding a new OpenAI-compatible provider is a one-line addition to a table, never a change to the loop.

---

## Features

- **Application tracking** — log, update status, and list job applications, backed by SQLite with real validation (dates, status enums) and duplicate-safe writes
- **Semantic memory** — save and recall notes about companies and interviews via Qdrant, with cosine-similarity search and optional hybrid (dense + sparse/BM25, fused with Reciprocal Rank Fusion) search
- **Self-managed memory** — the agent can `forget` or `correct` a note, update its own standing preferences (`profile.md`), and write new procedural skills mid-conversation, live — none of this is read-only
- **Platform-agnostic job search** — never hardcoded to one job board; which platforms to search (LinkedIn, Indeed, Glassdoor, or any others) and a default location live in a hot-reloadable config file, with a keyless DuckDuckGo fallback and an optional Tavily upgrade
- **Multi-provider LLM support** — Anthropic, OpenAI, Groq, OpenRouter, Gemini, DeepSeek, MiniMax, Kimi, and GLM, all behind one adapter, switchable via a single config value
- **Procedural skills** — Markdown playbooks (`SKILL.md`) matched to the conversation by keyword overlap, hot-reloaded the moment a new one is written — including ones the agent writes for itself
- **Full conversation persistence** — every conversation and its turns are stored in SQLite with list/retrieve/rename/delete endpoints, so a chat history survives a backend restart
- **Streaming chat API** — token-by-token text and live tool-call events over a single POST-and-stream connection (no EventSource limitations)
- **Runtime-mutable settings** — provider, model, API keys, embedding config, and job-search platforms are all changeable from a Settings-style API with no restart required
- **Observability that never breaks the conversation** — tracing and usage logging are wired in via the Observer pattern, decoupled from the loop, and fail silently rather than crash a turn
- **A real eval story** — deterministic tests (0/1 tool-calling correctness, run against real isolated storage) kept strictly separate from LLM-as-judge reply-quality scoring, gated together, never averaged into one soft number

---

## Tech stack

**Language & tooling**
- Python 3.13, managed with [`uv`](https://github.com/astral-sh/uv)
- `pytest` for both the deterministic and LLM-as-judge eval suites

**Agent core**
- Framework-free agent loop (no LangChain, LangGraph, CrewAI, or AutoGen)
- `anthropic` and `openai` Python SDKs — the OpenAI SDK also drives every OpenAI-compatible provider (Groq, OpenRouter, DeepSeek, etc.) via `base_url` overrides
- Hand-written provider adapter translating every non-Anthropic wire format into one internal dialect

**Memory**
- [`qdrant-client`](https://github.com/qdrant/qdrant-client) — semantic memory, named dense + sparse vectors, Reciprocal Rank Fusion hybrid search
- [`fastembed`](https://github.com/qdrant/fastembed) — local, free, no-API-key embeddings (Qdrant's own local embedding library)
- OpenAI embeddings (`text-embedding-3-small` etc.) as the alternative embedding provider, swappable via config, behind a Strategy-pattern interface
- SQLite (`sqlite3`, stdlib) — job applications, episodes, and full conversation history

**Search**
- [`ddgs`](https://github.com/deedy5/ddgs) — keyless DuckDuckGo search, the default job-search fallback
- [`tavily-python`](https://github.com/tavily-ai/tavily-python) — optional, higher-quality search when an API key is configured

**Backend API**
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- Pydantic v2 for every request/response schema
- Server-Sent Events (via `StreamingResponse`) for streaming chat, bridged from a fully synchronous agent loop via a background thread + `queue.Queue`
- Uniform `{"success": bool, ...}` response envelope and a global exception handler, so the API is predictable to build a frontend against

**Config**
- `python-dotenv` for local `.env` loading, with a runtime-mutable JSON overlay (`.careerpilot/runtime_config.json`) layered on top for settings changed live via the API

**Planned**
- React frontend (not yet built) — the API above was designed against a finalized frontend architecture (Component → Hook → Service → Axios) specifically so the contract wouldn't need to change once frontend work starts

---

## Project structure

```
careerpilot/
├── config/
│   └── settings.py            # the one place that reads environment variables
├── loop/
│   ├── agent.py                # the agent loop — reason/act/observe, ~95 lines
│   └── models.py                # multi-provider adapter (Anthropic-native + OpenAI-compatible)
├── tools/
│   ├── registry.py               # tool schema + dispatch
│   ├── applications.py            # log/update/list job applications
│   ├── search_jobs.py              # platform-agnostic job search
│   ├── notes.py                     # save/recall semantic notes
│   ├── memory_admin.py               # manage_memory, update_profile, create_skill
│   └── experimental.py                # flagged-off roadmap tools
├── memory/
│   ├── retrieval_gate.py           # decides WHETHER to retrieve, before WHAT
│   ├── semantic/qdrant_store.py     # Qdrant-backed semantic memory (dense + hybrid)
│   ├── episodic/sqlite_store.py      # job applications + episodes
│   ├── procedural/
│   │   ├── skill_loader.py            # hot-reloading SKILL.md loader
│   │   └── skill_writer.py             # shared skill-writing logic (agent tool + API both use this)
│   ├── soul.py                       # profile.md — standing preferences
│   ├── memory_mirror.py               # regenerates a human-readable MEMORY.md
│   └── consolidation.py                # batches chat history into durable facts
├── runtime/
│   └── session.py                  # assembles working memory for one turn
├── ops/
│   ├── tracing.py                   # append-only JSONL tracing via the Observer pattern
│   ├── usage.py                      # append-only token/cost ledger
│   └── release_gate.py                # gates a release on deterministic + judge evals together
├── gateway/
│   ├── cli.py                       # terminal entry point
│   └── dashboard/                    # the FastAPI backend
│       ├── app.py                      # app assembly, CORS, uniform error handling
│       ├── schemas.py                    # every request/response shape
│       ├── conversations_store.py         # persisted conversation + turn history
│       ├── session_store.py                # in-memory internal agent-loop state
│       ├── runtime_settings.py              # hot-reloadable, API-mutable settings overlay
│       └── routers/                          # chat, conversations, applications, memory, settings, skills
├── evals/
│   ├── deterministic/                # 0/1 tool-calling correctness, isolated storage per test
│   └── judge/                         # LLM-as-judge reply-quality scenarios
└── scripts/
    ├── demo_seed.py                  # backs up, resets, and seeds a clean demo state
    └── skill_install.py               # installs a SKILL.md from a GitHub/Gist URL
```

---

## Getting started

### 1. Install [`uv`](https://github.com/astral-sh/uv) and create the environment

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows

uv venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```


### 2. Start Qdrant with Docker

CareerPilot's semantic memory needs a running Qdrant instance. The simplest way is Docker.

Pull the image first:

```bash
docker pull qdrant/qdrant
```

```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 3. Configure your `.env`

```env
CAREERPILOT_PROVIDER=groq
CAREERPILOT_API_KEY=your-key-here
CAREERPILOT_MODEL=llama-3.3-70b-versatile

CAREERPILOT_EMBEDDING_PROVIDER=fastembed
CAREERPILOT_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

QDRANT_URL=http://localhost:6333
```

Groq (and most non-Anthropic/non-OpenAI providers) has no embeddings endpoint — `fastembed` sidesteps that entirely by running locally, with no second API key needed.

if you want to use anthropic or openAI do setup in the .env file

### 4. Run it

**CLI:**
```bash
python -m careerpilot.gateway.cli
```

**API** (for frontend development):
```bash
uvicorn careerpilot.gateway.dashboard.app:app --reload --port 7777
```

Interactive API docs: `http://127.0.0.1:7777/docs`

---

## Testing

```bash
# Deterministic suite — no API key needed, isolated SQLite + in-memory Qdrant, runs instantly
python -m pytest evals/deterministic -v

# LLM-as-judge suite — needs a real provider key; skips cleanly (not failing) without one
python -m pytest evals/judge -v
```

The two suites are deliberately kept separate: one is 0/1 correctness with no model judging it, the other is a scored opinion on reply quality — averaging them into one number would let a great judge score paper over a real correctness failure, or vice versa.

---

## Reset to a clean demo state

```bash
python -m scripts.demo_seed
```

Backs up whatever's currently in `.careerpilot/` before resetting, then seeds a few sample applications and notes — safe to run repeatedly.

---

## Acknowledgments & reference

CareerPilot's architecture is a direct study of **[waku-agent](https://github.com/ShenSeanChen/waku-agent)** by [ShenSeanChen](https://github.com/ShenSeanChen) — a teaching-grade reference implementation of the same four-pillar architecture (Harness, Loop, Memory, LLM-Ops) described above. Concepts adapted from it, studied and re-implemented rather than copied:

- The framework-free agent loop shape and its two guardrails
- The Observer pattern decoupling tracing/observability from the loop itself
- The retrieval gate — deciding *whether* to retrieve before *what* to retrieve
- Deterministic evals and LLM-as-judge evals as two permanently separate suites, gated together
- Procedural memory as plain Markdown (`SKILL.md`) rather than buried in code or embeddings
- Self-managed memory — giving the agent tools to correct its own memory instead of treating it as read-only

Deliberate differences, not oversights:

- **Semantic memory**: waku's default is SQLite FTS5 keyword search, with Supabase pgvector as a documented upgrade path. CareerPilot uses Qdrant with real embeddings (and optional hybrid dense+sparse search) from day one.
- **Domain**: a job-search co-pilot instead of a general personal assistant.
- **No AnthropicEmbeddingProvider**: Anthropic has no embeddings API at all — rather than fake one, the embedding provider is a Strategy interface (OpenAI or local FastEmbed today), so adding real Anthropic embeddings later would be one new class, not a rewrite.

---

## License

MIT

## Author

Built by [Adnan](https://github.com/) as a portfolio project demonstrating production agent architecture — B.S. Software Engineering, University of Haripur, Pakistan.