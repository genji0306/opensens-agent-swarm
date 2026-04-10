# LLM Wiki & Harness Engineering — Adaptation Plan for OAS

> **Status**: Active | **Target**: Phase 25 (Sprint 1-4) | **Depends on**: Phase 24 complete
> **Date**: 2026-04-10 | **Source**: `docs/LLM-WIKI-HARNESS-ENGINEERING-PLAN.md`

---

## 1. What This Plan Does

Adapts the two-workstream LLM Wiki + Harness Engineering plan to the **actual current state** of Opensens Agent Swarm. The original plan (647 lines) describes the vision; this document maps that vision onto what exists today, what's missing, what to build first, and what to skip or defer.

### Decision Framework

Every item from the original plan falls into one of four buckets:

| Bucket | Meaning | Action |
|--------|---------|--------|
| **BUILD** | Missing and needed | Implement in sprint order |
| **EXTEND** | Foundation exists, needs upgrade | Modify existing module |
| **DEFER** | Valuable but not blocking | Park for Phase 26 |
| **SKIP** | Already solved or unnecessary | Do nothing |

---

## 2. Gap Analysis — What Exists vs What's Needed

### 2.1 Wiki System

| Component | Original Plan | Current State | Bucket |
|-----------|--------------|---------------|--------|
| Wiki directory (`~/.darklab/wiki/`) | Sprint 1 | Missing | **BUILD** |
| `core/oas_core/knowledge/` facade | Sprint 1 | Missing | **BUILD** |
| `KnowledgeIngester` | Sprint 2 | Missing | **BUILD** |
| `EntityStore` (SQLite) | Sprint 2 | Missing | **BUILD** |
| `RetrievalRouter` (role-scoped) | Sprint 2 | Missing | **BUILD** |
| `EmbeddingIndex` (LanceDB) | Sprint 1 | Missing; `lancedb` not installed | **BUILD** |
| Local embeddings (`mlx-embeddings`) | Sprint 1 | Missing; not installed | **BUILD** |
| Wiki page compiler | Sprint 3 | Missing | **BUILD** |
| `index.md` auto-generator | Sprint 3 | Missing | **BUILD** |
| Conflict resolver | Sprint 3 | Missing | **BUILD** |
| Leader↔DEV knowledge sync | Sprint 4 | Missing | **DEFER** (needs DEV online) |
| OpenViking tiered memory | All sprints | **Complete** (`memory.py`, 264 LOC) | **SKIP** |
| KAIROS autodream | Sprint 3 | **Complete** (hash dedup) | **EXTEND** to embedding dedup |
| KAIROS proactive suggestions | Sprint 3 | **Complete** (gap detection) | **EXTEND** to wiki lint |

### 2.2 Harness Engineering

| Component | Original Plan | Current State | Bucket |
|-----------|--------------|---------------|--------|
| CLAUDE.md restructure (716→~70 lines) | Sprint 1 | 716 lines, monolithic | **BUILD** (highest priority) |
| 7 new skills | Sprint 1 | 11 exist in `.claude/skills/` | **BUILD** (7 new) |
| 3 new agents | Sprint 4 | 11 exist in `.claude/agents/` | **BUILD** (3 new) |
| 4 MCP servers | Sprint 2-4 | 3 exist (code-review-graph, sequential-thinking, github) | **BUILD** (4 new) |
| 4 new commands | Sprint 3 | 28 cluster skill commands exist | **BUILD** |
| Hook enhancements (4) | Sprint 4 | 3 hooks active (block-no-verify, command-log-audit, console-warn) | **BUILD** (4 new) |
| CLAUDE.md layering (L0-L4) | Sprint 1 | No layering — everything in L0 | **BUILD** |

### 2.3 Eval System

| Component | Original Plan | Current State | Bucket |
|-----------|--------------|---------------|--------|
| `core/oas_core/eval/` module | Sprint 2-3 | Missing | **BUILD** |
| Golden set fixtures | Sprint 1 | Missing (`core/tests/eval_golden/` absent) | **BUILD** |
| 5-dimension scoring rubric | Sprint 2 | `evaluation.py` has 4-criteria `RuleBasedEvaluator` | **EXTEND** |
| Eval-gated CI | Sprint 3 | No eval in CI | **BUILD** |
| Generator-Evaluator loop | Sprint 3 | Missing | **BUILD** |
| Pareto cost-quality analysis | Sprint 3 | Missing | **DEFER** (needs production data) |
| Production feedback loop | Sprint 4 | Missing | **DEFER** (needs Paperclip UI) |

---

## 3. Prioritized Sprint Plan

