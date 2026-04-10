# LLM Wiki & Harness Engineering to Develop Opensens Agent Swarm

> **Status**: Proposed | **Target**: Phase 25-26 | **Author**: Swarm Research (5-agent parallel synthesis)
> **Date**: 2026-04-10 | **Depends on**: Phase 24 (v2 Swarm Redesign)

---

## Executive Summary

This plan defines two converging workstreams that transform Opensens Agent Swarm from a capable but fragmented system into a self-improving, knowledge-compounding research platform:

1. **LLM Wiki** -- A Karpathy-pattern knowledge system where DarkLab's research agents don't just produce outputs, they build and maintain a living, cross-referenced, machine-navigable wiki. Every campaign compounds into permanent organizational knowledge.

2. **Harness Engineering** -- Systematic optimization of the Claude Code harness (CLAUDE.md, skills, agents, hooks, MCP servers) plus an eval-driven development loop that measures and improves agent performance continuously.

Together, these create a flywheel: better knowledge makes agents smarter, better harness engineering makes agents more reliable, and eval-driven feedback closes the loop.

### Key Metrics (Before/After Targets)

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Knowledge reuse across campaigns | ~0% (no cross-campaign retrieval) | >60% of campaigns cite prior findings | KB query logs |
| CLAUDE.md context cost | ~800 lines loaded every turn | <80 lines (10x reduction) | Token count |
| Task completion rate | Unknown (not measured) | >95% with eval tracking | Eval harness |
| Cost per successful research task | Unknown | Measured + Pareto-optimized | Budget middleware |
| Knowledge conflicts detected | 0 (no detection) | All contradictions flagged | KAIROS metrics |
| Harness change regression rate | Unknown | 0% (eval gate in CI) | Eval suite |

---

## Part 1: LLM Wiki -- DarkLab Knowledge System

### 1.1 Architecture Overview

Adopt the Karpathy LLM Wiki pattern (April 2026) adapted for a multi-agent research swarm operating on constrained local hardware:

```
~/.darklab/wiki/
    raw/                    # Immutable source documents (papers, sim results, data)
    wiki/                   # LLM-compiled entity pages, concept summaries, cross-refs
        index.md            # Master catalog (fits in Leader context window)
        entities/           # One .md per entity (BMIM-BF4, graphene, MoS2, ...)
        concepts/           # One .md per concept (DFT methods, ionic liquids, ...)
        campaigns/          # One .md per completed campaign (summary + outcomes)
        lessons/            # Cross-campaign lessons (upgraded from global_lessons.jsonl)
    log.md                  # Append-only operation log (who changed what, when, why)
    embeddings/             # LanceDB index for semantic search
    entities.db             # SQLite entity-relationship graph
```

### 1.2 Three-Layer Storage (Hot/Warm/Cold)

| Tier | Technology | Purpose | Node | RAM |
|------|-----------|---------|------|-----|
| **Hot** | OpenViking | Active session context, tiered L0/L1/L2 retrieval, agent memory | Leader | ~512 MB |
| **Warm** | LanceDB (embedded) | Semantic search over all wiki pages + entity embeddings | DEV | ~1 GB (mmap) |
| **Cold** | JSONL + SQLite | Append-only audit trail, full text archive, entity graph, offline fallback | Both | ~200 MB |

**Why these choices:**
- **OpenViking** is already integrated and its tiered retrieval (L0 abstract / L1 overview / L2 full) maps perfectly to wiki navigation
- **LanceDB** over ChromaDB: embedded (no server process), Lance columnar format with zero-copy access, 100x faster than Parquet for vector queries, fits easily on 24GB Mac mini
- **SQLite** for entity graph over Neo4j: current scale (thousands of entries) doesn't justify a graph server. Upgrade path to Kuzu (embedded graph DB) if entity count exceeds 100K

### 1.3 Local Embedding Model

**Primary**: `all-MiniLM-L6-v2` via `mlx-embeddings`
- 384-dimension vectors, 22M parameters, ~80 MB RAM
- 14.7ms per 1K tokens on Apple Silicon
- Quality: 68.06 MTEB (sufficient for research knowledge retrieval)
- Runs entirely local -- no API calls, compatible with confidential missions

