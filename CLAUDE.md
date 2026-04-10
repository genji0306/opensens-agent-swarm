# Opensens Agent Swarm (OAS) — Claude Code Project Guide

## What This Is

**Opensens Agent Swarm** is a four-layer agentic research swarm operating on the DarkLab Mac mini cluster. Under the v2 architecture (Phase 24+), authority, compute, and execution are split across explicit layers with hard non-overlap rules, multi-device human control, and cost-gated cloud escalation.

The v2 canonical plan is `docs/OAS-V2-MERGED-PLAN.md`. The legacy master plan `docs/OAS-DEVELOPMENT-PLAN.md` covers Phases 1–23 and remains the history of record for everything shipped before v2.

## Architecture (v2 — Phase 24+)

Four layers, strict authority boundaries:

```
Boss (human)        → sovereign intent · approval · override, exercised from any enrolled device
OAS Control Plane   → zero-LLM hosted service: plan store, approvals, timeline, override console
Leader (cyber02)    → strategic orchestration: plans, decomposes, routes, synthesizes, escalates
DEV (cyber01)       → execution + compute pool: local models, code, sim, borrowed inference, RL
```

- **Boss** never writes plans directly or executes work. Boss expresses intent via OAS from MacBook / iPad / iPhone.
- **OAS Control Plane** (hosted on DEV in the Phase 24 interim, dedicated host in Phase 25) has zero LLM calls, no personas, no agent identity. It is the cockpit: plan store, approval queue, live timeline, override console, cost ledger, audit exporter.
- **Leader** (16GB Mac mini at `leader.local`) runs the `OrchestratorAgent` with a Think-Act-Observe loop, backed by a local Gemma 4 E4B for routing decisions. Owns planning, decomposition, routing, synthesis, reflection, governance. The only node allowed to call paid APIs.
- **DEV** (24GB Mac mini at `dev.local`) hosts the Gemma worker pool (3× E4B), the Gemma 4 27B MoE reasoning model, Qwen2.5-Coder 7B, the simulation runner, and the MLX LoRA trainer. DEV runs under two OS identities: `dev-exec` for production work and `dev-forge` for sandboxed self-improvement (Phase 25).

### Two primitives between Leader and DEV

| | Task delegation | Inference borrowing |
|---|---|---|
| Logic owner | DEV | Leader |
| Compute owner | DEV | DEV |
| Transport | JSON-RPC 2.0 (WebSocket) | HTTP POST to `InferenceEndpoint` |
| Example | "Build a DFT simulation for AMIM/BMIM" | "Run this prompt on your 27B model" |
| Authority | Fully delegated | Leader retains full planning authority |

Borrowing lets Leader reason with 27B-class quality despite only having 16GB of its own RAM. DEV's `DevScheduler` serves two queues: local tasks (high priority, never preempted) and borrowed inference (time-sliced between bursts). DEV publishes a `priority_floor` on every heartbeat so Leader can back off during DEV load peaks.

### Model tier taxonomy (7 tiers)

| Tier | Location | Gate |
|---|---|---|
| `PLANNING_LOCAL` | Leader (Gemma 4 E4B) | Automatic |
| `REASONING_LOCAL` | DEV (Gemma 4 27B MoE Q4, borrowed) | Automatic |
| `WORKER_LOCAL` | DEV (3× Gemma 4 E4B pool, borrowed) | Automatic, time-sliced |
| `CODE_LOCAL` | DEV (Qwen2.5-Coder 7B) | DEV task delegation |
| `RL_EVOLVED` | DEV (Qwen3 + per-agent LoRA) | Automatic when LoRA available |
| `CLAUDE_SONNET` | Cloud (Anthropic) | **Per-mission budget cap** — automatic within cap |
| `CLAUDE_OPUS` | Cloud (Anthropic) | **Per-call Boss approval** — no timeout-grant, no bypass |

Default path never touches Anthropic. Sonnet handles the ~10% of cases where local quality is insufficient, subject to a per-mission budget. Opus is reserved for genuinely hard problems and always requires explicit Boss approval through the OAS approval queue for *every single call*. The `OpusGate` policy rule in `DecisionPolicyEngine` enforces this — disabling it requires Boss approval plus a 24-hour cooldown.

### Graceful degradation chain

```
REASONING_LOCAL (borrow DEV 27B)
  ↓ DEV priority_floor too high or unreachable
PLANNING_LOCAL (Leader E4B)
  ↓ output quality below threshold
CLAUDE_SONNET (if within per-mission budget)
  ↓ budget exhausted or confidential flag set
REQUEST CLAUDE_OPUS (emit decision.opus_requested, pause, wait for Boss)
  ↓ Boss rejects or times out
Mission pauses with "blocked: needs_boss"
```

Confidential missions (`mission.confidential=true`) block all cloud tiers at the router. They run entirely on Leader + DEV local compute; if quality is insufficient the mission fails with `degraded=true` rather than escalating.

### v2 command flow

Boss (device) → OAS Mission Launcher → Plan Store → Leader `PlanStoreWatcher` (HTTP poll, 5s) → `OrchestratorAgent` (TAO loop) → `CampaignEngine` → (task delegation to DEV OR borrowed inference to DEV OR Sonnet escalation OR Opus request) → `Reflector` → synthesized output → OAS → Boss.

## Legacy Architecture (Phases 1–23, still active)

The legacy command flow was: `Boss → Telegram → PicoClaw → Leader dispatch.py → OpenClaw node.invoke → Academic/Experiment agents`. It still works for slash-command missions and is not being removed. Phase 24 adds the plan-file entry point *alongside* the existing dispatch path; the two coexist during the transition. In Phase 24 the Academic/Experiment distinction collapses into DEV, with task routing handled internally by the `DevScheduler` based on task type.

```
Boss (MacBook)      → SSH/Telegram control, Paperclip dashboard, Opensens Office
Leader (Mac mini)   → OpenClaw gateway (:18789), Paperclip (:3100), Opensens Office (:5180)
Academic (Mac mini) → OpenClaw node-host, literature/research/browser agents
Experiment (Mac mini) → OpenClaw node-host, simulation/analysis/ML agents
```

## Directory Structure

