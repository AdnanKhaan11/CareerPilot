# CareerPilot architecture

```mermaid
flowchart TB
    subgraph GW["Gateway - careerpilot/gateway/"]
        CLI["cli.py"]
        TG["telegram.py"]
        VOICE["voice.py (stub)"]
        DASH["dashboard/app.py (stub)"]
    end

    subgraph RUN["Ephemeral Agent Run"]
        SOUL["profile.md - memory/soul.py"]
        WM["Working Memory - runtime/session.py"]
        subgraph LOOP["The Loop - loop/agent.py"]
            LLM["LLM call (loop/models.py)"]
            TOOLS["Tools - tools/"]
            LLM -->|tool calls| TOOLS -->|results| LLM
        end
        SOUL --> WM
        WM --> LLM
    end

    GW --> WM
    LLM -->|reply| GW

    subgraph MEM["Memory - careerpilot/memory/"]
        GATE{{"retrieval_gate.py"}}
        SEM["semantic/qdrant_store.py<br/>Qdrant + embeddings"]
        EPI["episodic/sqlite_store.py<br/>applications, interviews"]
        PROC["procedural/skill_loader.py<br/>SKILL.md playbooks"]
        CONS{{"consolidation.py"}}
        MIRROR["memory_mirror.py<br/>-> MEMORY.md"]
    end

    WM -.->|every turn| GATE
    GATE -->|only if needed| SEM & EPI
    PROC -->|keyword match| WM
    CONS -->|distill| SEM
    CONS -->|episode| EPI
    SEM & EPI -.->|after every turn| MIRROR

    subgraph TOOLADMIN["Self-managed memory - tools/memory_admin.py"]
        MM["manage_memory"]
        UP["update_profile"]
        CS["create_skill"]
    end
    TOOLS --- TOOLADMIN
    MM --> SEM
    UP --> SOUL
    CS --> PROC

    subgraph EXT["Optional integrations"]
        MCP["tools/mcp_loader.py<br/>.careerpilot/mcp.json"]
        EXP["tools/experimental.py<br/>CAREERPILOT_EXPERIMENTAL=1"]
    end
    MCP -.->|namespaced tools| TOOLS
    EXP -.->|flag-gated| TOOLS

    subgraph OPS["LLM Ops - careerpilot/ops/ + evals/"]
        TRACE["tracing.py"]
        USAGE["usage.py -> usage.jsonl"]
        DET["evals/deterministic"]
        JUDGE["evals/judge"]
        RGATE{{"release_gate.py"}}
        TRACE --> DET & JUDGE --> RGATE
    end
    RUN -.->|every event| TRACE
    RUN -.->|every LLM call| USAGE
```

## What's different from waku-agent, on purpose
- Semantic memory: Qdrant + real embeddings, not SQLite FTS5.
- Episodic memory: still SQLite, because applications/interviews are
  structured relational data, not free text needing similarity search.
- Domain: job-search co-pilot, not a general personal assistant.
- `auto_apply` and `draft_outreach_email` are experimental/disabled —
  auto-submitting applications or sending emails on your behalf is a
  real trust step that deserves a deliberate safety review, not a
  default-on tool.

## What's deliberately the same as waku-agent
- The loop shape (reason/act/observe, two guardrails) — `loop/agent.py`.
- The Observer pattern decoupling tracing/UI/usage-tracking from the loop.
- The retrieval gate before any memory query — `memory/retrieval_gate.py`.
- Deterministic + judge evals kept as two separate suites, gated together.
- Standing preferences in a plain, editable file (`profile.md`, waku's
  SOUL.md) — not buried in embeddings or code.
- A human-readable `MEMORY.md` mirror regenerated every turn, alongside
  the real queryable stores.
- An append-only `usage.jsonl` cost ledger that survives demo resets.
- Self-managed memory: the agent can `manage_memory` (forget/correct),
  `update_profile`, and `create_skill` — memory isn't read-only.
- MCP support: drop a `.careerpilot/mcp.json` and external tools show
  up namespaced (`mcp_<server>_<tool>`), same as waku.
- Multiple gateways (CLI, Telegram, voice, dashboard) all calling the
  exact same loop — "one brain, many doors."
- Roadmap features shipped as visible, flagged-off stubs
  (`tools/experimental.py`) rather than silently missing.

## Deliberately deferred (stubs, not full builds)
- `gateway/voice.py` — wake-word/STT/TTS is real infra, but adds no
  architectural learning until the core loop is solid. Build last.
- `gateway/dashboard/app.py` — the live multi-tab UI is a project of
  its own; the seam (Observer -> event stream) is scaffolded, tabs are
  TODO, prioritized Loop and Memory first.