**Fallback**: `nomic-embed-text-v1.5` via Ollama (already on Leader)
- 768 dimensions, better multilingual, ~300 MB RAM
- Use when MiniLM quality is insufficient for cross-lingual research

### 1.4 Five Core Operations

#### 1.4.1 INGEST -- Source Ingestion Pipeline

```
Campaign step completes
    -> CampaignReflector.reflect_on_step() (existing)
    -> KnowledgeIngester.ingest(step_result)
        -> extract_entities(text)       # Gemma 4 E4B structured output
        -> extract_claims(text)         # Claims with confidence scores
        -> link_to_campaign(id, step)   # Provenance tracking
        -> write_wiki_pages()           # Create/update entity + concept pages
        -> update_index_md()            # Rebuild master catalog
        -> write_to_openviking()        # Hot tier: tiered content
        -> index_embeddings()           # Warm tier: LanceDB vectors
        -> append_to_log()              # Cold tier: operation log
        -> emit DRVP: knowledge.ingested
```

Entity extraction uses Leader's Gemma 4 E4B with structured output (JSON mode). For higher quality on important findings, borrow DEV's 27B MoE. No external NER models needed.

#### 1.4.2 QUERY -- Knowledge Retrieval

Context-aware retrieval scoped by agent role:

| Agent | Retrieves | Source | Scope |
|-------|-----------|--------|-------|
| Leader | Campaign history, strategic summaries, decision rationale, prior reflections | OpenViking L0/L1 + `index.md` | `viking://knowledge`, `viking://research` |
| DEV | Technical parameters, simulation configs, model training history, code patterns | LanceDB semantic search | `evidence_type in (SIMULATION, EXPERIMENT, ANALYSIS)` |
| Boss | Human-readable summaries, approval history, cost trends | Paperclip dashboard + OpenViking L0 | All scopes, L0 only |

```python
class RetrievalRouter:
    """Role-aware knowledge retrieval."""

    async def retrieve(
        self, query: str, role: str, task_type: str, top_k: int = 5
    ) -> list[KnowledgeArtifact]:
        if role == "leader":
            # Index-first: read index.md, navigate to specific pages
            return await self._leader_retrieve(query, task_type)
        elif role == "dev":
            # Embedding-first: semantic search over execution knowledge
            return await self._dev_retrieve(query, task_type)
        elif role == "boss":
            # Summary-first: L0 abstracts only
            return await self._boss_retrieve(query)
```

#### 1.4.3 COMPILE -- Page Generation

When enough raw material accumulates on a topic, compile a wiki page:

1. Gather all KB entries, entity mentions, and campaign results related to the topic
2. Generate a structured markdown page with sections: Summary, Key Findings, Methods, Open Questions, Sources
3. Cross-link to related entity and concept pages (bidirectional `[[backlinks]]`)
4. Write tiered content to OpenViking (L0: 1-paragraph abstract, L1: key findings, L2: full page)

Compilation runs as a KAIROS background task (nice 19) using borrowed DEV inference for synthesis quality.

#### 1.4.4 LINT -- Knowledge Health Checks

Upgrade KAIROS autoDream from hash-dedup to full wiki linting:

| Check | Current (autoDream) | Upgraded |
|-------|-------------------|----------|
| Duplicates | SHA-256 hash (exact match) | Embedding cosine similarity > 0.92 |
| Staleness | Age > 90 days -> delete | Age > 90 days -> mark `stale`, exclude from retrieval, preserve for provenance |
| Contradictions | None | Confidence-weighted conflict detection + escalation |
| Orphans | None | Pages with zero inbound links flagged for review |
| Completeness | Source count < 3 -> gap | Source count < 3 AND topic referenced in recent campaigns -> priority gap |
| Cross-refs | None | Missing bidirectional links detected and auto-created |

#### 1.4.5 SYNC -- Leader <-> DEV Knowledge Flow

Leader is the knowledge authority. DEV contributes execution results:

```
Leader -> DEV: Task delegation includes relevant wiki context in payload
               (via MemoryMiddleware.pre_load, already exists)

DEV -> Leader: Task results flow back via JSON-RPC response
               Leader's KnowledgeIngester processes and stores

Nightly sync:  KAIROS pulls DEV's local KB entries via HTTP
               One-way merge into Leader's wiki + OpenViking
               Conflicts flagged via kairos.conflict.detected DRVP event
```