```
Opensens Agent Swarm/
├── CLAUDE.md                     # This file
├── pyproject.toml                # uv workspace root (members: core, cluster)
├── package.json                  # pnpm workspace root (members: office, paperclip)
│
├── cluster/                      # DarkLab cluster agents & installer (281 tests)
│   ├── agents/
│   │   ├── shared/               # models, config, llm_client, node_bridge, audit, crypto
│   │   ├── leader/               # dispatch, synthesis, media_gen, notebooklm, serve
│   │   ├── academic/             # research, literature, doe, paper, perplexity, browser_agent
│   │   ├── experiment/            # simulation, analysis, synthetic, report_data, autoresearch
│   │   └── dev/                   # v2 DEV node: inference_endpoint, scheduler
│   ├── skills/                   # 14 OpenClaw SKILL.md skill definitions
│   ├── tests/                    # pytest suite
│   └── configs/, scripts/, docker/, roles/, common/
│
├── core/                         # OAS shared framework (876 tests, ~7,000 LOC)
│   └── oas_core/
│       ├── swarm.py              # LangGraph swarm builder
│       ├── handoff.py            # Governed handoff tool factory
│       ├── memory.py             # OpenViking HTTP client + session continuity
│       ├── persona.py            # Agency-agents persona loader
│       ├── campaign.py           # Campaign execution engine (DAG + parallel)
│       ├── evaluation.py         # Self-evaluation loop (rule + LLM)
│       ├── sandbox.py            # NemoClaw sandbox manager (stub)
│       ├── middleware/            # Pipeline: budget → audit → governance → memory
│       │   ├── __init__.py       # Pipeline compositor (PipelineConfig)
│       │   ├── budget.py         # Paperclip budget enforcement
│       │   ├── governance.py     # Issue tracking + approval gates
│       │   ├── audit.py          # Ed25519 audit trail
│       │   ├── memory.py         # OpenViking context loading/storing
│       │   └── summarization.py  # Context window management
│       ├── decision/              # Campaign intelligence (Phase 20)
│       │   ├── policy_engine.py  # DecisionPolicyEngine + composable rules
│       │   ├── readiness.py      # 4-dimension readiness scoring
│       │   ├── reflection.py     # Post-step campaign reflection
│       │   └── uncertainty_router.py  # Readiness-aware pre-routing
│       ├── scheduler/             # Multi-node orchestration (Phase 22)
│       │   ├── task_queue.py     # Redis-backed priority queue + DLQ
│       │   ├── heartbeat.py      # Node health + lease model
│       │   ├── scheduler.py      # Resource-aware dispatch
│       │   ├── discovery.py      # Dynamic capability discovery
│       │   └── isolation.py      # Failure isolation + circuit breaker
│       ├── inference/             # v2 compute borrowing (Phase 24)
│       │   ├── types.py          # BorrowRequest/BorrowResponse (frozen, extra=forbid)
│       │   └── client.py         # BorrowedInferenceClient (Leader→DEV HTTP)
│       ├── kairos/               # v2 ambient daemon (Phase 24)
│       │   ├── heartbeat.py      # 60s scan: budget, leases, stuck campaigns
│       │   ├── autodream.py      # Nightly KB consolidation (forked subprocess)
│       │   ├── proactive.py      # Gap detection + RL rollout curation
│       │   └── forked_worker.py  # Subprocess isolation (nice 19)
│       ├── webhooks/              # External event delivery (Phase 23)
│       │   ├── registry.py       # Webhook subscription CRUD
│       │   └── dispatcher.py     # HMAC-SHA256 + retry + DLQ
│       ├── campaign_journal.py   # Append-only JSONL with SHA-256 hash chain
│       ├── campaign_templates.py # YAML-defined reusable campaign patterns
│       ├── model_router.py       # 7-tier v2 taxonomy + degradation chain
│       ├── plan_file.py          # YAML+MD plan parser (v2 fields)
│       ├── plan_store_client.py  # HTTP client for OAS Plan Store API
│       ├── plan_watcher.py       # Filesystem plan watcher (legacy)
│       ├── lineage.py            # Artifact provenance graph (DAG queries)
│       ├── audit_export.py       # ZIP audit bundle with integrity manifest
│       ├── protocols/
│       │   ├── drvp.py           # 79+ event types, Redis Pub/Sub transport
│       │   └── events.py         # Unified event schema (OpenClaw + Paperclip + DRVP)
│       ├── adapters/
│       │   ├── paperclip.py      # Paperclip REST client (costs, issues, goals, approvals)
│       │   └── openclaw.py       # OpenClaw WS client (JSON-RPC 2.0)
│       └── subagents/
│           └── claude_code.py    # Claude Code CLI sub-agent
│
├── office/                       # Opensens Office — React 19 + Vite 6 + TS (24 tests)
│   └── src/
│       ├── gateway/              # OpenClaw WebSocket adapter + types (OfficeStore interface)
│       ├── store/                # 17 Zustand stores (office, drvp, paperclip, console)
│       ├── drvp/                 # SSE client + consumer + types (matches drvp.py schema)
│       ├── paperclip/            # REST client + types (matches paperclip.py)
│       ├── hooks/                # useDrvpConnection, usePaperclipPolling
│       ├── components/           # office-2d, office-3d, panels, console, chat, layout
│       └── pages/                # Dashboard, Agents, Channels, Skills, Cron, Requests, Settings
│
├── paperclip/                    # Paperclip AI — governance platform
│   ├── server/                   # Express 5 REST API + WebSocket + DRVP bridge + issue linker
│   ├── ui/                       # React 19 dashboard (Kanban, org chart, costs)
│   ├── packages/                 # db (Drizzle, 37 tables), shared (Zod + types), adapters
│   └── cli/                      # Paperclip CLI
│
├── frameworks/                   # Reference frameworks (read-only, git-ignored)
│   ├── langgraph-swarm/          # LangGraph multi-agent handoff
│   ├── openviking/               # Context database for AI agents
│   ├── agency-agents/            # 70+ curated agent persona definitions
│   ├── deepagents/               # Batteries-included agent harness
│   ├── nemoclaw/                 # NVIDIA sandbox wrapper
│   ├── openclaw/                 # OpenClaw core (reference)
│   ├── OpenClaw-RL-main/         # Async RL framework for agent self-evolution
│   ├── MiroShark-main/           # Multi-agent debate/simulation engine (Neo4j + CAMEL-AI)
│   ├── claude-code-skill/        # Claude Code MCP skill
│   ├── browser-use/              # Browser automation
│   ├── AIClient-2-API-main/      # Client-account-to-API proxy (Gemini/Kiro/Codex/Grok)
│   ├── autoresearch-mlx/         # MLX-based autoresearch training
│   ├── onecli-main/              # OneCLI security audit tooling
│   ├── drawbridge/               # UI annotation bridge
│   ├── deer-flow-main/           # DeerFlow 2.0 super agent harness (ByteDance)
│   │   └── skills/custom/darklab-research/  # DarkLab custom research skill
│   └── everything-claude-code/   # ECC: 156 skills, 38 agents, hooks, rules (MIT)
│
├── .claude/                      # Claude Code harness configuration
│   ├── commands/bridge.md        # Drawbridge UI annotation command
│   ├── settings.json             # Hooks, env, ECC profile config
│   ├── skills/                   # 35 ECC + DarkLab skills
│   │   ├── python-patterns/      # Pythonic idioms, PEP 8, type hints
│   │   ├── agentic-engineering/  # Eval-first, decomposition, model routing
│   │   ├── deep-research/        # Multi-source research with citations
│   │   ├── security-review/      # OWASP Top 10, secrets, input validation
│   │   ├── darklab-swarm-ops/    # DarkLab dispatch, DRVP, budget patterns
│   │   ├── darklab-code-review/  # DarkLab-specific code review checklist
│   │   └── ... (33 more)
│   ├── agents/                   # 11 ECC specialist agents
│   │   ├── code-reviewer.md      # Post-change quality review
│   │   ├── security-reviewer.md  # Vulnerability detection
│   │   ├── architect.md          # System design decisions
│   │   ├── planner.md            # Implementation planning
│   │   └── ... (7 more)
│   └── rules/                    # 20 rule files (common + python + typescript)
│       ├── common/               # 10 cross-language rules
│       ├── python/               # Python-specific patterns
│       └── typescript/           # TypeScript-specific patterns
│
└── docs/
    ├── OAS-DEVELOPMENT-PLAN.md                    # Full roadmap
    ├── AICLIENT-INTEGRATION-PLAN.md               # AIClient boost tier strategy
    ├── DEERFLOW-INTEGRATION-PLAN.md               # DeerFlow + Autoresearch integration plan
    ├── OPENCLAW-RL-MIROSHARK-INTEGRATION-PLAN.md  # RL self-evolution + debate simulation strategy
    ├── MEMENTO-CODEX-INTEGRATION-PLAN.md          # Memento + Codex orchestrator plan
    ├── PARAMETER-GOLF-SOLUTION.md                 # Parameter golf optimization docs
    └── SECURITY-AND-INTEGRATION-PLAN.md           # OneCLI security audit + PicoClaw↔Paperclip integration
```