### Guiding Principle

**Harness first, then wiki, then eval.** Rationale:
1. CLAUDE.md restructuring is zero-risk and immediately saves ~13K tokens per turn
2. Skills/agents are harness scaffolding that wiki and eval modules plug into
3. Wiki needs embeddings + LanceDB installed (hardware dependency)
4. Eval needs a golden set (requires curating past campaign outputs)

### Sprint 1: Harness Lean-Out (Week 1-2)

**Goal**: Reduce CLAUDE.md from 716→~70 lines. Create 7 new skills. Install embedding dependencies.

| # | Task | Type | Est. LOC | Tests | Priority |
|---|------|------|----------|-------|----------|
| 1 | **Restructure CLAUDE.md** — extract routing table, DRVP protocol, architecture details, directory tree, module descriptions into skills. Keep: identity, quick ref, conventions, current phase, test commands | BUILD | -650 net | 0 | P0 |
| 2 | Create skill: `darklab-drvp-events` — 79 event types, emission patterns, consumer handling (extracted from CLAUDE.md + `drvp.py`) | BUILD | ~300 | 0 | P0 |
| 3 | Create skill: `darklab-model-routing` — 7-tier taxonomy, degradation chain, cost estimation (extracted from CLAUDE.md + `model_router.py`) | BUILD | ~250 | 0 | P0 |
| 4 | Create skill: `darklab-kairos-ops` — heartbeat, autoDream, proactive, wiki lint, daemon lifecycle | BUILD | ~200 | 0 | P1 |
| 5 | Create skill: `darklab-plan-authoring` — plan-file YAML+MD format, v2 fields, validation rules | BUILD | ~200 | 0 | P1 |
| 6 | Create skill: `darklab-memory-ops` — OpenViking operations, tiered retrieval, session continuity, wiki queries | BUILD | ~250 | 0 | P1 |
| 7 | Create skill: `darklab-knowledge-wiki` — wiki page authoring, entity extraction, cross-referencing, lint rules | BUILD | ~300 | 0 | P1 |
| 8 | Create skill: `darklab-eval-harness` — golden set management, eval scoring, Pareto analysis, CI integration | BUILD | ~200 | 0 | P2 |
| 9 | Install `lancedb` + `mlx-embeddings` in `core/pyproject.toml` as optional deps `[wiki]` | BUILD | ~10 | 2 | P1 |
| 10 | Create `~/.darklab/wiki/` directory scaffold + `wiki/index.md` template | BUILD | ~30 | 3 | P1 |

**Sprint 1 deliverables**: CLAUDE.md at ~70 lines, 7 new skills loadable via `/skill-name`, wiki directory created, embedding deps available.

**Verification gate**:
- [ ] All 1,200 existing tests still pass
- [ ] CLAUDE.md < 80 lines
- [ ] Each new skill loads without error via `/skill-name`
- [ ] `python -c "import lancedb"` succeeds on both Macs

### Sprint 2: Wiki Foundation + Eval Bootstrap (Week 3-4)

**Goal**: Build the knowledge ingestion pipeline and eval runner. Wire retrieval into existing middleware.

| # | Task | Type | Est. LOC | Tests | Priority |
|---|------|------|----------|-------|----------|
| 11 | Create `core/oas_core/knowledge/__init__.py` facade — public API surface for wiki operations | BUILD | ~60 | 5 | P0 |
| 12 | Build `EmbeddingIndex` wrapper around LanceDB — embed, search, delete, stats | BUILD | ~120 | 8 | P0 |
| 13 | Build `KnowledgeIngester` — entity extraction via Gemma E4B structured output, claim extraction, wiki page write, OpenViking write, embedding index, DRVP emit | BUILD | ~200 | 12 | P0 |
| 14 | Build `EntityStore` — SQLite: entities, relationships, claims with provenance metadata | BUILD | ~180 | 10 | P0 |
| 15 | Build `RetrievalRouter` — role-scoped retrieval (Leader→index-first, DEV→embedding-first, Boss→L0 only) | BUILD | ~150 | 8 | P1 |
| 16 | Wire `KnowledgeIngester` into middleware pipeline as post-step hook | EXTEND | ~60 | 5 | P1 |
| 17 | Build `core/oas_core/eval/runner.py` — loads golden set YAML, runs agents, collects outputs | BUILD | ~150 | 8 | P1 |
| 18 | Build `core/oas_core/eval/scorer.py` — 5-dimension rubric (extend existing 4-criteria `RuleBasedEvaluator`) | EXTEND | ~120 | 8 | P1 |
| 19 | Build golden set fixtures — 20 initial tasks from past campaign outputs | BUILD | ~500 | 20 | P2 |
| 20 | Create `model-router` MCP server — `query_tier()`, `explain_decision()`, `list_models()`, `estimate_cost()` | BUILD | ~200 | 8 | P2 |
| 21 | Create `openviking-memory` MCP server — `memory_read()`, `memory_write()`, `memory_search()` | BUILD | ~180 | 8 | P2 |