### 1.5 Conflict Resolution Protocol

When two knowledge entries on the same topic contradict:

```
Confidence delta > 0.3:
    Auto-resolve: higher-confidence entry becomes primary
    Lower entry marked as `superseded_by: {primary_id}`
    Emit: knowledge.conflict.auto_resolved

Confidence delta <= 0.3:
    Escalate: emit kairos.conflict.detected DRVP event
    Queue /debate command for multi-perspective analysis
    Both entries preserved with status: `disputed`
    Leader or Boss resolves manually

Either entry confidence < 0.3:
    Low-confidence entry marked as `unverified`
    Excluded from retrieval until corroborated
```

### 1.6 Actor-Aware Memory (Mem0 v2 Pattern)

Tag every wiki write with provenance metadata:

```python
@dataclass(frozen=True)
class KnowledgeProvenance:
    agent_id: str       # Which agent produced this
    mission_id: str     # Which mission context
    campaign_id: str    # Which campaign step
    model_tier: str     # Which model tier was used
    confidence: float   # Producer's self-assessed confidence
    timestamp: datetime
    sources: list[str]  # DOIs, URLs, file paths
```

This prevents one agent's speculation from being treated as ground truth by downstream agents. The `RetrievalRouter` can filter by provenance -- e.g., only return findings from REASONING_LOCAL or higher tiers for synthesis tasks.

### 1.7 Temporal Versioning (Zep Pattern)

Research findings evolve. Every wiki fact carries temporal metadata:

```markdown
<!-- entities/bmim-bf4.md -->
# BMIM-BF4

## Properties
- Viscosity: 154 mPa·s at 25°C [source: DOI:10.1021/..., as of 2026-03-15, confidence: 0.92]
- Thermal stability: up to 350°C [source: campaign:DL-2026-042, as of 2026-04-01, confidence: 0.78]

## Superseded Claims
- ~~Viscosity: 180 mPa·s at 25°C~~ [superseded by DOI:10.1021/... on 2026-03-15]
```

Lint passes flag facts older than `retention_days` without re-confirmation.

---

## Part 2: Harness Engineering -- Systematic Agent Optimization

### 2.1 CLAUDE.md Restructuring

**Problem**: Current CLAUDE.md is ~800 lines, loaded on every turn, consuming ~15K tokens of context budget. The recommended maximum is 60 lines.

**Solution**: Extract details into on-demand skills, keep CLAUDE.md as a navigation hub:

```markdown
# CLAUDE.md (target: ~70 lines)

## Identity
Opensens Agent Swarm (OAS) -- 4-layer research swarm on DarkLab Mac mini cluster.
v2 architecture: Boss -> OAS Control Plane -> Leader -> DEV.

## Quick Reference
- Tests: `.venv/bin/pytest cluster/tests/ -q` (291) | `.venv/bin/pytest core/tests/ -q` (881)
- Python 3.11+, Pydantic v2, async/await. Model IDs: claude-opus-4-6, claude-sonnet-4-6
- Config: env vars via `shared.config.Settings`, dotenv from `~/.darklab/.env`
- core/ uses stdlib logging (oas.*); cluster/ uses structlog -- don't mix
- Optional deps guarded: SWARM_AVAILABLE, _WS_AVAILABLE, _NACL_AVAILABLE, DEERFLOW_AVAILABLE

## Architecture (load /darklab-swarm-ops for details)
Boss (any device) -> OAS Control Plane -> Leader (cyber02, 16GB) -> DEV (cyber01, 24GB)
7-tier model taxonomy: PLANNING_LOCAL -> REASONING_LOCAL -> WORKER_LOCAL -> CODE_LOCAL -> RL_EVOLVED -> CLAUDE_SONNET -> CLAUDE_OPUS

## Current Phase
Phase 24 (v2 Swarm Redesign) -- see docs/OAS-V2-MERGED-PLAN.md
Phase 25 planned: Self-evolution + Multi-device

## Conventions
- Paths: settings.darklab_home (not Path.home())
- All modules export via __all__; no circular imports
- frameworks/ is read-only reference -- import and wrap in core/
```