## Running Tests

```bash
cd "Opensens Agent Swarm"
.venv/bin/pytest cluster/tests/ -q   # 291 tests
.venv/bin/pytest core/tests/ -q      # 881 tests (9 skipped without langgraph)
cd office && npx vitest run           # 28 tests
```

**Total: 1,200 passing** (881 core + 291 cluster + 28 office). Run cluster and core separately — conftest collision. Use `.venv/bin/pytest` directly — system `VIRTUAL_ENV` can conflict with uv workspace.

## Key Modules

### cluster/agents/shared/
- **`models.py`** — `Task`, `TaskResult`, `TaskType` (16 enum values: 5 academic + 6 experiment + 4 leader + STATUS), `AgentInfo`
- **`config.py`** — Pydantic `Settings` (25 fields): API keys, networking, Paperclip, OpenViking, Redis, LiteLLM, signing keys, logging
- **`llm_client.py`** — Async wrappers for Anthropic, OpenAI, Gemini, Perplexity with atomic budget enforcement (`_check_and_record_spend` under `fcntl.LOCK_EX`)
- **`node_bridge.py`** — stdin/argv JSON → Task → handler → TaskResult → stdout JSON
- **`audit.py`** — Append-only JSONL audit logger
- **`crypto.py`** — Ed25519 payload signing/verification (PyNaCl)

### core/oas_core/ (28 modules, all implemented)

**Orchestration:**
- **`swarm.py`** (284 LOC) — LangGraph swarm builder: `build_swarm()`, `wrap_agent_as_node()`. Import guard: `SWARM_AVAILABLE`.
- **`handoff.py`** (77 LOC) — Governed handoff tool factory with Paperclip metadata
- **`campaign.py`** (349 LOC) — `CampaignEngine`: DAG dependency resolution, parallel step execution (`max_parallel`), step timeout, DRVP events, Paperclip issue per step
- **`evaluation.py`** (349 LOC) — `RuleBasedEvaluator` (4 criteria: completeness/structure/sources/error-free) + `Evaluator` with optional LLM fallback. Campaign-level scoring.

**Memory & Personas:**
- **`memory.py`** (264 LOC) — `MemoryClient`: async OpenViking HTTP client. Tiered L0/L1/L2 reading, write-back, semantic search, directory ops, relations. Session continuity: `load_session_context()`, `archive_session()`, `find_related_sessions()`.
- **`persona.py`** (170 LOC) — `load_persona()`: YAML frontmatter parser. `ROLE_PERSONA_MAP` maps 16 DarkLab agents → real agency-agents persona files.

**Middleware Pipeline** (`middleware/`):
- **`__init__.py`** (179 LOC) — `Pipeline` compositor: Budget → Audit → Governance → Memory → handler → post-store → DRVP events
- **`budget.py`** (155 LOC) — Pre-check via Paperclip, post-report costs, file-lock fallback
- **`governance.py`** (262 LOC) — Auto-create issues, status tracking, campaign approval gates
- **`audit.py`** (200 LOC) — SHA-256 hashing + optional Ed25519 signing, JSONL append
- **`memory.py`** (119 LOC) — Pre-load (semantic search), post-store (write findings), DRVP events
- **`summarization.py`** (92 LOC) — Token-count heuristic compression

**Protocols:**
- **`protocols/drvp.py`** (159 LOC) — 25 event types (incl. browser.navigate/action/blocked), Redis Pub/Sub transport, best-effort `emit()`
- **`protocols/events.py`** (287 LOC) — `UnifiedEvent` with converters: `from_drvp()`, `from_openclaw()`, `from_paperclip()`

**Adapters:**
- **`adapters/paperclip.py`** (338 LOC) — Async REST client: costs, issues, approvals, goals (hierarchy), budgets, activity log, dashboard
- **`adapters/openclaw.py`** (343 LOC) — Async WS client (JSON-RPC 2.0): handshake, 15+ RPC methods, event streaming
- **`adapters/deerflow.py`** (210 LOC) — DeerFlow embedded client wrapper: `DeerFlowAdapter` with DRVP events, streaming via `asyncio.to_thread`, file uploads, model selection
- **`adapters/labclaw.py`** (120 LOC) — LabClaw lab-loop adapter: `run_lab_loop()`, import guard `LABCLAW_AVAILABLE`, stub when uninstalled
- **`adapters/internagent.py`** (115 LOC) — InternAgent deep research graph adapter: `run_deep_research()`, import guard `INTERNAGENT_AVAILABLE`
- **`adapters/uniscientist.py`** (130 LOC) — UniScientist polymathic synthesis: `synthesize()` with multi-finding merge, import guard `UNISCIENTIST_AVAILABLE`