**Sprint 2 deliverables**: Working ingestion pipeline, role-scoped retrieval, eval runner + scorer, 20-task golden set, 2 MCP servers.

**Verification gate**:
- [ ] `KnowledgeIngester.ingest()` produces valid wiki pages from 3 test campaign outputs
- [ ] `EmbeddingIndex.search()` returns relevant results for 10 test queries
- [ ] `eval/runner.py` produces 5-dimension scores for all 20 golden set tasks
- [ ] 2 MCP servers respond to tool calls from Claude Code

### Sprint 3: Wiki Operations + Eval Loop (Week 5-6)

**Goal**: Wiki compilation + lint, eval CI gate, Generator-Evaluator loop, new commands.

| # | Task | Type | Est. LOC | Tests | Priority |
|---|------|------|----------|-------|----------|
| 22 | Build wiki page compiler — gather KB entries by topic, generate structured .md, cross-link with `[[backlinks]]`, write tiered OpenViking content | BUILD | ~250 | 10 | P0 |
| 23 | Build `index.md` auto-generator — master catalog fitting <4K tokens | BUILD | ~100 | 5 | P0 |
| 24 | Upgrade KAIROS `autodream.py` — replace SHA-256 hash dedup with embedding cosine similarity >0.92, add staleness marking, orphan detection, cross-ref auto-creation | EXTEND | ~150 | 8 | P1 |
| 25 | Build `ConflictResolver` — confidence-weighted auto-resolve (Δ>0.3), escalation (Δ≤0.3), low-confidence quarantine (<0.3) | BUILD | ~180 | 12 | P1 |
| 26 | Build `core/oas_core/eval/compare.py` — paired t-test between baseline and challenger configs | BUILD | ~120 | 6 | P1 |
| 27 | Wire eval into CI — GitHub Action that blocks PRs regressing on any scoring dimension | BUILD | ~80 | 5 | P1 |
| 28 | Build Generator-Evaluator loop in `CampaignEngine` — separate evaluator agent (fresh context), 2 max retries, score threshold 3.5/5.0 | BUILD | ~150 | 8 | P1 |
| 29 | Add `/kairos` command — `status` / `heartbeat` / `autodream` / `suggest` / `lint` | BUILD | ~100 | 0 | P2 |
| 30 | Add `/wiki` command — `query <topic>` / `ingest <path>` / `lint` / `stats` / `entities` | BUILD | ~100 | 0 | P2 |
| 31 | Add `/model-route` command — `<task_type> [context]` → inspect routing decision | BUILD | ~80 | 0 | P2 |
| 32 | Add `/eval` command — `run` / `compare <a> <b>` / `baseline` / `report` | BUILD | ~80 | 0 | P2 |

**Sprint 3 deliverables**: Wiki compilation + lint, conflict resolution, eval CI gate, Generator-Evaluator loop, 4 slash commands.

**Verification gate**:
- [ ] Wiki compiler produces valid entity + concept pages from test data
- [ ] `index.md` auto-generated and < 4K tokens
- [ ] KAIROS lint detects duplicates, stale entries, orphans in test wiki
- [ ] Eval CI blocks a deliberately-regressed PR in test
- [ ] Generator-Evaluator loop improves quality score by ≥10% on 5 golden set tasks

### Sprint 4: Agents, Hooks, Integration (Week 7-8)

**Goal**: New agents, hook enhancements, remaining MCP servers, Office panels, golden set expansion.