**Detailed content moves to skills:**
- Architecture details -> `/darklab-swarm-ops`
- Routing table -> `/darklab-swarm-ops`
- DRVP protocol -> new `/darklab-drvp-events` skill
- Directory structure -> derivable from codebase (remove)
- Module descriptions -> derivable from codebase (remove)
- Integration references -> existing integration plan docs
- Development status table -> `docs/COMPLETED-PHASE-TASKS.md`

### 2.2 New Skills (7 additions)

| Skill | Purpose | Replaces |
|-------|---------|----------|
| `darklab-drvp-events` | 79 event types, emission patterns, consumer handling | CLAUDE.md DRVP section |
| `darklab-model-routing` | 7-tier taxonomy, degradation chain, cost estimation, routing context | CLAUDE.md model routing details |
| `darklab-kairos-ops` | Heartbeat, autoDream, proactive suggestions, wiki lint, daemon lifecycle | None (gap) |
| `darklab-plan-authoring` | Plan-file YAML+MD format, v2 fields, validation rules, Plan Store protocol | CLAUDE.md plan sections |
| `darklab-memory-ops` | OpenViking operations, tiered retrieval, session continuity, wiki queries | None (gap) |
| `darklab-knowledge-wiki` | Wiki page authoring, entity extraction, cross-referencing, lint rules | None (gap) |
| `darklab-eval-harness` | Golden set management, eval scoring, Pareto analysis, CI integration | None (gap) |

### 2.3 New Agents (3 additions)

| Agent | Role | Model Tier |
|-------|------|------------|
| `knowledge-curator` | Wiki page compilation, entity linking, conflict resolution, lint | REASONING_LOCAL (DEV 27B) |
| `gap-researcher` | Acts on ProactiveSuggester output, fills knowledge gaps autonomously | WORKER_LOCAL (DEV pool) |
| `eval-analyst` | Runs golden set evals, compares configs, produces regression reports | PLANNING_LOCAL (Leader E4B) |

### 2.4 New MCP Servers (4 additions)

| Server | Tools Exposed | Priority |
|--------|--------------|----------|
| `model-router` | `query_tier(task_type, context)`, `explain_decision(routing_id)`, `list_models()`, `estimate_cost(task, tokens)` | HIGH |
| `openviking-memory` | `memory_read(uri, level)`, `memory_write(uri, content)`, `memory_search(query, scope)` | HIGH |
| `wiki-knowledge` | `wiki_query(topic)`, `wiki_ingest(content, source)`, `wiki_lint()`, `wiki_entities(query)` | MEDIUM |
| `plan-store` | `list_plans()`, `get_plan(id)`, `validate_plan(yaml)`, `plan_history(id)` | MEDIUM |

### 2.5 New Commands (4 additions)

| Command | Function |
|---------|----------|
| `/kairos` | `status` / `heartbeat` / `autodream` / `suggest` / `lint` |
| `/wiki` | `query <topic>` / `ingest <path>` / `lint` / `stats` / `entities` |
| `/model-route` | `<task_type> [context]` -- inspect routing decision for a task |
| `/eval` | `run` / `compare <config_a> <config_b>` / `baseline` / `report` |

### 2.6 Hook Enhancements

| Hook | Type | Trigger | Action |
|------|------|---------|--------|
| `post-edit-typecheck` | PostToolUse (Edit/Write) | Python file edited | Run `mypy --strict` on changed file |
| `stop-coverage-check` | Stop | Session ends | Verify test coverage >= 80% for changed files |
| `pre-compact-summary` | PreCompact | Context compaction | Write structured session summary to wiki log |
| `post-step-ingest` | PostToolUse (Bash) | Campaign step completes | Trigger KnowledgeIngester if step produced findings |

### 2.7 CLAUDE.md Layering Strategy

Following Martin Fowler's "harnessability" principle -- progressive disclosure:

```
Layer 0: CLAUDE.md (~70 lines)          -- Always loaded, every turn
Layer 1: Skills (on-demand)              -- Loaded when task matches
Layer 2: MCP tools (deferred)            -- Schema loaded only when called
Layer 3: Wiki pages (retrieved)          -- Semantic search, role-scoped
Layer 4: Full docs (explicit read)       -- Only when agent reads a file
```

This reduces baseline context from ~15K tokens to ~2K tokens, with deeper knowledge available on demand.

---