**v2 Compute Borrowing** (`inference/`):
- **`inference/types.py`** (125 LOC) — `BorrowRequest` / `BorrowResponse` / `BorrowOutcome` — frozen Pydantic schemas, distinct from task delegation (§6.1)
- **`inference/client.py`** (180 LOC) — `BorrowedInferenceClient` — httpx async client for DEV InferenceEndpoint; rejections are `BorrowResponse`, only transport faults raise

**v2 KAIROS** (`kairos/`):
- **`kairos/heartbeat.py`** (125 LOC) — 60s scan: budget ratio vs idle cap, expired leases, stuck campaigns, DEV health
- **`kairos/autodream.py`** (175 LOC) — Nightly KB consolidation: deduplicate, prune stale, merge similar, atomic write-back
- **`kairos/proactive.py`** (160 LOC) — Gap detection: research_gap, low_confidence, rl_curation suggestions
- **`kairos/forked_worker.py`** (120 LOC) — Subprocess isolation with `os.nice(19)`, JSON I/O via temp files

**v2 Research Router:**
- **`deep_research/router.py`** (260 LOC) — `ResearchRouter` — parallel/sequential/hybrid mode orchestration across research backends + synthesis

**v2 Plan Store:**
- **`plan_store_client.py`** (160 LOC) — `PlanStoreClient` — HTTP poller for OAS Plan Store API: cursor-based `fetch_new()`, `mark_accepted()`, `parse_plan()`

**Sub-agents:**
- **`subagents/claude_code.py`** (250 LOC) — Spawns Claude Code CLI as subprocess. Strips CLAUDECODE env, model/tool overrides, JSON output parsing.

**Integration:**
- **`deep_agent.py`** (175 LOC) — Deepagents subprocess wrapper: `DeepAgentRunner` with isolated workspaces, timeout, file seeding
- **`sandbox.py`** (185 LOC) — NemoClaw sandbox manager: `create()`, `destroy()`, `run_code()` with Linux/macOS fallback

### cluster/agents/dev/ (v2 Phase 24)
- **`scheduler.py`** (330 LOC) — `DevScheduler` — two-queue cooperative scheduler: Q1 local tasks (never preempted), Q2 borrowed inference (time-sliced), priority-floor backpressure
- **`inference_endpoint.py`** (135 LOC) — FastAPI app: `/v1/borrow` (200+outcome), `/v1/capability`, `/v1/health`, optional bearer auth

### cluster/agents/leader/
- **`dispatch.py`** — Dual-mode dispatch with 5 lazy-init middleware singletons (sentinel pattern). Slash commands → ROUTING_TABLE; free-form → swarm → campaign. Memory pre-loading, audit logging, CampaignEngine execution.
- **`serve.py`** — FastAPI (:8100): `/health`, `/drvp/events/{company_id}` (SSE), `/dispatch`, `/synthesize`, `/media`, `/task`
- **`swarm_registry.py`** — Maps 12-15 DarkLab agents (notebooklm, deerflow optional) to handlers for the LangGraph swarm router
- **`orchestrator.py`** — `OrchestratorAgent` with Think-Act-Observe loop. Parses plan files, builds campaign steps, delegates to CampaignEngine, emits DRVP events. Wires `ModelRouter.route_v2()` via `routing_context_factory`. Dispatch entry: `handle()`.
- **`kairos.py`** — `KairosDaemon` — ambient intelligence daemon. 60s heartbeat, nightly autoDream (forked), proactive suggestions, RL rollout curation. Local-only by policy, subject to IdleBudgetRule. Dispatch entry: `handle()`.
- **`plan_watcher_service.py`** — `PlanWatcherService` — dual-mode (filesystem + HTTP Plan Store). Polls for new plans, executes via OrchestratorAgent, writes idempotent receipts.

### paperclip/ (Express 5 + React 19 + Drizzle ORM)

**Server** (`server/src/`):
- **`routes/`** (17 modules) — Full REST API: agents, issues, approvals, goals, projects, costs, secrets, access, dashboard, sidebar-badges, health, llms, assets, activity
- **`services/`** (28 modules) — Business logic layer:
  - **`heartbeat.ts`** (2,150 LOC) — Agent scheduling, execution, task assignment
  - **`issues.ts`** (1,320 LOC) — Task CRUD, status transitions, checkout, execution locking
  - **`drvp-bridge.ts`** (75 LOC) — Redis `drvp:{companyId}` subscriber → LiveEvent publisher
  - **`drvp-issue-linker.ts`** (330 LOC) — Auto-creates issues from `request.created`, records cost events from `llm.call.completed`, records zero-cost boost events from `llm.call.boosted`, creates approvals from `campaign.approval.required`, updates issue status on `request.completed`/`request.failed`
  - **`live-events.ts`** (41 LOC) — In-memory EventEmitter for WebSocket broadcast
  - **`costs.ts`** — Cost event creation with auto agent/company spend tracking and budget pausing
  - **`approvals.ts`** — Hiring + strategy approval workflow (approve/reject/revision/resubmit)
  - **`workspace-runtime.ts`** (940 LOC) — Agent session state persistence
- **`realtime/live-events-ws.ts`** (274 LOC) — WebSocket server (`/api/companies/{id}/events/ws`)
- **`middleware/`** — auth (board/agent), board-mutation-guard, error-handler, logger (pino), validate (Zod)
- **`auth/better-auth.ts`** — OAuth + JWT authentication

**UI** (`ui/src/`):
- **27 pages** — Dashboard, Agents, Issues (Kanban), Approvals, Activity, Costs, OrgChart, Goals, Projects, Settings, Auth, DesignGuide
- **50+ components** — KanbanBoard (dnd-kit), AgentProperties, MarkdownEditor, CommentThread, CommandPalette, OnboardingWizard
- **7 agent runtime adapters** — claude-local, codex-local, cursor, gemini-local, openclaw-gateway, opencode-local, pi-local

**Packages** (`packages/`):
- **`db/`** — Drizzle ORM with 37 PostgreSQL tables (agents, issues, heartbeat_runs, cost_events, approvals, activity_log, goals, projects, etc.)
- **`shared/`** — Zod validators + TypeScript types (18 type modules, constants with all enums)
- **`adapters/`** — 7 agent runtime adapter packages
- **`adapter-utils/`** — Shared adapter utilities

