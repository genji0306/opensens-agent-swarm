<h1 align="center">Opensens Agent Swarm</h1>

<p align="center">
  <strong>A unified agentic research platform for the DarkLab distributed AI cluster</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776ab?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/node-20+-339933?logo=node.js&logoColor=white" alt="Node 20+" />
  <img src="https://img.shields.io/badge/react-19-61dafb?logo=react&logoColor=white" alt="React 19" />
  <img src="https://img.shields.io/badge/tests-1385_passing-brightgreen" alt="1385 Tests" />
  <img src="https://img.shields.io/badge/phase-25-8a2be2" alt="Phase 25" />
  <img src="https://img.shields.io/badge/license-proprietary-lightgrey" alt="License" />
</p>

---

## What is this?

**Opensens Agent Swarm (OAS)** is a four-layer agentic research swarm running on the DarkLab Mac mini cluster. Under the v2 architecture (Phase 24+), authority, compute, and execution are split across explicit layers with hard non-overlap rules, multi-device human control, and cost-gated cloud escalation.

- **Boss** &mdash; the human operator role, exercised from any enrolled device (MacBook / iPad / iPhone). Sovereign intent and approval authority.
- **OAS Control Plane** &mdash; hosted zero-LLM service: plan store, approval queue, live timeline, override console, cost ledger, audit exporter.
- **Leader** (cyber02, 16GB) &mdash; strategic orchestration: `OrchestratorAgent` with a Think-Act-Observe loop, `CampaignEngine`, `DecisionPolicyEngine`, KAIROS daemon, research adapters (DeerFlow, LabClaw, InternAgent, UniScientist). The only node that talks to paid APIs.
- **DEV** (cyber01, 24GB) &mdash; execution + compute pool: Gemma worker pool (3× E4B), Gemma 4 27B MoE reasoning model, Qwen2.5-Coder 7B, simulation runner, MLX LoRA trainer. Runs under two OS identities (`dev-exec` for production, `dev-forge` for sandboxed self-improvement).

The v2 roadmap is `docs/OAS-V2-MERGED-PLAN.md`. Phases 1–23 (shipped) provide the foundation: dispatch routing, 20 research skills, governance middleware, DRVP event bus, campaign engine, RL self-evolution, TurboQuant KV compression, multi-node scheduler, webhook SDK. Phase 24 adds the v2 swarm redesign (plan-file orchestrator, compute borrowing, 7-tier router, KAIROS daemon). **Phase 25 (current)** adds the LLM Wiki knowledge subsystem, eval-driven development harness, Generator-Evaluator loop, and harness layering that drops per-turn context cost from ~15K to ~2K tokens.

### Phase 25 — LLM Wiki + Harness Engineering

Phase 25 adds three things that compound agent quality across missions:

- **LLM Wiki (`core/oas_core/knowledge/`)** — Karpathy-pattern compounding knowledge store. `KnowledgeIngester` turns every campaign step output into structured entities and claims (SQLite-backed `EntityStore`), compiles wiki pages, and feeds an embedded LanceDB vector index. A `RetrievalRouter` scopes reads by layer: Leader sees the full wiki, DEV only the entity store, Boss only L0 abstracts from OpenViking. Wire-compatible with KAIROS autoDream for nightly consolidation.
- **Eval harness (`core/oas_core/eval/`)** — eval-driven development with a 5-dimension rubric (completeness 25%, accuracy 25%, source quality 20%, synthesis 20%, cost efficiency 10%) and 30 golden YAML fixtures covering the DarkLab research domain (EIT sensors, ionic liquids, DFT, materials science). `EvalRunner` produces markdown reports and emits regression events when scores drop more than 0.3 from baseline. The `CampaignEngine._run_step` loop scores output against the rubric and retries up to three times before accepting a weak result.
- **Harness layering** — `CLAUDE.md` restructured from 716 lines (~15K tokens/turn) to ~110 lines of always-loaded L0 context. The deep material moved into seven on-demand DarkLab skills (`darklab-drvp-events`, `darklab-model-routing`, `darklab-kairos-ops`, `darklab-plan-authoring`, `darklab-memory-ops`, `darklab-knowledge-wiki`, `darklab-eval-harness`) that Claude Code loads only when relevant. Three new specialist agents (`knowledge-curator`, `gap-researcher`, `eval-analyst`) plug into the harness.