## Part 3: Eval-Driven Development Loop

### 3.1 Golden Set Construction

Build from existing campaign history. Target: 50 tasks across all major types:

| Task Type | Count | Source | Quality Annotation |
|-----------|-------|--------|-------------------|
| RESEARCH | 10 | Past literature reviews | Expert-graded summaries |
| SIMULATE | 8 | Past DFT/simulation runs | Verified parameter sets + outputs |
| SYNTHESIZE | 8 | Past multi-source syntheses | Human-rated coherence + accuracy |
| DOE | 5 | Past experimental designs | Correct factors, levels, design type |
| DEEP_RESEARCH | 5 | Past deep research campaigns | Recall against expert-curated source list |
| LITERATURE | 5 | Past literature searches | Precision/recall on known papers |
| ANALYZE | 5 | Past analysis runs | Verified conclusions |
| AUTORESEARCH | 4 | Past automated research | End-to-end quality score |

Store in `core/tests/eval_golden/` as YAML fixtures with ground-truth annotations.

### 3.2 Five-Dimension Scoring Rubric

| Dimension | Weight | 1 (Poor) | 3 (Acceptable) | 5 (Excellent) |
|-----------|--------|----------|-----------------|----------------|
| **Completeness** | 25% | Addresses <50% of question | Covers main points | Comprehensive, all aspects |
| **Accuracy** | 25% | Contains factual errors | Mostly correct | Verifiably correct, well-sourced |
| **Source Quality** | 20% | No sources or irrelevant | Some relevant sources | Primary literature, recent, high-impact |
| **Synthesis** | 20% | Lists facts without connection | Basic analysis | Novel connections, actionable insights |
| **Cost Efficiency** | 10% | Excessive cloud escalation | Reasonable tier usage | Optimal tier selection per task |

### 3.3 Eval Infrastructure

New module `core/oas_core/eval/`:

```
core/oas_core/eval/
    __init__.py
    runner.py          # Loads golden set, runs agents, collects outputs
    scorer.py          # Deterministic rubric + optional LLM scorer
    store.py           # Persists results linked to config version + commit hash
    compare.py         # Statistical comparison of two configs (paired t-test)
    pareto.py          # Cost vs quality analysis per task type per model tier
    reporter.py        # Generates eval report (markdown + DRVP events)
```

### 3.4 Eval-Gated CI

```
PR touches prompts/skills/routing/model config
    -> CI runs: .venv/bin/pytest core/tests/test_evals.py
        -> Loads golden set (50 tasks)
        -> Runs against current config (baseline) and PR config (challenger)
        -> Scores both on 5-dimension rubric
        -> Compare: challenger must score >= baseline on ALL dimensions
            -> PASS: merge allowed
            -> FAIL: block merge, show regression report with per-dimension deltas
```

Baselines stored in `core/tests/eval_baselines/` as JSON, updated only with explicit human approval.

### 3.5 Generator-Evaluator Loop

Adopt Anthropic's GAN-style pattern for complex campaigns:

```
Generator (implementation agent):
    Produces research output for campaign step
    Self-evaluates (quick check)
    Hands off structured result

Evaluator (separate agent, fresh context):
    Receives result + rubric + golden set examples
    Scores on 5 dimensions
    Identifies specific weaknesses with citations

    Score >= threshold (3.5/5.0)?
        YES -> Accept, proceed to next step
        NO  -> Return critique to Generator
               Generator retries with critique injected
               Max 2 retries per step

    Cost insight: Evaluator runs on PLANNING_LOCAL (cheap)
                  Generator runs on REASONING_LOCAL or higher
                  Net quality improvement: 15-30% at 20-40% cost increase
```

### 3.6 Cost-Quality Pareto Optimization

For each task type, run the golden set at each viable model tier and plot:

```
Quality (0-5)
    ^
5.0 |                                              * OPUS
    |                                    * SONNET
4.0 |                          * REASONING_LOCAL
    |               * RL_EVOLVED
3.0 |    * PLANNING_LOCAL
    |
    +------------------------------------------------> Cost ($)
    $0.00  $0.01        $0.03            $0.15
```