### office/src/ (React 19 + Vite 6 + Zustand 5)

**Gateway** (`gateway/`):
- **`ws-client.ts`** — Native WebSocket with auto-reconnect (exponential backoff, max 20 attempts)
- **`rpc-client.ts`** — JSON-RPC 2.0 wrapper with request/response correlation
- **`ws-adapter.ts`** — `WsAdapter`: ~30 RPC methods (chat, sessions, channels, skills, cron, agents, files, config)
- **`event-parser.ts`** — OpenClaw `agent` events → visual/chat state mapping
- **`types.ts`** — `OfficeStore` interface, `VisualAgent`, `AgentVisualStatus`, `CollaborationLink`

**DRVP** (`drvp/`):
- **`drvp-client.ts`** — `DrvpSseClient` (native EventSource to Leader SSE endpoint)
- **`drvp-consumer.ts`** (165 LOC) — Bridges DRVP events to stores: visual status mapping, handoff animations (from/to agent status), budget event → Paperclip refresh, campaign step progress tracking, approval event handling
- **`drvp-types.ts`** — 22 event types matching `core/oas_core/protocols/drvp.py`

**Stores** (`store/`):
- **`office-store.ts`** (52 KB) — Agent CRUD, positions, zones, movement, collaboration links, sessions, metrics, theme
- **`drvp-store.ts`** — Circular buffer (500 events), active request tracking with campaign progress (`CampaignProgress`), agent→issue mapping
- **`paperclip-store.ts`** — Dashboard, agents, issues, costs via REST polling
- **11 console stores** — agents, channels, skills, cron, config, dashboard, settings, chat-dock, clawhub

**Components** (`components/`):
- **`office-2d/`** — SVG isometric floor plan: `FloorPlan`, `AgentAvatar`, `DeskUnit`, furniture (desk/chair/sofa/plant)
- **`office-3d/`** — R3F 3D scene: `Scene3D`, `AgentCharacter`, `SkillHologram`, `SpawnPortal`, `ThinkingIndicator`
- **`panels/`** (11) — `PaperclipPanel` (campaign alerts + approval counts), `EventTimeline` (rich DRVP payload details for 15 event types), `AgentDetailPanel`, `MetricsPanel`, `TokenLineChart`, `CostPieChart`, `ActivityHeatmap`, `BudgetGauge`, `ActiveIssuesList` (priority badges + assignee), `NetworkGraph`, `SubAgentPanel`
- **`chat/`** — `ChatDockBar`, `ChatDialog`, `AgentSelector`, `StreamingIndicator`, `SessionSwitcher`
- **`console/`** — Dashboard, Agents, Channels, Skills, Cron, Settings, Requests (campaign progress bars + 5 stat cards) page components

## Routing Table

| Command | Device | Skill | TaskType |
|---------|--------|-------|----------|
| research | academic | darklab-research | RESEARCH |
| literature | academic | darklab-literature | LITERATURE |
| doe | academic | darklab-doe | DOE |
| paper | academic | darklab-paper | PAPER |
| perplexity | academic | darklab-perplexity | PERPLEXITY |
| simulate | experiment | darklab-simulation | SIMULATE |
| analyze | experiment | darklab-analysis | ANALYZE |
| synthetic | experiment | darklab-synthetic | SYNTHETIC |
| report-data | experiment | darklab-report-data | REPORT_DATA |
| autoresearch | experiment | darklab-autoresearch | AUTORESEARCH |
| deerflow | leader | darklab-deerflow | DEERFLOW |
| synthesize | leader | darklab-synthesis | SYNTHESIZE |
| report | leader | darklab-media-gen | MEDIA_GEN |
| notebooklm | leader | darklab-notebooklm | NOTEBOOKLM |
| deepresearch | leader | darklab-deepresearch | DEEP_RESEARCH |
| swarmresearch | leader | darklab-deepresearch | SWARM_RESEARCH |
| parametergolf | experiment | darklab-parameter-golf | PARAMETER_GOLF |
| debate | leader | darklab-debate | DEBATE |
| rl-train | leader | darklab-rl-train | RL_TRAIN |
| rl-status | leader | darklab-rl-train | RL_TRAIN |
| rl-rollback | leader | darklab-rl-train | RL_TRAIN |
| rl-freeze | leader | darklab-rl-train | RL_TRAIN |
| turboswarm | leader | darklab-turboswarm | TURBO_SWARM |
| fullswarm | leader | darklab-fullswarm | FULL_SWARM |
| paperreview | leader | darklab-paper-review | PAPER_REVIEW |
| dft | leader | darklab-dft | DFT |
| ane-research | leader | darklab-ane-research | ANE_RESEARCH |
| gemma-swarm | leader | darklab-gemma-swarm | GEMMA_SWARM |
| unipat | leader | darklab-unipat-swarm | UNIPAT_SWARM |
| orchestrate | leader | darklab-orchestrator | ORCHESTRATE |
| kairos | leader | darklab-kairos | KAIROS |

## Dispatch Flow

```
Incoming text → audit.log_task_start → memory.pre_load (inject prior_context)
    │
parse_command(text)
    │
┌───┴────┐
/cmd     free-form
 │          │
ROUTING    get_swarm_app()
TABLE       │
 │       ┌──┴──┐
 │    swarm   None
 │      │       │
 │   _dispatch  plan_campaign() → governance.open_issue
 │   _via_swarm    │
 │      │       approval gate
 │      │          │
 │      │     ┌────┴─────┐
 │      │  approved    pending
 │      │     │           │
 │      │  CampaignEngine return plan
 │      │  (parallel DAG)
 └──────┴─────┘
         │
     TaskResult
```

## DRVP (Dynamic Request Visualization Protocol)

79+ event types emitted by the middleware pipeline. Events flow via Redis Pub/Sub (`drvp:{company_id}`) and persist to the Paperclip activity log.

```
Middleware emit → Redis drvp:{company_id}
                        │
                ┌───────┴───────┐
                ▼               ▼
        Leader SSE          Paperclip bridge
   /drvp/events/{id}      drvp-bridge.ts → publishLiveEvent
        │                       │
        ▼                       ├──→ WS clients (Paperclip UI)
   DrvpSseClient               └──→ drvp-issue-linker.ts
        │                            │
   dispatchDrvpEvent()               ├─ request.created    → auto-create issue
        │                            ├─ llm.call.completed → record cost_event
   ┌────┴────┐                       ├─ campaign.approval  → create approval
   ▼         ▼                       ├─ request.completed  → issue → done
drvp-store  office-store             └─ request.failed     → issue → blocked
   │         │
   │         ├─ visual status (thinking/speaking/error/idle)
   │         ├─ handoff animation (from→to agent status)
   │         └─ budget.exhausted → agent error state
   │
   ├─ campaign progress (step/total/title/quality)
   ▼
EventTimeline, RequestsPage, PaperclipPanel, TaskBadge
```