Phase 25 also ships four new slash commands (`/wiki-compile`, `/wiki-lint`, `/eval-run`, `/eval-report`), two MCP servers (`model-router`, `openviking-memory`) that expose OAS internals as tools for external agents, and an mlx-embeddings helper that the KAIROS autoDream daemon uses for semantic deduplication (cosine similarity ≥ 0.85) with a hash-fallback path when the Apple Silicon embedding stack is unavailable.

### Two primitives between Leader and DEV

- **Task delegation** &mdash; DEV owns the logic and the compute ("build a DFT simulation"). JSON-RPC over WebSocket.
- **Inference borrowing** &mdash; Leader owns the logic, DEV owns the compute ("run this prompt on your 27B model"). HTTP POST to DEV's `InferenceEndpoint`. Leader retains full planning authority; DEV acts as a model server for that one forward pass.

Borrowing lets Leader reason with 27B-class quality despite only having 16GB of its own RAM, without blurring the authority model.

### 7-tier model routing

| Tier | Location | Gate |
|---|---|---|
| `PLANNING_LOCAL` | Leader (Gemma 4 E4B) | Automatic |
| `REASONING_LOCAL` | DEV (Gemma 4 27B MoE Q4, borrowed) | Automatic |
| `WORKER_LOCAL` | DEV (3× Gemma 4 E4B pool, borrowed) | Automatic, time-sliced |
| `CODE_LOCAL` | DEV (Qwen2.5-Coder 7B) | DEV task delegation |
| `RL_EVOLVED` | DEV (Qwen3 + per-agent LoRA) | Automatic when LoRA available |
| `CLAUDE_SONNET` | Cloud | Per-mission budget cap |
| `CLAUDE_OPUS` | Cloud | **Per-call Boss approval &mdash; no timeout-grant, no bypass** |

Default path never touches Anthropic. Sonnet handles the ~10% of cases where local quality is insufficient. Opus is reserved for genuinely hard problems and always requires an explicit Boss approval through the OAS approval queue for every single call.

Every request &mdash; from a Telegram command to a plan-file-driven research campaign &mdash; flows through a governed pipeline with real-time visual feedback and signed audit trails.

---

## Screenshots

<table>
  <tr>
    <td align="center"><strong>2D Office Floor Plan</strong></td>
    <td align="center"><strong>3D Office View</strong></td>
  </tr>
  <tr>
    <td><img src="office/assets/office-2d.png" alt="2D Office" width="480" /></td>
    <td><img src="office/assets/office-3d.png" alt="3D Office" width="480" /></td>
  </tr>
  <tr>
    <td align="center"><strong>Console Dashboard</strong></td>
    <td align="center"><strong>Agent Management</strong></td>
  </tr>
  <tr>
    <td><img src="office/assets/console-dashboard.png" alt="Dashboard" width="480" /></td>
    <td><img src="office/assets/console-agent.png" alt="Agents" width="480" /></td>
  </tr>
</table>

---

## Architecture (v2)

```
+------------------------------------------------------------------+
|  BOSS (human)   MacBook / iPad / iPhone                          |
|  clients of OAS; zero local swarm state                          |
+-----------------------------+------------------------------------+
                              |  HTTPS (Cloudflare Tunnel + Passkey)
                              v
+------------------------------------------------------------------+
|  OAS CONTROL PLANE  (hosted on DEV, interim)                     |
|  Mission Launcher  Plan Store  Approval Queue  Live Timeline     |
|  Override Console  Cost Ledger  Audit Exporter  PicoClaw adapter |
|  ZERO LLM CALLS                                                  |
+--------------+---------------------------------------------------+
               |  plan pull (HTTP)  approval verdicts  overrides
               v
+------------------------------------------------------------------+
|  LEADER   cyber02   16GB   leader.local                          |
|  PlanStoreWatcher  OrchestratorAgent (TAO loop, Gemma E4B)       |
|  CampaignEngine    DecisionPolicyEngine  UncertaintyRouter       |
|  KAIROS daemon     Reflector  Knowledge Base  Lineage Graph      |
|  Research adapters: DeerFlow, LabClaw, InternAgent, UniScientist |
|  ModelRouter (7 tiers)  Redis DRVP bus  FastAPI :8100            |
+-----+------------------------------------------------------------+
      |  task delegation (JSON-RPC)          ^  artifacts, metrics
      |  inference borrowing (HTTP)          |  evidence, proposals
      v                                      |
+------------------------------------------------------------------+
|  DEV   cyber01   24GB   dev.local                                |
|  identities:  dev-exec (production)  dev-forge (sandbox)         |
|  Gemma pool (3x E4B)   Gemma 4 27B MoE Q4 (borrowed)             |
|  Qwen2.5-Coder 7B      Simulation runner  Experiment harness     |
|  MLX LoRA trainer      DevScheduler (two-queue cooperative)      |
|  Paperclip + Postgres  OAS control plane (interim host)          |
+------------------------------------------------------------------+
```