Encode findings into `ModelRouter.route_v2()`:
- If REASONING_LOCAL scores >= 3.5 for a task type, never escalate to Sonnet for that type
- If RL_EVOLVED with LoRA scores >= REASONING_LOCAL, prefer it (zero cost + specialized)
- Sonnet threshold: only when local quality < 3.0 AND task importance > medium

### 3.7 Production Feedback Loop

```
Production campaigns
    -> 10% sampled for human scoring (via Paperclip approval UI)
    -> Scores feed into:
        1. Eval golden set expansion (high-quality examples with human annotations)
        2. KAIROS RL candidate curation (quality_score >= 0.7 -> training data)
        3. ModelRouter threshold tuning (empirical tier boundaries)
        4. Skill refinement (lowest-scoring skills get variant testing)
    -> Monthly cycle:
        - Generate 10 variants of 3 worst-performing skills
        - Run all through eval suite
        - Promote winners
        - Archive losers with scores for reference
```

---

## Part 4: Implementation Roadmap

### Sprint 1: Foundation (Week 1-2)

| # | Task | Component | LOC Est. | Tests |
|---|------|-----------|----------|-------|
| 1 | Restructure CLAUDE.md to ~70 lines, extract details to skills | Harness | -700 | -- |
| 2 | Create 7 new skills (drvp-events, model-routing, kairos-ops, plan-authoring, memory-ops, knowledge-wiki, eval-harness) | Harness | ~2,100 | -- |
| 3 | Create `core/oas_core/knowledge/__init__.py` facade | Wiki | ~50 | 5 |
| 4 | Install `mlx-embeddings` + `lancedb` on both Macs | Infra | -- | 2 |
| 5 | Build `EmbeddingIndex` wrapper around LanceDB | Wiki | ~120 | 8 |
| 6 | Build wiki directory structure (`~/.darklab/wiki/`) | Wiki | ~80 | 5 |
| 7 | Build golden set fixtures (20 initial tasks) | Eval | ~500 | 20 |

**Sprint 1 deliverables**: Leaner CLAUDE.md, 7 new skills, wiki directory, embedding index, initial golden set.

### Sprint 2: Ingestion + Retrieval (Week 3-4)

| # | Task | Component | LOC Est. | Tests |
|---|------|-----------|----------|-------|
| 8 | Build `KnowledgeIngester` with Gemma-based entity extraction | Wiki | ~200 | 12 |
| 9 | Build `EntityStore` (SQLite: entities, relationships, claims) | Wiki | ~180 | 10 |
| 10 | Build `RetrievalRouter` with role-scoped retrieval | Wiki | ~150 | 8 |
| 11 | Wire `KnowledgeIngester` into middleware pipeline (post-step hook) | Wiki | ~60 | 5 |
| 12 | Build `eval/runner.py` + `eval/scorer.py` | Eval | ~250 | 15 |
| 13 | Create `model-router` MCP server | Harness | ~200 | 8 |
| 14 | Create `openviking-memory` MCP server | Harness | ~180 | 8 |

**Sprint 2 deliverables**: Working ingestion pipeline, role-scoped retrieval, eval runner, 2 MCP servers.

### Sprint 3: Wiki Operations + Eval Loop (Week 5-6)

| # | Task | Component | LOC Est. | Tests |
|---|------|-----------|----------|-------|
| 15 | Build wiki page compiler (entity + concept pages) | Wiki | ~250 | 10 |
| 16 | Build `index.md` auto-generator | Wiki | ~100 | 5 |
| 17 | Upgrade KAIROS autoDream with embedding-based dedup | Wiki | ~150 | 8 |
| 18 | Build `ConflictResolver` (confidence-weighted + escalation) | Wiki | ~180 | 12 |
| 19 | Build `eval/compare.py` + `eval/pareto.py` | Eval | ~200 | 10 |
| 20 | Wire eval into CI (GitHub Action) | Eval | ~80 | 5 |
| 21 | Build Generator-Evaluator loop in CampaignEngine | Eval | ~150 | 8 |
| 22 | Add 4 new commands (/kairos, /wiki, /model-route, /eval) | Harness | ~400 | -- |

**Sprint 3 deliverables**: Wiki compilation + lint, conflict resolution, eval CI gate, Generator-Evaluator loop, 4 commands.

### Sprint 4: Integration + Polish (Week 7-8)