## Budget System

Daily per-role limits enforced via file-locked JSON (`~/.darklab/logs/spend-YYYY-MM-DD.json`):
- Leader: $50, Academic: $30, Experiment: $20
- `BudgetMiddleware` in core pre-checks via Paperclip, post-reports costs, falls back to file lock
- Paperclip dashboard shows monthly budgets at http://192.168.23.25:3100

## Leader Docker Stack (192.168.23.25)

| Service | Port | Image/Build |
|---------|------|-------------|
| OpenClaw Gateway | 18789 | Native process (loopback) |
| Paperclip AI | 3100 | `./paperclip` (PostgreSQL backend) |
| Opensens Office | 5180 | `./office` (Node.js) |
| DarkLab Leader | 8100 | `./cluster` (FastAPI) |
| LiteLLM | 4000 | `ghcr.io/berriai/litellm` |
| PicoClaw | — | `./picoclaw` (Telegram agent) |
| Redis | 6379 | `redis:7-alpine` |
| Caddy | 80 | `caddy:2-alpine` |
| Cloudflared | — | `cloudflare/cloudflared` (tunnel) |
| PostgreSQL | 5432 | `postgres:17-alpine` |
| Dozzle | 8081 | `amir20/dozzle` (log viewer) |

Docker CLI: `/Applications/Docker.app/Contents/Resources/bin/docker`

## Paperclip Governance

Company "Opensens DarkLab" (prefix: DL) with 4 agents:
- **Boss** (CEO, human) — $0 budget
- **DarkLab Leader** (CTO) — $1,500/month
- **DarkLab Academic** (Research Director) — $900/month
- **DarkLab Experiment** (Lab Director) — $600/month

CEO user: steve@opensens.io. Dashboard: http://192.168.23.25:3100

## Conventions

- Python 3.11+, Pydantic v2, async/await throughout
- Model IDs: `claude-opus-4-6-20260301`, `claude-sonnet-4-6-20260301`
- Config via env vars loaded by `shared.config.Settings` (dotenv from `~/.darklab/.env`)
- Paths use `settings.darklab_home` (not `Path.home()`) for testability
- `core/` uses stdlib `logging` (`oas.*` hierarchy); `cluster/` uses `structlog` — don't mix
- `frameworks/` is read-only reference — import and wrap in `core/`
- Optional deps guarded: langgraph (`SWARM_AVAILABLE`), websockets (`_WS_AVAILABLE`), PyNaCl (`_NACL_AVAILABLE`), deerflow (`DEERFLOW_AVAILABLE`)
- All modules export via `__all__`; no circular imports

## Office Environment

```bash
# Required in office/.env.local
VITE_GATEWAY_URL=ws://localhost:18789
VITE_GATEWAY_TOKEN=...
VITE_LEADER_URL=http://192.168.23.25:8100      # DRVP SSE
VITE_PAPERCLIP_URL=http://192.168.23.25:3100    # Governance REST
VITE_DRVP_COMPANY_ID=...                        # Paperclip company UUID
```

## SSH Access (Leader Mac mini)

```bash
ssh "cyber 02@192.168.23.25"  # password: Opensens26
```

## Development Status

| Phase | Focus | Status | Tests |
|-------|-------|--------|-------|
| 1. Merge & Foundation | Folder restructure, CLAUDE.md, logging | **Complete** | 56 → 68 |
| 2. Swarm & Governance | LangGraph, DRVP, budget, governance, dispatch | **Complete** | 68 → 131 |
| 3. Visualization | Agent Office ↔ Paperclip, request flow DAG | **Complete** | 131 → 168 |
| 4. Memory & Personas | OpenViking, agency-agents, audit, summarization | **Complete** | 168 → 222 |
| 5. Advanced Orchestration | Campaign engine, evaluation, Claude Code, pipeline | **Complete** | 222 → 287 |
| 6. DRVP Bridge & Office | Cost events, approvals, issue lifecycle, visual handlers | **Complete** | 287 → 297 |
| 7. Office UX & AIClient | RequestCard campaign progress, EventTimeline rich details, priority badges, AIClient boost tier | **Complete** | 297 → 361 |
| 8. Security & Integration | Browser domain allowlist, per-task profiles, DRVP browser events, PicoClaw-Paperclip dispatch hooks, budget pre-check | **Complete** | 361 → 384 |
| 9. Finish All Tasks | OpenViking deploy, knowledge graph, deepagents, NemoClaw sandbox, E2E tests, /boost command | **Complete** | 384 → 405 |
| 10. DeerFlow Integration | DeerFlow adapter, /deerflow command, boost tier, custom skill, 27 new tests | **Complete** | 405 → 474 |
| 11. RL Self-Evolution | OpenClaw-RL + MiroShark integration, 48 new tests | **Complete** | 474 → 522 |
| 12. Deep Research | Iterative research pipeline, academic search, convergence eval, 12 new tests | **Complete** | 522 → 534 |
| 13. Research Expansion | 9 academic sources, knowledge base, parameter golf route, 7 new tests | **Complete** | 534 → 541 |
| 14. Swarm + Wiring | /swarmresearch, Tinker training wired, MiroShark simulation wired | **Complete** | 541 |
| 15. TurboQuant | KV cache compression (PolarQuant + QJL + Middle-Out), memory pool, runtime adapter, 30 new tests | **Complete** | 541 → 571 |
| 16. Qwen3 Multi-Model | Specialist routing (Qwen3:8b general, qwen2.5-coder coding, glm4:9b reasoning), RL_EVOLVED+TurboQuant 12k context, 10 new tests | **Complete** | 571 → 581 |
| 17. Office + Registry | Swarm registry entries for new agents, Office panels (RLStatusPanel, TurboQuantPanel), DRVP consumer handlers | **Complete** | 581 |
| 18. Research Mgmt | /results, /schedule, LLM synthesizer (Qwen3 via Ollama), Dashboard panel wiring | **Complete** | 581 |