### Legacy (Phases 1–23, still active alongside v2)

```
Boss (MacBook) --> Telegram/PicoClaw --> Leader dispatch.py
                                             |
                                             v
                              +---------------------------+
                              | Academic  |  Experiment   |
                              | (research)| (simulation)  |
                              +---------------------------+
```

In Phase 24 the Academic/Experiment distinction collapses into DEV. Task routing happens internally on DEV via `DevScheduler` based on task type.

---

## Dispatch Flow

```
Incoming text ──> audit.log ──> memory.pre_load (inject prior_context)
                                        |
                                  parse_command(text)
                                        |
                           ┌────────────┴────────────┐
                        /command                   free-form
                           |                          |
                     ROUTING TABLE              get_swarm_app()
                           |                          |
                           |                   ┌──────┴──────┐
                           |                 swarm         campaign
                           |                   |              |
                           |            _dispatch_via     plan_campaign()
                           |              _swarm             |
                           |                   |        governance gate
                           |                   |              |
                           |                   |      ┌───────┴───────┐
                           |                   |   approved        pending
                           |                   |      |               |
                           |                   |  CampaignEngine   return
                           |                   |  (parallel DAG)    plan
                           └───────────────────┴──────┘
                                        |
                                   TaskResult
                                        |
                           ┌────────────┴────────────┐
                     audit.log                   DRVP emit
                                            (25 event types)
                                                 |
                                    ┌────────────┴────────────┐
                               Redis Pub/Sub           Paperclip Bridge
                                    |                         |
                              Leader SSE              drvp-issue-linker
                                    |                    (auto-create
                             DrvpSseClient              issues, costs,
                                    |                    approvals)
                           ┌────────┴────────┐
                      drvp-store        office-store
                      (timeline)     (visual status)
```

---

## DRVP (Dynamic Request Visualization Protocol)

25 event types flow through the middleware pipeline, enabling real-time visualization:

| Category | Events | Visual Effect |
|----------|--------|---------------|
| **Request** | `request.created`, `request.completed`, `request.failed` | Issue lifecycle in Paperclip |
| **Agent** | `agent.thinking`, `agent.responding`, `agent.error`, `agent.idle` | Avatar status animation |
| **Handoff** | `handoff.initiated`, `handoff.completed` | Agent-to-agent connection line |
| **LLM** | `llm.call.started`, `llm.call.completed`, `llm.call.boosted` | Token/cost metrics update |
| **Campaign** | `campaign.started`, `campaign.step.*`, `campaign.completed` | Progress bar + step tracking |
| **Budget** | `budget.warning`, `budget.exhausted` | Red alert + agent error state |
| **Governance** | `campaign.approval.required`, `campaign.approval.granted` | Approval panel notification |
| **Memory** | `memory.loaded`, `memory.stored` | Context indicator |
| **Browser** | `browser.navigate`, `browser.action`, `browser.blocked` | Domain security events |

---

## Project Structure