| # | Task | Component | LOC Est. | Tests |
|---|------|-----------|----------|-------|
| 23 | Build Leader <-> DEV knowledge sync protocol | Wiki | ~180 | 10 |
| 24 | Add 8 DRVP event types (`knowledge.*`, `eval.*`, `wiki.*`) | Protocol | ~100 | 8 |
| 25 | Build Office KnowledgePanel component | Office | ~300 | 5 |
| 26 | Build Office EvalDashboard component | Office | ~250 | 5 |
| 27 | Create 3 new agents (knowledge-curator, gap-researcher, eval-analyst) | Harness | ~300 | -- |
| 28 | Add hook enhancements (typecheck, coverage, pre-compact summary) | Harness | ~120 | 4 |
| 29 | Create `wiki-knowledge` + `plan-store` MCP servers | Harness | ~350 | 12 |
| 30 | Expand golden set to 50 tasks, run full Pareto analysis | Eval | ~300 | 30 |

**Sprint 4 deliverables**: Cross-node sync, DRVP events, Office panels, 3 agents, 2 MCP servers, full golden set.

### Total Estimates

| Category | New LOC | New Tests | New Skills | New Agents | New MCP Servers | New Commands |
|----------|---------|-----------|------------|------------|-----------------|--------------|
| LLM Wiki | ~1,700 | ~100 | 1 | 2 | 1 | 1 |
| Harness Engineering | ~3,300 | ~30 | 6 | 1 | 3 | 3 |
| Eval System | ~1,480 | ~90 | 1 | -- | -- | 1 |
| **Total** | **~6,480** | **~220** | **8** | **3** | **4** | **5** |

Post-implementation test count: ~1,420 (current 1,200 + 220 new).

---

## Part 5: Dependencies & Risks

### New Dependencies

| Package | Purpose | Size | Node |
|---------|---------|------|------|
| `mlx-embeddings` | Local embedding generation on Apple Silicon | ~80 MB model | Both |
| `lancedb` | Embedded vector database | pip install, no server | DEV |
| `all-MiniLM-L6-v2` | Embedding model (via mlx-embeddings) | ~80 MB | Both |

No new server processes. No cloud services. All local-first.

### Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Embedding quality insufficient for research domain | Poor retrieval, missed connections | LOW | MiniLM benchmarks well on scientific text; fallback to nomic-embed via Ollama |
| LanceDB performance on 16GB Leader | Slow wiki queries | LOW | LanceDB uses mmap; index lives on DEV, Leader queries via HTTP |
| CLAUDE.md restructuring breaks existing workflows | Agent confusion, regressions | MEDIUM | Run full test suite + eval golden set before/after; gradual migration |
| Golden set bias | Evals optimize for past patterns, miss novel tasks | MEDIUM | Expand golden set monthly; include adversarial examples |
| Wiki page explosion | Too many pages for index.md to fit in context | LOW | At current scale (~1K pages), index.md is ~50KB. Threshold: switch to hierarchical index at 5K pages |
| Entity extraction quality with local models | Missed entities, wrong relationships | MEDIUM | Use structured output mode; validate with simple rules; borrow DEV 27B for important campaigns |

### What NOT to Build

Based on research findings, explicitly avoid:

1. **Vector database server** (Qdrant, Weaviate, Pinecone) -- LanceDB embedded is sufficient at current scale
2. **Full graph database** (Neo4j) -- SQLite entity graph is sufficient until 100K+ entities
3. **Mem0 or Zep cloud services** -- OAS has its own memory layer; confidentiality model requires local-only
4. **Real-time GraphRAG indexing** -- too compute-intensive for 16GB Mac mini; defer community detection to monthly batch on DEV
5. **Auto-generated CLAUDE.md** -- research confirms human-curated is strictly better
6. **Full bidirectional Leader<->DEV sync** -- Leader is knowledge authority; one-way pull is sufficient

---

## Part 6: Success Criteria

### Phase Gate: Wiki System (end of Sprint 2)

- [ ] Wiki directory structure created and populated from existing KB
- [ ] Entity extraction producing valid entities from 3 test campaigns
- [ ] Semantic search returning relevant results for 10 test queries
- [ ] `index.md` auto-generated and fits in <4K tokens
- [ ] DRVP `knowledge.ingested` events flowing to Office EventTimeline

### Phase Gate: Harness Optimization (end of Sprint 3)