| 19. Live Deployment | DeerFlow on Mac mini, deep research daemon, liaison-broker dispatch, autoresearch, Drawbridge, MOQ library | **Complete** | 581 |
| 20. Campaign Intelligence | Decision policy engine, readiness scoring, reflection layer, uncertainty router, DRVP events, DecisionPanel | **Complete** | 581 → 625 |
| 21. Governance Maturity | Campaign journal (hash chain), template library (4 YAML), lineage graph, audit export (ZIP), signed approvals | **Complete** | 625 → 760 |
| 22. Multi-Node Foundation | Redis task queue, node heartbeat, resource-aware scheduler, capability discovery, failure isolation, ClusterStatusPanel | **Complete** | 760 → 804 |
| 23. Platformization | Webhook event layer (HMAC-SHA256), Python SDK (sync+async), ClusterStatusPanel, partner console differentiation | **Complete** | 804 → 832 |
| 24. v2 Swarm Redesign | Boss/Leader/DEV four-layer split, plan-file protocol, compute borrowing, 7-tier ModelRouter, OpusGate, KAIROS, DEV online | **In Progress** | 832 → 1200 |
| 25. Self-evolution + Multi-device | 6-gate promotion pipeline, frozen benchmarks, shadow runs, auto-rollback, Passkey/WebAuthn, iPad/iPhone UI, OAS dedicated host | **Planned** | TBD |
| 26. Scaling primitives | Generalized NodeDescriptor, capability tags, affinity hints, provisioning script | **Planned** | TBD |

**Phase 24 tasks (v2 Swarm Redesign — in progress):**

| # | Task | Status |
|---|------|--------|
| 111 | `PlanFile` parser + v2 fields (sonnet_cap_usd, opus_allowed, confidential) | **Complete** |
| 113 | `PlanStoreWatcher` — HTTP poller (dual-mode: filesystem + HTTP Plan Store) | **Complete** |
| 116 | `InferenceEndpoint` on DEV (FastAPI: /v1/borrow, /v1/capability, /v1/health) | **Complete** |
| 117 | `DevScheduler` — two-queue cooperative scheduler (Q1 local tasks, Q2 borrows) | **Complete** |
| 118 | `CapabilityManifest` publisher on DEV heartbeat | **Complete** |
| 119 | `BorrowedInferenceClient` on Leader (httpx async, degradation-aware) | **Complete** |
| 120 | `ModelRouter` rewrite — 7-tier taxonomy + §6.4 degradation chain (`route_v2`) | **Complete** |
| 121 | `OpusGate` policy rule — per-call Boss approval, no bypass | **Complete** |
| 122 | `SonnetBudget` policy rule — per-mission hard cap | **Complete** |
| 123 | `OrchestratorAgent` — TAO loop, DRVP events, `route_v2` wiring | **Complete** |
| 124 | `LabClawAdapter` + import guard + DRVP events | **Complete** |
| 125 | `InternAgentAdapter` + import guard + DRVP events | **Complete** |
| 126 | `UniScientistAdapter` + import guard + synthesis wiring | **Complete** |
| 127 | `ResearchRouter` — parallel/sequential/hybrid modes | **Complete** |
| 128 | `KairosDaemon` — heartbeat, autoDream (forked), proactive suggestions, RL curation | **Complete** |
| 132 | Office: `OpusApprovalModal` (first-class multi-device approval UI) | **Complete** |
| 133 | Office: `ComputePoolPanel`, `OrchestratorPanel`, `KairosPanel` | **Complete** |
| 134 | DRVP events: +24 new types → 79 total; TypeScript consumer handlers | **Complete** |
| 112 | OAS Plan Store API (CRUD, versioning, auth) — server side | **Pending** (ops) |
| 114 | Relocate Paperclip + Postgres from Leader to DEV | **Pending** (ops) |
| 115 | DEV base provisioning: Ollama + MLX + models | **Pending** (ops) |
| 129 | Relocate OAS from MacBook → DEV (interim host) | **Pending** (ops) |
| 130 | `dev-exec` / `dev-forge` OS identities + sandbox worktree | **Pending** (ops) |
| 131 | PicoClaw refactor: Telegram → OAS client adapter | **Pending** (ops) |
| 137 | Feature-flag rollout | **Pending** (ops) |

**110 of 110 legacy tasks implemented.** Phase 24 adds ~80 new tests. See task table above for v2 progress.

> Detailed per-task tables for Phases 11–23: see `docs/COMPLETED-PHASE-TASKS.md`

## Subsystem Quick Reference

Read the source for details — these summaries exist only for navigation.

- **Campaign Intelligence** (`core/oas_core/decision/`): `DecisionPolicyEngine` (4 rules), `ReadinessScorer` (4 dimensions), `CampaignReflector`, `UncertaintyRouter`. DRVP events: `decision.*`, `readiness.*`, `uncertainty.*`.
- **Governance** (`core/oas_core/campaign_journal.py`, `campaign_templates.py`, `lineage.py`, `audit_export.py`): Hash-chain journal, 4 YAML templates, DAG lineage, ZIP audit export, Ed25519 signed approvals.
- **Scheduler** (`core/oas_core/scheduler/`): Redis task queue (5 priority levels), heartbeat, resource-aware dispatch, discovery, circuit breaker. Feature-flag: `DARKLAB_SCHEDULER_ENABLED`.
- **Webhooks** (`core/oas_core/webhooks/`): HMAC-SHA256 signatures, retry with backoff, DLQ. Subscribes to any of 29 DRVP event types.
- **Python SDK** (`sdk/opensens_oas/`): `OASClient` + `AsyncOASClient` — campaigns, dispatch, webhooks, health. Bearer token auth.

## v2 Compute Borrowing (Phase 24)

The compute borrowing primitive (§6 of OAS-V2-MERGED-PLAN) is the most important new capability in v2. Two distinct primitives on the same Leader→DEV wire:

- **Task delegation** (JSON-RPC) — DEV gets full workflow authority
- **Inference borrowing** (HTTP) — Leader retains full authority, DEV does one forward pass

Wire schemas (`core/oas_core/inference/types.py`): `BorrowRequest` (frozen, extra=forbid) and `BorrowResponse` with 7 `BorrowOutcome` states. Leader-side client: `BorrowedInferenceClient`. DEV-side: `DevScheduler` (two-queue cooperative, Q1 never preempted) + `InferenceEndpoint` (FastAPI).

**Degradation chain** (ModelRouter.route_v2): `REASONING_LOCAL` → `PLANNING_LOCAL` → `CLAUDE_SONNET` (if budget) → `CLAUDE_OPUS` (if Boss approves) → blocked. Confidential missions (`mission.confidential=true`) block all cloud tiers at the router.

**Policy rules**: `OpusGateRule` (per-call Boss approval, no bypass), `SonnetBudgetRule` (per-mission hard cap), `IdleBudgetRule` (KAIROS gating at 20% daily spend).

## v2 Research Router (Phase 24)