| # | Task | Type | Est. LOC | Tests | Priority |
|---|------|------|----------|-------|----------|
| 33 | Create agent: `knowledge-curator` — wiki page compilation, entity linking, conflict resolution, lint (REASONING_LOCAL) | BUILD | ~100 | 0 | P1 |
| 34 | Create agent: `gap-researcher` — acts on ProactiveSuggester output, fills knowledge gaps autonomously (WORKER_LOCAL) | BUILD | ~100 | 0 | P1 |
| 35 | Create agent: `eval-analyst` — runs golden set evals, compares configs, produces regression reports (PLANNING_LOCAL) | BUILD | ~100 | 0 | P1 |
| 36 | Add hook: `post-edit-typecheck` — run `mypy --strict` on changed Python files | BUILD | ~20 | 2 | P1 |
| 37 | Add hook: `stop-coverage-check` — verify test coverage ≥ 80% for changed files on session end | BUILD | ~30 | 2 | P2 |
| 38 | Add hook: `pre-compact-summary` — write structured session summary to wiki log before context compaction | BUILD | ~40 | 2 | P2 |
| 39 | Add hook: `post-step-ingest` — trigger KnowledgeIngester when campaign step produces findings | BUILD | ~30 | 2 | P1 |
| 40 | Create `wiki-knowledge` MCP server — `wiki_query()`, `wiki_ingest()`, `wiki_lint()`, `wiki_entities()` | BUILD | ~200 | 8 | P2 |
| 41 | Create `plan-store` MCP server — `list_plans()`, `get_plan()`, `validate_plan()`, `plan_history()` | BUILD | ~180 | 8 | P2 |
| 42 | Add 8 new DRVP event types (`knowledge.*`, `eval.*`, `wiki.*`) | BUILD | ~100 | 8 | P1 |
| 43 | Expand golden set from 20→50 tasks with ground-truth annotations | BUILD | ~300 | 30 | P2 |
| 44 | Update `TASK_SKILL_MAP` in `claude_code.py` with 6 new task→skill mappings | EXTEND | ~20 | 3 | P1 |

**Sprint 4 deliverables**: 3 new agents, 4 hooks, 2 MCP servers, 8 DRVP events, 50-task golden set.

**Verification gate**:
- [ ] All 3 agents loadable and respond to test prompts
- [ ] `post-edit-typecheck` hook fires on Python file edits
- [ ] `post-step-ingest` hook triggers KnowledgeIngester after a simulated campaign step
- [ ] 4 MCP servers all respond to tool calls
- [ ] Golden set has 50 tasks; eval runner scores all within expected ranges

---

## 4. CLAUDE.md Restructuring Detail

This is the highest-priority single task. Here's the extraction map:

### What stays in CLAUDE.md (~70 lines)

```
## Identity (5 lines)
OAS v2, 4-layer swarm, DarkLab Mac mini cluster, Phase 24 status

## Quick Reference (10 lines)
Test commands, Python version, model IDs, config pattern, logging split, optional dep guards

## Architecture (8 lines)
Boss → OAS Control Plane → Leader → DEV (one-liner per layer)
Link to /darklab-swarm-ops for details

## Current Phase (5 lines)
Phase 24 status, link to docs/OAS-V2-MERGED-PLAN.md

## Conventions (8 lines)
Paths, imports, frameworks policy, __all__ rule

## Test Commands (5 lines)
pytest invocations for cluster, core, office

## Skills & Agents (5 lines)
Pointer to /darklab-swarm-ops for routing table
Pointer to .claude/ for harness config
```

### What moves to skills

| Current CLAUDE.md Section | Lines | Destination Skill |
|--------------------------|-------|-------------------|
| Architecture (v2) detailed description | ~80 | `darklab-swarm-ops` (extend) |
| Model tier taxonomy + degradation chain | ~40 | `darklab-model-routing` (new) |
| Dispatch flow + routing table | ~50 | `darklab-swarm-ops` (extend) |
| DRVP protocol + event flow | ~60 | `darklab-drvp-events` (new) |
| Budget system | ~15 | `darklab-swarm-ops` (extend) |
| v2 Compute Borrowing | ~30 | `darklab-swarm-ops` (extend) |
| v2 Research Router | ~15 | `darklab-swarm-ops` (extend) |
| v2 KAIROS Daemon | ~20 | `darklab-kairos-ops` (new) |
| Key Modules descriptions | ~120 | **Remove** (derivable from code) |
| Directory Structure tree | ~50 | **Remove** (derivable from `ls`) |
| Development Status table | ~80 | Move to `docs/COMPLETED-PHASE-TASKS.md` |
| Integration Quick Reference | ~30 | `darklab-swarm-ops` (extend) |
| ECC Integration | ~40 | **Remove** (derivable from `.claude/`) |
| Docker stack table | ~15 | `darklab-swarm-ops` (extend) |
| SSH Access | ~5 | **Remove** (ops detail, not code context) |

### Layering model (post-restructure)

