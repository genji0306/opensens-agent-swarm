---
name: darklab-knowledge-wiki
description: OAS knowledge subsystem — KnowledgeIngester pipeline, EntityStore (SQLite), EmbeddingIndex (LanceDB), RetrievalRouter, wiki page format, and DRVP knowledge events.
origin: OAS
---

# Knowledge Wiki

Three-tier knowledge store: Hot (OpenViking), Warm (LanceDB embedded — Phase 25), Cold (JSONL + SQLite).

## When to Activate

- Working on `core/oas_core/knowledge/` subsystem
- Adding entity/claim extraction or wiki page compilation
- Debugging knowledge ingestion or retrieval
- Wiring new campaign steps into the ingestion pipeline

## Architecture

```
Campaign step output
        │
KnowledgeIngester.ingest()
        │
   ┌────┴────┐
   ▼         ▼
EntityStore  WikiPage
(SQLite)     (~/.darklab/wiki/{topic}.md)
   │
   ├─ entities table
   ├─ claims table
   └─ relationships table
        │
  EmbeddingIndex (LanceDB, Phase 25)
        │
  RetrievalRouter
   ├─ Leader: entity store + wiki search + OpenViking
   ├─ DEV: entity store only
   └─ Boss: OpenViking L0 only
```

## KnowledgeIngester

`core/oas_core/knowledge/ingester.py`

```python
from oas_core.knowledge import KnowledgeIngester

ingester = KnowledgeIngester(settings, entity_store, embedding_index)
result = await ingester.ingest(
    text=step_output,
    source_id=step_id,
    agent_id="darklab-academic",
    mission_id=mission_id,
    confidence=0.8,
)
# result: {entity_count, claim_count, page_path, duration_s}
```

Pipeline: extract text → extract entities (regex: chemical formulas, compounds) → extract claims (sentence-level, SHA-256 IDs) → write wiki pages → update `wiki/index.md` → optional OpenViking write-back.

## EntityStore

`core/oas_core/knowledge/entity_store.py` — SQLite-backed, 3 tables:

```python
from oas_core.knowledge import EntityStore

store = EntityStore(db_path)
await store.add_entity(Entity(id="BMIM-BF4", name="...", type="compound", ...))
entities = await store.search_entities(query="ionic liquid", limit=10)
await store.add_claim(Claim(id=sha256, entity_id="BMIM-BF4", text="...", ...))
await store.supersede_claim(old_claim_id, new_claim_id)
```

Claims have status: `active` | `superseded` | `disputed` | `unverified`.

## EmbeddingIndex

`core/oas_core/knowledge/embedding_index.py` — LanceDB wrapper:

```python
from oas_core.knowledge import EmbeddingIndex

index = EmbeddingIndex(db_path)  # lazy open
await index.add(texts=[...], ids=[...], vectors=[...], metadata=[...])
results = await index.search(query_vector=vec, limit=5)
```

Guard: `_LANCEDB_AVAILABLE` — degrades gracefully if `lancedb` not installed. **Requires pre-computed vectors** — does not call embedding model itself.

Install: `uv pip install "oas-core[wiki]"` → adds `lancedb>=0.6`, `mlx-embeddings>=0.1`.

## Frozen Types

`core/oas_core/knowledge/types.py`

```python
@dataclass(frozen=True)
class KnowledgeProvenance:
    agent_id: str
    mission_id: str
    campaign_id: str | None
    model_tier: str
    confidence: float       # 0.0–1.0
    timestamp: str          # ISO 8601
    sources: tuple[str, ...]

@dataclass(frozen=True)
class Claim:
    id: str                 # SHA-256 of (entity_id + text)
    entity_id: str
    text: str
    status: str             # active | superseded | disputed | unverified
    provenance: KnowledgeProvenance
```

## Wiki Page Format

`~/.darklab/wiki/{topic}.md`

```markdown
# {Topic}

**Last updated**: {ISO timestamp}
**Confidence**: {0.0–1.0}
**Sources**: {count}

## Summary
{synthesized summary}

## Key Claims
- {claim text} (confidence: {n})

## Entities
- {entity name}: {type}

## Sources
- {source_id} — {agent_id} @ {timestamp}
```

## DRVP Events

New events (added in `core/oas_core/protocols/drvp.py`):
```
knowledge.ingested
knowledge.conflict.detected
knowledge.conflict.auto_resolved
knowledge.page.compiled
wiki.lint.completed
wiki.sync.completed
```

## RetrievalRouter

`core/oas_core/knowledge/retrieval.py`

```python
from oas_core.knowledge import RetrievalRouter

router = RetrievalRouter(entity_store, embedding_index, memory_client)
artifacts = await router.retrieve(
    query="BMIM conductivity",
    role="leader",    # leader | dev | boss
    limit=5,
)
# returns list[KnowledgeArtifact] sorted by relevance desc
```