`core/oas_core/deep_research/router.py` — orchestrates multiple research backends per plan-file mode:

- **Sequential**: `internagent → labclaw → uniscientist` (each receives prior output as context)
- **Parallel**: `deerflow ∥ labclaw ∥ internagent`, then `uniscientist` merges
- **Hybrid**: `{deerflow ∥ internagent}` → `labclaw` → `uniscientist`

Protocol-based backends: any async callable matching `ResearchBackend` / `SynthesisBackend` protocols. All LLM calls inside adapters borrow DEV compute — Leader never runs a 27B forward pass.

## v2 KAIROS Daemon (Phase 24)

KAIROS (Ancient Greek: "the right moment") runs at OS-level idle priority on Leader:

1. **Heartbeat** (60s): budget ratio check, expired leases, stuck campaigns, DEV health
2. **autoDream** (nightly 03:00): KB consolidation in forked subprocess — deduplicate, prune stale, merge similar, atomic write-back
3. **Proactive suggestions**: gap detection (low source count), low confidence, RL rollout curation
4. **Hard rules**: never calls Sonnet/Opus, subject to IdleBudgetRule (20% cap), all actions emit `kairos.*` DRVP events

Core: `core/oas_core/kairos/` (heartbeat, autodream, proactive, forked_worker). Leader daemon: `cluster/agents/leader/kairos.py`.

## Everything Claude Code (ECC) Integration

ECC (`frameworks/everything-claude-code/`) is integrated as a Claude Code harness optimizer. 11 skills (code-referenced only) and 11 agents are installed in `.claude/`.

### How It Works

1. **Claude Code sessions** — Skills in `.claude/skills/` are available on demand via `/skill-name`
2. **Sub-agent enrichment** — `ClaudeCodeAgent` in `core/oas_core/subagents/claude_code.py` injects skill context via `TASK_SKILL_MAP` (14 task types → 2 skills max each)
3. **Invoke-only policy** — Skills are NOT loaded into context automatically. They are loaded only when CLAUDE.md or a plan explicitly calls for them, or via `/skill-name`.

### Installed Skills (11 — code-referenced only)

| Category | Skills |
|----------|--------|
| Python | python-patterns, pytorch-patterns |
| Agentic | agentic-engineering, autonomous-agent-harness |
| Research | deep-research, search-first |
| Security | security-review |
| Quality | benchmark, verification-loop |
| DarkLab | darklab-swarm-ops, darklab-code-review |

### Installed Agents (11)

`code-reviewer`, `python-reviewer`, `typescript-reviewer`, `security-reviewer`, `architect`, `planner`, `performance-optimizer`, `tdd-guide`, `e2e-runner`, `doc-updater`, `harness-optimizer`

### Hooks

Configured in `.claude/settings.json`:
- **PreToolUse:** `block-no-verify` (prevents `--no-verify` on git), `config-protection` (blocks linter config edits)
- **PostToolUse:** `command-log-audit` (bash audit log), `console-warn` (detects console.log)
- **Stop:** `cost-tracker` (session cost metrics)

Hook profile: `ECC_HOOK_PROFILE=standard` (set in settings.json env)

### MCP Servers

`.mcp.json` includes: `code-review-graph`, `sequential-thinking`, `github`

### Helpers

```python
from oas_core.subagents.claude_code import (
    load_ecc_skill,     # Load skill content by name
    load_ecc_agent,     # Load agent definition by name
    list_ecc_skills,    # List all installed skills
    list_ecc_agents,    # List all installed agents
    TASK_SKILL_MAP,     # DarkLab task type → ECC skill mapping
)
```

## Integration Quick Reference

- **DeerFlow** (`core/oas_core/adapters/deerflow.py`): `/deerflow <objective>`. Guard: `DEERFLOW_AVAILABLE`. Config: `~/.darklab/deerflow/config.yaml`. Install: `uv pip install -e ./frameworks/deer-flow-main/backend/packages/harness`. Plan: `docs/DEERFLOW-INTEGRATION-PLAN.md`.
- **OpenClaw-RL** (`core/oas_core/rl/`, `adapters/openclaw_rl.py`): `/rl-train`, `/rl-status`, `/rl-rollback`, `/rl-freeze`. Per-agent LoRA, 4-gate promotion, A/B comparison. Guard: `OPENCLAW_RL_AVAILABLE`. Config: `DARKLAB_RL_ENABLED`. Plan: `docs/OPENCLAW-RL-MIROSHARK-INTEGRATION-PLAN.md`.
- **MiroShark** (`core/oas_core/adapters/miroshark.py`): `/debate <topic>` (6 scenarios). Guard: `MIROSHARK_AVAILABLE`. Docker: `miroshark` + `neo4j-miroshark` profile.
- **Deep Research** (`core/oas_core/deep_research/`): `/deepresearch <topic>`. 7 academic databases, 5-metric convergence, JSONL knowledge base. Plan: `docs/MEMENTO-CODEX-INTEGRATION-PLAN.md`.
- **TurboQuant** (`core/oas_core/turbo_quant/`): PolarQuant + QJL + Middle-Out. `/turboq-status`. Config: `DARKLAB_TURBOQUANT_ENABLED`, `_BITS`, `_POOL_MB`. ~12k tokens/agent at 4-bit with 4GB pool. Plan: `docs/TURBOQUANT-INTEGRATION-PLAN.md`.

## Browser Security

The browser agent enforces a domain allowlist before any navigation:

```bash
# ~/.darklab/.env (comma-separated)
DARKLAB_BROWSER_ALLOWED_DOMAINS=perplexity.ai,scholar.google.com,arxiv.org,pubmed.ncbi.nlm.nih.gov,semanticscholar.org,google.com,biorxiv.org,medrxiv.org
DARKLAB_BROWSER_MAX_STEPS=20
DARKLAB_BROWSER_HEADLESS=true
```

- Subdomain matching: `scholar.google.com` matches `google.com` in the allowlist
- Per-task browser profiles: each invocation gets an isolated Chromium profile
- DRVP events: `browser.navigate`, `browser.action`, `browser.blocked`
- `DomainBlockedError` raised for unauthorized URLs (including PDF downloads)

## PicoClaw-Paperclip Integration

The `pre_dispatch_hook()` in dispatch.py runs before any routing decision:

1. **Budget pre-check** — queries Paperclip for remaining budget; blocks if exhausted
2. **DRVP `request.created`** — emits event with request title and source
3. **Auto issue creation** — for `picoclaw`/`telegram`/`boss` sources, creates a Paperclip issue so every external request is tracked

This ensures PicoClaw requests flow through the full governance pipeline even before routing.