```
Opensens Agent Swarm/
│
├── core/                          # Shared framework (24+ modules, ~5,000 LOC)
│   └── oas_core/
│       ├── swarm.py               # LangGraph swarm builder
│       ├── turbo_swarm/           # Performance orchestration layer (lazy loading, budgets, truncation)
│       ├── team_runtime/          # Team state/event/worktree runtime primitives
│       ├── handoff.py             # Governed handoff tool factory
│       ├── memory.py              # OpenViking HTTP client + session continuity
│       ├── persona.py             # Agency-agents persona loader (16 agents)
│       ├── campaign.py            # Campaign engine (DAG + parallel execution)
│       ├── campaign_journal.py    # Append-only campaign journal + integrity chain
│       ├── evaluation.py          # Self-evaluation (rule + LLM scoring)
│       ├── model_router.py        # Tiered model selection (PLANNING/EXECUTION/BOOST)
│       ├── deep_agent.py          # Deepagents subprocess wrapper
│       ├── sandbox.py             # NemoClaw sandbox manager
│       ├── schemas/team.py        # Team manifest/worker/task/event schemas
│       ├── middleware/            # Pipeline: budget → audit → governance → memory
│       ├── protocols/             # DRVP events + unified event schema
│       ├── adapters/              # Paperclip, OpenClaw, DeerFlow, ProRL clients
│       └── subagents/             # Claude Code CLI sub-agent
│
├── cluster/                       # DarkLab cluster agents & installer
│   └── agents/
│       ├── shared/                # Models, config, LLM client, audit, crypto
│       ├── leader/                # Dispatch, synthesis, media gen, serve
│       ├── academic/              # Research, literature, DOE, paper, browser
│       └── experiment/            # Simulation, analysis, synthetic, report
│
├── office/                        # Opensens Office (React 19 + Vite 6)
│   └── src/
│       ├── gateway/               # OpenClaw WebSocket adapter
│       ├── store/                 # 17 Zustand stores
│       ├── drvp/                  # SSE client + consumer
│       ├── paperclip/             # REST client + types
│       ├── components/            # 2D/3D office, panels, console, chat
│       └── pages/                 # Dashboard, Agents, Channels, Skills, ...
│
├── paperclip/                     # Paperclip AI governance platform
│   ├── server/                    # Express 5 REST API + WebSocket + DRVP bridge
│   ├── ui/                        # React 19 dashboard (Kanban, org chart, costs)
│   └── packages/                  # db (Drizzle, 37 tables), shared (Zod), adapters
│
├── frameworks/                    # External references (git-ignored, clone separately)
│   ├── OpenClaw-RL-main/         # Async RL for agent self-evolution
│   ├── MiroShark-main/           # Multi-agent debate/simulation engine
│   ├── langgraph-swarm/          # LangGraph multi-agent handoff
│   ├── openviking/               # Context database for AI agents
│   ├── deer-flow-main/           # DeerFlow 2.0 research harness
│   └── ...                       # 12 more reference frameworks
│
└── docs/                          # Architecture docs & roadmaps
```

> **Note:** The `frameworks/` directory is excluded from version control. It contains 16 read-only reference repos including OpenClaw-RL (RL self-evolution), MiroShark (debate simulation), LangGraph Swarm, OpenViking, DeerFlow, and others. Clone them separately as needed.

---

## Research Skills (20)

| # | Skill | Node | Description |
|---|-------|------|-------------|
| 1 | `research` | Academic | Deep literature research with multi-source synthesis |
| 2 | `literature` | Academic | Systematic literature review and citation analysis |
| 3 | `doe` | Academic | Design of Experiments planning |
| 4 | `paper` | Academic | Scientific paper drafting and formatting |
| 5 | `perplexity` | Academic | Real-time web research via Perplexity AI |
| 6 | `browser` | Academic | Secure browser automation (domain-allowlisted) |
| 7 | `simulate` | Experiment | Numerical simulation and modeling |
| 8 | `analyze` | Experiment | Statistical analysis and data processing |
| 9 | `synthetic` | Experiment | Synthetic data generation |
| 10 | `report-data` | Experiment | Data report generation with visualizations |
| 11 | `autoresearch` | Experiment | Autonomous multi-step research campaigns |
| 12 | `deerflow` | Leader | Deep multi-step research via DeerFlow harness |
| 13 | `synthesize` | Leader | Cross-agent result synthesis |
| 14 | `report` | Leader | Media generation (PDF, presentations) |
| 15 | `notebooklm` | Leader | NotebookLM-style knowledge management |
| 16 | `debate` | Leader | Multi-agent debate simulation via MiroShark |
| 17 | `deepresearch` | Leader | Iterative deep research with convergence scoring |
| 18 | `swarmresearch` | Leader | Multi-angle parallel research (5 perspectives) |
| 19 | `parametergolf` | Experiment | Compressed LM training under 16MB |
| 20 | `turboswarm` | Leader | Maximum-performance 5-angle parallel research |

---

## Middleware Pipeline

Every request passes through the full middleware stack:

```
Request ──> BudgetMiddleware ──> AuditMiddleware ──> GovernanceMiddleware ──> MemoryMiddleware
                |                     |                      |                      |
           Pre-check $          SHA-256 hash           Auto-create            Semantic search
           via Paperclip        + Ed25519 sign          issue in              for prior context
                                                       Paperclip
                                                                                   |
                                                                                   v
                                                                              Agent Handler
                                                                                   |
                                                                                   v
            Post-report $       Append JSONL           Update issue           Store findings
            cost event          audit trail             status                in OpenViking
```

---

## Budget System

Daily per-role limits enforced via file-locked JSON with Paperclip oversight:

| Role | Daily Limit | Monthly Budget |
|------|-------------|----------------|
| Leader (CTO) | $50 | $1,500 |
| Academic (Research Dir.) | $30 | $900 |
| Experiment (Lab Dir.) | $20 | $600 |

Budget exhaustion triggers `budget.exhausted` DRVP events, pausing the agent until the next day.

---

## Getting Started

### Prerequisites

- Python 3.11+ with [uv](https://github.com/astral-sh/uv)
- Node.js 20+ with [pnpm](https://pnpm.io/)
- PostgreSQL 17 (for Paperclip)
- Redis 7 (for DRVP Pub/Sub)

### Install

```bash
# Python workspace
uv sync

# Node workspace
pnpm install
```

### Environment

```bash
# cluster agents — ~/.darklab/.env
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
PERPLEXITY_API_KEY=...

# office — office/.env.local
VITE_GATEWAY_URL=ws://localhost:18789
VITE_GATEWAY_TOKEN=...
VITE_LEADER_URL=http://192.168.23.25:8100
VITE_PAPERCLIP_URL=http://192.168.23.25:3100
VITE_DRVP_COMPANY_ID=...
```

### Run Tests

```bash
# Python (run separately — conftest collision)
.venv/bin/pytest core/tests/ -q       # 403 tests (7 skipped without langgraph)
.venv/bin/pytest cluster/tests/ -q    # 150 tests

# Frontend
cd office && npx vitest run           # 28 tests
# Total: 581 passing
```

---

## Docker Stack (Leader Node)

The Leader Mac mini runs the full service mesh:

| Service | Port | Purpose |
|---------|------|---------|
| OpenClaw Gateway | 18789 | Agent communication hub |
| Paperclip AI | 3100 | Governance dashboard |
| Opensens Office | 5180 | Agent visualization |
| DarkLab Leader | 8100 | FastAPI dispatch + SSE |
| LiteLLM | 4000 | Model router proxy |
| Redis | 6379 | DRVP Pub/Sub transport |
| PostgreSQL | 5432 | Paperclip database |
| Caddy | 80 | Reverse proxy |
| Cloudflared | &mdash; | Secure tunnel |
| Dozzle | 8081 | Log viewer |

---

## Tech Stack

<table>
  <tr>
    <th>Layer</th>
    <th>Technology</th>
  </tr>
  <tr>
    <td><strong>Orchestration</strong></td>
    <td>LangGraph, custom campaign DAG engine, DeerFlow research harness</td>
  </tr>
  <tr>
    <td><strong>Backend</strong></td>
    <td>Python 3.11, FastAPI, Pydantic v2, async/await</td>
  </tr>
  <tr>
    <td><strong>Governance</strong></td>
    <td>Express 5, Drizzle ORM, PostgreSQL 17, Better Auth</td>
  </tr>
  <tr>
    <td><strong>Frontend</strong></td>
    <td>React 19, Vite 6, Zustand 5, Tailwind CSS 4</td>
  </tr>
  <tr>
    <td><strong>3D Rendering</strong></td>
    <td>React Three Fiber, @react-three/drei</td>
  </tr>
  <tr>
    <td><strong>Real-time</strong></td>
    <td>WebSocket (JSON-RPC 2.0), SSE, Redis Pub/Sub</td>
  </tr>
  <tr>
    <td><strong>Memory</strong></td>
    <td>OpenViking (tiered L0/L1/L2 context)</td>
  </tr>
  <tr>
    <td><strong>Security</strong></td>
    <td>Ed25519 signing, domain allowlist, per-task browser profiles</td>
  </tr>
  <tr>
    <td><strong>AI Models</strong></td>
    <td>Claude (Opus/Sonnet), GPT-4o, Gemini, Perplexity, LLaMA (local)</td>
  </tr>
  <tr>
    <td><strong>Testing</strong></td>
    <td>pytest (core + cluster suites), Vitest (office)</td>
  </tr>
</table>

---

## Development Status

Phases 1–25 are shipped (1,385 tests passing, 110/110 tasks for Phases 1–23, v2 redesign for Phase 24, LLM Wiki + harness engineering for Phase 25). See `docs/OAS-V2-MERGED-PLAN.md` for the canonical plan.

| Phase | Focus | Status |
|-------|-------|--------|
| 1. Merge & Foundation | Folder restructure, CLAUDE.md, logging | Done |
| 2. Swarm & Governance | LangGraph, DRVP, budget, governance, dispatch | Done |
| 3. Visualization | Agent Office ↔ Paperclip, request flow DAG | Done |
| 4. Memory & Personas | OpenViking, agency-agents, audit, summarization | Done |
| 5. Advanced Orchestration | Campaign engine, evaluation, Claude Code, pipeline | Done |
| 6. DRVP Bridge & Office | Cost events, approvals, issue lifecycle, visual handlers | Done |
| 7. Office UX & AIClient | Campaign progress, EventTimeline, priority badges, boost tier | Done |
| 8. Security & Integration | Browser allowlist, per-task profiles, DRVP browser events | Done |
| 9. Finish All Tasks | Knowledge graph, deepagents, NemoClaw, E2E tests, /boost | Done |
| 10. DeerFlow Integration | DeerFlow adapter, /deerflow command, boost tier, 27 new tests | Done |
| 11. RL Self-Evolution | OpenClaw-RL + MiroShark debate simulation, 48 new tests | Done |
| 12. Deep Research | Iterative research pipeline, academic search, convergence eval | Done |
| 13. Research Expansion | 9 academic sources, knowledge base, parameter golf route | Done |
| 14. Swarm + Wiring | /swarmresearch, Tinker training wired, MiroShark wired | Done |
| 15. TurboQuant | KV cache compression, memory pool, Middle-Out, runtime adapter | Done |
| 16. Qwen3 Multi-Model | Specialist routing, RL_EVOLVED+TurboQuant 12k context | Done |
| 17. Office + Registry | Swarm registry, RLStatusPanel, TurboQuantPanel, DRVP handlers | Done |
| 18. Research Mgmt | /results, /schedule, LLM synthesizer, Dashboard wiring | Done |
| 19. Team Runtime Foundation | Team schemas, file state store, lifecycle events, worktree guard, journal bridge | Done |
| 20. ProRL Sidecar Integration (Phase 1-2) | ProRL adapter, config surface, `/prorl-status`, `/prorl-run`, DRVP + governance linkage | Done |
| 21. Governance Maturity | Campaign journal (hash chain), template library, lineage graph, audit export, signed approvals | Done |
| 22. Multi-Node Foundation | Redis task queue, heartbeat, resource-aware scheduler, capability discovery, failure isolation | Done |
| 23. Platformization | Webhook event layer (HMAC-SHA256), Python SDK (sync+async), partner console | Done |
| 24. v2 Swarm Redesign | Boss/Leader/DEV four-layer split, plan-file protocol, compute borrowing, 7-tier ModelRouter, OpusGate, KAIROS, DEV online | Done |
| 25. LLM Wiki + Harness Engineering | Knowledge subsystem, eval harness, Generator-Evaluator loop, CLAUDE.md layering, 7 DarkLab skills, 3 specialist agents, 2 MCP servers, mlx-embeddings autoDream | **Done** |
| 26. Self-evolution + Multi-device | 6-gate promotion pipeline, frozen benchmarks, shadow runs, auto-rollback, Passkey/WebAuthn, iPad/iPhone UI | Planned |
| 27. Scaling primitives | Generalized NodeDescriptor, capability tags, affinity hints, provisioning script | Planned |

### Phase 19 Highlights (2026-04-01)

- Added OAS-native team schemas: manifest, worker, task, event contracts.
- Added `team_runtime` package with deterministic state paths, event JSONL persistence, backend registry, and worktree isolation manager.
- Wired leader dispatch lifecycle into team runtime (`task.created/started/completed/failed`) with best-effort DRVP + persistent event logging.
- Added governance worktree guard for mutating tasks (`requires_worktree` / `mutating` payload flags).
- Added bridge sync from `events.jsonl` into `CampaignJournal` with checkpointing for replay-ready dashboards.
- Extended `/status` to include live team runtime summary (team count, task count, event count).

### Phase 20 Highlights (2026-04-02)

- Added `core/oas_core/adapters/prorl.py` with async status, registration, startup, and `/process` normalization into a stable OAS envelope.
- Added ProRL runtime config in `cluster/agents/shared/config.py` and `cluster/configs/env.template` (`DARKLAB_PRORL_*` variables).
- Added leader commands `/prorl-status` and `/prorl-run` with Telegram-safe aliases (`/prorl_status`, `/prorl_run`).
- Wired DRVP tool events and best-effort Paperclip issue linkage for `/prorl-run` experimental executions.
- Added adapter and command tests covering health, normalization, route wiring, and guarded `/rl-train --backend prorl` behavior.

### Phase 25 Highlights (2026-04-10)

- **Knowledge subsystem** — `core/oas_core/knowledge/` with `KnowledgeIngester`, `EntityStore` (SQLite, 3 tables), `EmbeddingIndex` (LanceDB wrapper with import guard), `RetrievalRouter` (role-scoped: Leader / DEV / Boss), and frozen Pydantic types.
- **Eval subsystem** — `core/oas_core/eval/` with `EvalScorer` (5-dimension weighted rubric), `EvalRunner` (YAML golden set loader, markdown report generator), and `EvalReport` with per-task-type breakdown.
- **30 golden fixtures** — `core/tests/eval_golden/` covering EIT sensors, ionic liquids, DFT simulations, wearable electronics, and materials science.
- **Eval CI gate** — `core/tests/test_eval_ci_gate.py` enforces golden fixture schema, scoring ranges, and minimum fixture count to block regressions at merge time.
- **Generator-Evaluator loop** — `CampaignEngine._run_step` scores output against the rubric and retries up to three times (configurable via `_EVAL_MAX_RETRIES`) before accepting a weak step result.
- **Four new slash commands** — `/wiki-compile`, `/wiki-lint`, `/eval-run`, `/eval-report` with handlers in `cluster/agents/leader/wiki_eval_cmd.py`.
- **Harness layering** — CLAUDE.md restructured 716 → ~110 lines. Deep detail moved into seven on-demand DarkLab skills in `.claude/skills/`. Three new specialist agents: `knowledge-curator`, `gap-researcher`, `eval-analyst`.
- **KAIROS autoDream semantic merge** — `_merge_similar()` upgraded from prefix matching to cosine similarity via an optional `embedding_fn`. Pure Python `_cosine_similarity()` is forked-worker safe. `oas_core.knowledge.embeddings.get_embedding_fn()` returns an mlx-embeddings-backed function on Apple Silicon and falls back to a deterministic hash embedding when unavailable.
- **Two MCP servers** — `core/oas_core/mcp/model_router.py` exposes the 7-tier router and policy rules; `core/oas_core/mcp/openviking_memory.py` exposes tiered memory read/write, semantic search, and session context. Both run as stdio MCP servers for external tool use.
- **Eight new DRVP event types** — `KNOWLEDGE_INGESTED`, `KNOWLEDGE_CONFLICT_DETECTED`, `KNOWLEDGE_CONFLICT_AUTO_RESOLVED`, `KNOWLEDGE_PAGE_COMPILED`, `WIKI_LINT_COMPLETED`, `WIKI_SYNC_COMPLETED`, `EVAL_RUN_COMPLETED`, `EVAL_REGRESSION_DETECTED`.
- **Office panels** — `WikiPanel.tsx` (entities/claims/pages grid, conflict resolution state, lint indicator) and `EvalPanel.tsx` (weighted score gauge, delta from previous run, per-dimension bars, regression badge). Both wired into `DashboardPage.tsx` alongside the existing KAIROS panel.
- **Four PostToolUse hooks** — `.claude/settings.json` journals wiki and eval events to `~/.darklab/logs/wiki-eval-events.jsonl` for KAIROS to pick up.
- **Tests** — 1,061 core + 324 cluster + 28 office = **1,413 passing**. Core grew from 881 to 1,061 (+180 new tests) covering knowledge, eval, embeddings, MCP servers, and CI gates.

---

## License

Proprietary &mdash; Opensens B.V. All rights reserved.