```
Layer 0: CLAUDE.md (~70 lines, ~2K tokens)     — always loaded
Layer 1: Skills (on-demand, ~300 lines each)    — loaded when task matches
Layer 2: MCP tools (deferred schema)            — loaded only when called
Layer 3: Wiki pages (semantic retrieval)        — LanceDB + OpenViking
Layer 4: Full docs (explicit read)              — `docs/*.md`
```

**Expected savings**: ~13K tokens per turn → ~2K tokens per turn (85% reduction).

---

## 5. New Dependencies

| Package | Purpose | Install Target | Optional Group | Size |
|---------|---------|---------------|----------------|------|
| `lancedb` | Embedded vector DB for wiki | `core/pyproject.toml` | `[wiki]` | pip, no server |
| `mlx-embeddings` | Local embeddings on Apple Silicon | `core/pyproject.toml` | `[wiki]` | ~80 MB model |
| `all-MiniLM-L6-v2` | Embedding model | Downloaded by mlx-embeddings | — | ~80 MB |

**Zero new server processes. Zero cloud services. All local-first.**

Fallback: `nomic-embed-text-v1.5` via Ollama (already on Leader) if `mlx-embeddings` unavailable.

---

## 6. What to Explicitly Defer to Phase 26

| Item | Reason |
|------|--------|
| Leader↔DEV knowledge sync | Needs DEV fully online with wiki storage |
| Pareto cost-quality optimization | Needs production data across multiple model tiers |
| Production feedback loop (10% sampling) | Needs Paperclip approval UI wired to eval |
| Office KnowledgePanel + EvalDashboard | Nice-to-have; command-line access sufficient initially |
| Full bidirectional sync | Original plan already rules this out |
| GraphRAG community detection | Too compute-intensive for 16GB Leader |
| Hierarchical wiki index | Not needed until >5K pages |

---

## 7. What to Skip Entirely

| Item | Reason |
|------|--------|
| OpenViking replacement | Already complete, tiered retrieval works |
| ModelRouter rewrite | `route_v2` already implements 7-tier + degradation |
| New evaluation module from scratch | Extend existing `evaluation.py` instead |
| Vector database server (Qdrant, Weaviate) | LanceDB embedded is sufficient |
| Full graph database (Neo4j) | SQLite entity graph sufficient at current scale |
| Mem0/Zep cloud services | Confidentiality requires local-only |
| Auto-generated CLAUDE.md | Human-curated is strictly better |

---

## 8. Success Metrics

| Metric | Current | Sprint 2 Target | Sprint 4 Target |
|--------|---------|-----------------|-----------------|
| CLAUDE.md context cost | ~15K tokens | ~2K tokens | ~2K tokens |
| Knowledge reuse across campaigns | 0% | >20% | >40% |
| Task completion rate | Unknown | Measured | >90% |
| Eval golden set size | 0 | 20 tasks | 50 tasks |
| KAIROS lint coverage | Hash dedup only | +embedding dedup | +staleness +orphans +conflicts |
| Harness change regression rate | Unknown | Measured | 0% (eval gate) |
| Skills available on-demand | 11 | 18 | 18 |
| MCP servers | 3 | 5 | 7 |

---

## 9. Risk Mitigations Specific to OAS

| Risk | OAS-Specific Context | Mitigation |
|------|---------------------|------------|
| CLAUDE.md restructuring breaks workflows | 28 cluster skills + dispatch.py depend on routing table knowledge | Run full 1,200-test suite before/after; gradual extraction (one section per PR) |
| mlx-embeddings on 16GB Leader | Leader only has 16GB; embedding model needs ~80MB | 80MB is fine; run embeddings on DEV if Leader memory-constrained |
| LanceDB on Leader vs DEV | Plan says DEV but Leader needs retrieval too | Install on both; Leader queries local index, DEV has full index |
| Golden set bootstrapping | No existing scored campaign outputs | Start with 10 manually-annotated tasks from recent research campaigns; grow to 50 |
| Skill explosion | 18 skills + 28 cluster skills = 46 total | Skills are on-demand only; no context cost unless invoked |

---

## 10. Implementation Order Summary

```
Week 1-2 (Sprint 1): CLAUDE.md lean-out + 7 skills + wiki scaffold + deps
    ↓
Week 3-4 (Sprint 2): Knowledge pipeline + eval runner + 2 MCP servers
    ↓
Week 5-6 (Sprint 3): Wiki compile/lint + eval CI gate + Gen-Eval loop + 4 commands
    ↓
Week 7-8 (Sprint 4): 3 agents + 4 hooks + 2 MCP servers + golden set expansion
```

Total new: **~5,800 LOC**, **~220 tests**, **7 skills**, **3 agents**, **4 MCP servers**, **4 commands**, **4 hooks**, **8 DRVP events**.

Post-implementation test count: **~1,420** (current 1,200 + 220 new).
