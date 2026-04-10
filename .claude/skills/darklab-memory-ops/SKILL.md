---
name: darklab-memory-ops
description: OpenViking memory tiers, MemoryClient API, session continuity patterns, middleware memory pipeline, and semantic search usage.
origin: OAS
---

# Memory Operations

OAS uses OpenViking as the hot-tier memory store. Three tiers: Hot (OpenViking), Warm (LanceDB — Phase 25), Cold (JSONL + SQLite).

## When to Activate

- Working on `core/oas_core/memory.py` (MemoryClient)
- Modifying the memory middleware (`core/oas_core/middleware/memory.py`)
- Adding semantic search or session continuity features
- Debugging context pre-loading or write-back failures

## Memory Tiers

| Tier | Store | Access pattern |
|------|-------|----------------|
| L0 Hot | OpenViking | Every request — abstract summaries |
| L1 Warm | OpenViking structured | Campaign-level context |
| L2 Cold | JSONL + SQLite KB | Deep retrieval on demand |

## MemoryClient API

`core/oas_core/memory.py`

```python
from oas_core.memory import MemoryClient

client = MemoryClient(settings)

# Tiered read — L0 always, L1/L2 if needed
context = await client.read(
    session_id=session_id,
    tiers=[0, 1],
    max_tokens=2000,
)

# Semantic search across stored memories
results = await client.search(
    query="ionic liquid electrode conductivity",
    limit=5,
    session_id=session_id,  # optional scope
)

# Write findings back after step completion
await client.write(
    session_id=session_id,
    content=findings_text,
    tags=["ionic-liquid", "electrode"],
    tier=1,
)

# Session continuity
ctx = await client.load_session_context(session_id)
await client.archive_session(session_id, summary=summary_text)
related = await client.find_related_sessions(query, limit=3)
```

## Memory Middleware Pipeline

`core/oas_core/middleware/memory.py`

Runs as part of `Pipeline` compositor: Budget → Audit → Governance → **Memory** → handler.

**Pre-load**: semantic search for `prior_context` → injected into request payload.
**Post-store**: writes step findings to OpenViking after handler returns.

DRVP events: `memory.read`, `memory.write`

## Session Continuity Pattern

```python
# At mission start
ctx = await memory.load_session_context(mission_id)
if ctx.prior_sessions:
    prompt = f"Prior context:\n{ctx.summary}\n\n{prompt}"

# At mission end
await memory.archive_session(
    session_id=mission_id,
    summary=synthesized_findings,
    tags=[plan.id, "archived"],
)
```

## Role-Scoped Retrieval

The `RetrievalRouter` in `core/oas_core/knowledge/retrieval.py` scopes reads by layer:

- **Leader**: entity store + wiki filename search + OpenViking
- **DEV**: entity store only (no OpenViking in Phase 24)
- **Boss**: OpenViking L0 abstracts only

## Config

```bash
# ~/.darklab/.env
OPENVIKING_URL=http://192.168.23.25:8200
OPENVIKING_API_KEY=...
```

OpenViking URL is injected into `Settings.openviking_url`. The client falls back gracefully if OpenViking is unreachable — logs warning, returns empty context, never blocks the pipeline.