- [ ] CLAUDE.md reduced to <80 lines, all tests still passing
- [ ] 7 new skills loadable via `/skill-name`
- [ ] 2 MCP servers (model-router, openviking-memory) responding to tool calls
- [ ] Eval golden set of 30+ tasks with ground-truth annotations
- [ ] Eval runner producing 5-dimension scores for all golden set tasks

### Phase Gate: Closed Loop (end of Sprint 4)

- [ ] Generator-Evaluator loop active in CampaignEngine, measurable quality improvement
- [ ] Eval CI gate blocking PRs that regress on any dimension
- [ ] Pareto analysis completed for all task types, routing thresholds updated
- [ ] Wiki lint running nightly via KAIROS, conflict resolution active
- [ ] Knowledge reuse rate >30% (campaigns citing prior wiki findings)
- [ ] Office KnowledgePanel and EvalDashboard deployed

---

## Appendix A: Research Sources

### LLM Wiki
- Karpathy, A. (2026). "LLM Wiki" [GitHub Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- SamurAIGPT/llm-wiki-agent (1,471 stars) -- Self-maintaining KB with entity pages
- Microsoft GraphRAG -- Graph-based RAG with community hierarchies
- SuperLocalMemory V3.3 (arXiv 2604.04514) -- Zero-cloud memory, 87.7% accuracy

### Harness Engineering
- Anthropic (2026). "Harness Design for Long-Running Application Development"
- Fowler, M. (2026). "Harness Engineering for Coding Agent Users"
- HumanLayer (2026). "Skill Issue -- Harness Engineering for Coding Agents"
- Osmani, A. (2026). "The Code Agent Orchestra" -- Multi-agent orchestration patterns

### Multi-Agent Knowledge Systems
- Mem0 (arXiv 2504.19413) -- Hybrid vector+graph agent memory, 26% improvement
- Zep/Graphiti -- Temporal knowledge graph, 18.5% accuracy improvement
- KARMA (arXiv 2502.06472) -- 9-agent knowledge graph enrichment
- CrewAI Memory Architecture -- Four-type memory (short/long/entity/procedural)

### Eval-Driven Development
- LangChain (2026). Agent harness optimization: 52.8% -> 66.5% through harness-only changes
- Masood, A. (2026). "Eval-Driven Development: The Missing Discipline in the Agentic AI Lifecycle"
- Everything Claude Code v1.10.0 -- 156 skills, instinct-based continuous learning

## Appendix B: TASK_SKILL_MAP Updates

```python
# Additions to core/oas_core/subagents/claude_code.py
TASK_SKILL_MAP.update({
    "KAIROS":          ["darklab-kairos-ops", "darklab-knowledge-wiki"],
    "WIKI_COMPILE":    ["darklab-knowledge-wiki", "darklab-memory-ops"],
    "WIKI_LINT":       ["darklab-knowledge-wiki", "darklab-kairos-ops"],
    "EVAL_RUN":        ["darklab-eval-harness", "benchmark"],
    "PLAN_AUTHOR":     ["darklab-plan-authoring", "darklab-swarm-ops"],
    "MODEL_INSPECT":   ["darklab-model-routing"],
})
```

## Appendix C: New DRVP Event Types

| Event | Payload | Emitter |
|-------|---------|---------|
| `knowledge.ingested` | `{topic, entity_count, claim_count, source, campaign_id}` | KnowledgeIngester |
| `knowledge.conflict.detected` | `{topic, entry_a_id, entry_b_id, confidence_delta}` | ConflictResolver |
| `knowledge.conflict.auto_resolved` | `{topic, winner_id, loser_id, reason}` | ConflictResolver |
| `knowledge.page.compiled` | `{page_path, entity_count, cross_refs, tier}` | WikiCompiler |
| `wiki.lint.completed` | `{duplicates, stale, orphans, conflicts, duration_s}` | KAIROS autoDream |
| `wiki.sync.completed` | `{entries_pulled, conflicts, merged, duration_s}` | KAIROS nightly sync |
| `eval.run.completed` | `{golden_set_size, avg_score, per_dimension, config_hash}` | EvalRunner |
| `eval.regression.detected` | `{dimension, baseline, challenger, delta, pr_url}` | EvalCompare |
