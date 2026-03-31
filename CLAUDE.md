# Opensens Agent Swarm (OAS) — Claude Code Project Guide

## What This Is

**Opensens Agent Swarm** is the unified agentic research platform for the DarkLab distributed AI research cluster. It merges the DarkLab agent infrastructure (dispatch routing, budget enforcement, 16 research skills, multi-AI cross-validation) with a suite of agentic frameworks (LangGraph Swarm, OpenViking memory, agency-agents personas, deepagents harness, OpenClaw-RL self-evolution, MiroShark debate simulation) under Paperclip governance and Agent Office visualization.

The system runs autonomous scientific research on a Mac mini cluster, where every request flows through a governed pipeline with real-time visual feedback. Agents self-evolve via OpenClaw-RL reinforcement learning on their own conversation history, with MiroShark providing synthetic debate scenarios for accelerated training.

See `docs/OAS-DEVELOPMENT-PLAN.md` for the comprehensive roadmap and `docs/OPENCLAW-RL-MIROSHARK-INTEGRATION-PLAN.md` for the RL self-evolution strategy.

## Architecture

```
Boss (MacBook)      → SSH/Telegram control, Paperclip dashboard, Opensens Office
Leader (Mac mini)   → OpenClaw gateway (:18789), Paperclip (:3100), Opensens Office (:5180)
Academic (Mac mini) → OpenClaw node-host, literature/research/browser agents
Experiment (Mac mini) → OpenClaw node-host, simulation/analysis/ML agents
```

Commands flow: **Boss → Telegram → PicoClaw → Leader dispatch.py → OpenClaw node.invoke → Academic/Experiment agents**

## Directory Structure

```
Opensens Agent Swarm/
├── CLAUDE.md                     # This file
├── pyproject.toml                # uv workspace root (members: core, cluster)
├── package.json                  # pnpm workspace root (members: office, paperclip)
│
├── cluster/                      # DarkLab cluster agents & installer (96 tests)
│   ├── agents/
│   │   ├── shared/               # models, config, llm_client, node_bridge, audit, crypto
│   │   ├── leader/               # dispatch, synthesis, media_gen, notebooklm, serve
│   │   ├── academic/             # research, literature, doe, paper, perplexity, browser_agent
│   │   └── experiment/           # simulation, analysis, synthetic, report_data, autoresearch
│   ├── skills/                   # 14 OpenClaw SKILL.md skill definitions
│   ├── tests/                    # pytest suite
│   └── configs/, scripts/, docker/, roles/, common/
│
├── core/                         # OAS shared framework (241 tests, ~4,500 LOC)
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
│       ├── webhooks/              # External event delivery (Phase 23)
│       │   ├── registry.py       # Webhook subscription CRUD
│       │   └── dispatcher.py     # HMAC-SHA256 + retry + DLQ
│       ├── campaign_journal.py   # Append-only JSONL with SHA-256 hash chain
│       ├── campaign_templates.py # YAML-defined reusable campaign patterns
│       ├── lineage.py            # Artifact provenance graph (DAG queries)
│       ├── audit_export.py       # ZIP audit bundle with integrity manifest
│       ├── protocols/
│       │   ├── drvp.py           # 29 event types, Redis Pub/Sub transport
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
│   └── deer-flow-main/           # DeerFlow 2.0 super agent harness (ByteDance)
│       └── skills/custom/darklab-research/  # DarkLab custom research skill
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
.venv/bin/pytest cluster/tests/ -q   # 176 tests
.venv/bin/pytest core/tests/ -q      # 628 tests (10 skipped without langgraph/yaml)
cd office && npx vitest run           # 28 tests
```

**Total: 832 passing** (run cluster and core separately — conftest collision). Use `.venv/bin/pytest` directly — system `VIRTUAL_ENV` can conflict with uv workspace.

## Key Modules

### cluster/agents/shared/
- **`models.py`** — `Task`, `TaskResult`, `TaskType` (16 enum values: 5 academic + 6 experiment + 4 leader + STATUS), `AgentInfo`
- **`config.py`** — Pydantic `Settings` (25 fields): API keys, networking, Paperclip, OpenViking, Redis, LiteLLM, signing keys, logging
- **`llm_client.py`** — Async wrappers for Anthropic, OpenAI, Gemini, Perplexity with atomic budget enforcement (`_check_and_record_spend` under `fcntl.LOCK_EX`)
- **`node_bridge.py`** — stdin/argv JSON → Task → handler → TaskResult → stdout JSON
- **`audit.py`** — Append-only JSONL audit logger
- **`crypto.py`** — Ed25519 payload signing/verification (PyNaCl)

### core/oas_core/ (22 modules, all implemented)

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

**Sub-agents:**
- **`subagents/claude_code.py`** (250 LOC) — Spawns Claude Code CLI as subprocess. Strips CLAUDECODE env, model/tool overrides, JSON output parsing.

**Integration:**
- **`deep_agent.py`** (175 LOC) — Deepagents subprocess wrapper: `DeepAgentRunner` with isolated workspaces, timeout, file seeding
- **`sandbox.py`** (185 LOC) — NemoClaw sandbox manager: `create()`, `destroy()`, `run_code()` with Linux/macOS fallback

### cluster/agents/leader/
- **`dispatch.py`** — Dual-mode dispatch with 5 lazy-init middleware singletons (sentinel pattern). Slash commands → ROUTING_TABLE; free-form → swarm → campaign. Memory pre-loading, audit logging, CampaignEngine execution.
- **`serve.py`** — FastAPI (:8100): `/health`, `/drvp/events/{company_id}` (SSE), `/dispatch`, `/synthesize`, `/media`, `/task`
- **`swarm_registry.py`** — Maps 12-15 DarkLab agents (notebooklm, deerflow optional) to handlers for the LangGraph swarm router

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

29 event types emitted by the middleware pipeline. Events flow via Redis Pub/Sub (`drvp:{company_id}`) and persist to the Paperclip activity log.

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

**110 of 110 tasks implemented.** 832 tests passing (628 core + 176 cluster + 28 office) + 16 MOQ tests.

**Phase 19 tasks (Live Deployment + Research Pipeline):**

| # | Task | Status |
|---|------|--------|
| 83 | Deploy DeerFlow + deps to Leader Mac mini Docker (Dockerfile.leader baked) | **Complete** |
| 84 | Liaison-broker `__dispatch` handler (Go): DarkLab commands → Leader :8100, `/deepresearch` → daemon :8102 | **Complete** |
| 85 | Deep Research daemon (:8102) with LaunchAgent auto-start, request queue, health/status/results/schedule endpoints | **Complete** |
| 86 | 9 academic source search: arXiv, Semantic Scholar, PubMed, OpenAlex, CrossRef, CORE, EuropePMC, DOAJ, DuckDuckGo | **Complete** |
| 87 | `/swarmresearch` command — 5-angle parallel research with synthesis agent | **Complete** |
| 88 | MOQ library (767 LOC, 16 tests) — head_scorer, quantizer, cache with autoresearch loop | **Complete** |

**Phase 11 tasks (RL Self-Evolution + Debate Simulation):**

| # | Task | Status |
|---|------|--------|
| 46 | `RL_EVOLVED` tier in ModelRouter + per-agent LoRA routing | **Complete** |
| 47 | RolloutCollector middleware (captures conversations as JSONL) | **Complete** |
| 48 | RL config fields in Settings + baseline versioning (`/rl-freeze`) | **Complete** |
| 49 | MiroShark adapter + `/debate` command (6 scenario types) | **Complete** |
| 50 | TranscriptConverter (MiroShark → OpenClaw-RL rollout format) | **Complete** |
| 51 | 10 new DRVP event types (6 RL + 4 debate) + Office consumers | **Complete** |
| 52 | `/rl-train`, `/rl-status`, `/rl-rollback` dispatch commands | **Complete** |
| 53 | RL subpackage: promotion gate, training pipeline, checkpoint eval, A/B comparison, data manager, circuit breaker | **Complete** |
| 54 | Deep Research orchestrator with iterative convergence loop | **Complete** |
| 55 | Academic source search: arXiv, Semantic Scholar, bioRxiv | **Complete** |
| 56 | 5-metric convergence evaluator (completeness, sources, structure, novelty, accuracy) | **Complete** |
| 57 | `/deepresearch` command + DRVP events (5 new types) + Office consumer | **Complete** |
| 58 | Expand academic search to 9 sources (add PubMed, OpenAlex, CrossRef, EuropePMC) | **Complete** |
| 59 | Knowledge base persistence (knowledge.jsonl + global_lessons.jsonl) | **Complete** |
| 60 | `/parametergolf` route + PARAMETER_GOLF TaskType | **Complete** |
| 61 | Knowledge base tests (7 new tests) | **Complete** |
| 62 | Wire Tinker training job submission into `/rl-train` (replaces stub) | **Complete** |
| 63 | Wire MiroShark simulation + transcript conversion into `/debate` (replaces stub) | **Complete** |
| 64 | `/swarmresearch` command — 5-perspective parallel research with synthesis | **Complete** |
| 65 | `SWARM_RESEARCH` TaskType + dispatch route | **Complete** |
| 66 | TurboQuant PolarQuant compression (rotation + scalar quantization) | **Complete** |
| 67 | QJL 1-bit residual correction | **Complete** |
| 68 | CompressedKVCache container with on-demand decompression | **Complete** |
| 69 | Multi-agent MemoryPool with priority eviction | **Complete** |
| 70 | Middle-Out adaptive precision (attention-aware bit assignment) | **Complete** |
| 71 | RuntimeAdapter (Ollama/MLX hooks) + `/turboq-status` command | **Complete** |
| 72 | Qwen3 multi-model strategy: specialist routing for coding/reasoning/general tasks | **Complete** |
| 73 | RL_EVOLVED tier wired to Qwen3:8b + TurboQuant 4-bit (12k tokens/agent context) | **Complete** |
| 74 | Swarm registry entries: deepresearch, swarmresearch, debate agents | **Complete** |
| 75 | `RLStatusPanel.tsx` — RL training metrics panel for Agent Office | **Complete** |
| 76 | `TurboQuantPanel.tsx` — KV cache pool utilization panel for Agent Office | **Complete** |
| 77 | DRVP consumer handlers for `memory.pool.*` events in Office TypeScript | **Complete** |
| 78 | `/results` command — list recent deep research from knowledge base | **Complete** |
| 79 | `/schedule` command — manage recurring auto-research schedules (add/list/remove) | **Complete** |
| 80 | `LLMSynthesizer` — Qwen3 via Ollama for structured report generation (with placeholder fallback) | **Complete** |
| 81 | Wire RLStatusPanel + TurboQuantPanel into Office DashboardPage | **Complete** |
| 82 | `RESULTS` + `SCHEDULE` TaskTypes + dispatch routes (25 total) | **Complete** |

**Phase 20 tasks (Campaign Intelligence — OAS-3 completion):**

| # | Task | Status |
|---|------|--------|
| 89 | `DecisionPolicyEngine` with 4 composable rules (CostCeiling, ConfidenceFloor, MaxRetries, HumanEscalation) | **Complete** |
| 90 | `ReadinessScorer` with 4 dimensions (knowledge, simulation, experiment, infrastructure) | **Complete** |
| 91 | `CampaignReflector` — post-step analysis with knowledge base integration | **Complete** |
| 92 | `UncertaintyRouter` — readiness-aware pre-routing with prerequisite suggestions | **Complete** |
| 93 | 4 new DRVP events + Office `DecisionPanel` + consumer handlers | **Complete** |

**Phase 21 tasks (Governance Maturity — OAS-4 completion):**

| # | Task | Status |
|---|------|--------|
| 94 | `CampaignJournal` — append-only JSONL with SHA-256 hash chain + `JournalReader` | **Complete** |
| 95 | `CampaignTemplate` + `TemplateRegistry` — YAML-defined, 4 built-in templates | **Complete** |
| 96 | `LineageGraph` — DAG provenance with ancestors/descendants/path queries + DOT/JSON export | **Complete** |
| 97 | `export_campaign_audit()` — ZIP bundle with checksums + `verify_audit_bundle()` | **Complete** |
| 98 | Signed approval records — Ed25519 `sign_approval()` / `verify_approval_signature()` in governance | **Complete** |

**Phase 22 tasks (Multi-Node Foundation — OAS-5 start):**

| # | Task | Status |
|---|------|--------|
| 99 | `TaskQueue` — Redis-backed priority queue with in-memory fallback, visibility timeout, DLQ | **Complete** |
| 100 | `HeartbeatService` — node registration, heartbeat tracking, lease model, state transitions | **Complete** |
| 101 | `Scheduler` — resource-aware dispatch with discovery integration, rebalancing | **Complete** |
| 102 | `DiscoveryService` — dynamic node capabilities, default DarkLab topology, model lookup | **Complete** |
| 103 | `IsolationPolicy` — failure classification (4 classes), circuit breaker, node failure handling | **Complete** |
| 104 | `ClusterStatusPanel.tsx` — node health, active tasks, wired into Dashboard | **Complete** |

**Phase 23 tasks (Platformization Foundation — OAS-6 start):**

| # | Task | Status |
|---|------|--------|
| 105 | `WebhookRegistry` + `WebhookDispatcher` — HMAC-SHA256 signatures, retry with backoff, DLQ | **Complete** |
| 106 | Campaign template CRUD via `TemplateRegistry` (built in Phase 21) | **Complete** |
| 107 | Structured campaign creation via `CampaignSchema.from_checkpoint()` + templates | **Complete** |
| 108 | `OASClient` + `AsyncOASClient` Python SDK — campaigns, dispatch, webhooks, health | **Complete** |
| 109 | API key management via SDK auth headers + Paperclip `agent_api_keys` table | **Complete** |
| 110 | `ClusterStatusPanel` + partner-scoped dashboard panels | **Complete** |

## Campaign Intelligence (Decision Engine)

The decision engine upgrades OAS from reactive routing to proactive campaign management:

- **Policy Engine:** `core/oas_core/decision/policy_engine.py` — composable `PolicyRule` objects evaluate (confidence, cost, risk, readiness). 4 built-in rules: CostCeiling, ConfidenceFloor, MaxRetries, HumanEscalation. Outputs `DecisionRecommendation` with 6 action types.
- **Readiness Scoring:** `core/oas_core/decision/readiness.py` — 4-dimension scoring (knowledge 35%, simulation 20%, experiment 15%, infrastructure 30%). Each dimension has 3-4 sub-scores.
- **Reflection:** `core/oas_core/decision/reflection.py` — post-step analysis comparing output vs intent. Scores `intent_alignment` and `evidence_gain`, stores lessons in knowledge base.
- **Uncertainty Router:** `core/oas_core/decision/uncertainty_router.py` — pre-routing check that evaluates readiness before dispatching. Suggests prerequisite steps if readiness below threshold.
- **DRVP events:** `decision.recommended`, `readiness.scored`, `campaign.reflection.completed`, `uncertainty.routing`
- **Office panel:** `DecisionPanel.tsx` — shows latest recommendation, confidence bar, readiness dimension bars

## Governance Maturity

- **Campaign Journal:** `core/oas_core/campaign_journal.py` — append-only JSONL per campaign with SHA-256 hash chain for tamper detection. `JournalReader` for cross-campaign queries by type/time.
- **Template Library:** `core/oas_core/campaign_templates.py` — YAML-defined templates loaded via `TemplateRegistry.load_from_dir()`. 4 built-in templates in `cluster/templates/`: `literature-review`, `hypothesis-test`, `full-pipeline`, `simulation-validate`.
- **Lineage Graph:** `core/oas_core/lineage.py` — in-memory DAG with 5 node types (campaign/step/artifact/approval/cost) and 5 edge types. Supports `ancestors()`, `descendants()`, `path()`, `build_from_journal()`, `to_dot()`, `to_json()`.
- **Audit Export:** `core/oas_core/audit_export.py` — `export_campaign_audit()` creates ZIP with journal, lineage, costs, approvals + SHA-256 checksum manifest. `verify_audit_bundle()` validates integrity.
- **Signed Approvals:** Ed25519 `sign_approval()` / `verify_approval_signature()` added to `GovernanceMiddleware` for cryptographic approval records.

## Multi-Node Scheduler

Distributed task scheduling across the DarkLab cluster with health monitoring and failure isolation:

- **Task Queue:** `core/oas_core/scheduler/task_queue.py` — 5 priority levels, device affinity, Redis sorted sets with in-memory fallback, visibility timeout, DLQ
- **Heartbeat:** `core/oas_core/scheduler/heartbeat.py` — node registration, periodic heartbeats (10s), state machine (online → degraded → offline), task leases
- **Scheduler:** `core/oas_core/scheduler/scheduler.py` — resource-aware dispatch, discovery integration, lease rebalancing, static fallback routing
- **Discovery:** `core/oas_core/scheduler/discovery.py` — dynamic node capabilities, default 3-node DarkLab topology, model/command lookup
- **Isolation:** `core/oas_core/scheduler/isolation.py` — failure classification (transient/resource/node_down/permanent), circuit breaker per (node, task_type), node failure handling
- **Config:** Feature-flag via `DARKLAB_SCHEDULER_ENABLED` (optional — falls back to direct dispatch)

## Webhook Event Layer

External event subscriptions with reliable delivery:

- **Registry:** `core/oas_core/webhooks/registry.py` — CRUD for webhook subscriptions, event type filtering, company scoping
- **Dispatcher:** `core/oas_core/webhooks/dispatcher.py` — HMAC-SHA256 signatures, exponential backoff retry (1s/5s/30s/5m), dead letter log
- **Integration:** Subscribe to any of the 29 DRVP event types for real-time external notifications

## Python SDK

`sdk/opensens_oas/` — minimal client for programmatic campaign management:

- **`OASClient`** — synchronous HTTP client: `create_campaign()`, `dispatch()`, `subscribe_webhook()`, `health()`
- **`AsyncOASClient`** — async version for integration with asyncio applications
- **Auth:** Bearer token via `api_key` parameter
- **Package:** `opensens-oas` (to be published via PyPI)

## DeerFlow Integration

DeerFlow 2.0 (ByteDance) is integrated as an embedded research harness via `DeerFlowAdapter`:

- **Command:** `/deerflow <research objective>` — deep multi-step research with sub-agents
- **Adapter:** `core/oas_core/adapters/deerflow.py` — wraps `DeerFlowClient` with DRVP events
- **Handler:** `cluster/agents/experiment/deerflow_research.py` — Task/TaskResult bridge
- **Model routing:** Respects OAS tiered model selection (PLANNING/EXECUTION/BOOST)
- **Boost eligible:** Added to `BOOST_ELIGIBLE_TASKS` for free AIClient models
- **Custom skill:** `frameworks/deer-flow-main/skills/custom/darklab-research/SKILL.md`
- **Config:** `~/.darklab/deerflow/config.yaml` (models, sandbox, memory, skills)
- **Import guard:** `DEERFLOW_AVAILABLE` — OAS works without `deerflow-harness` installed

**Install DeerFlow harness:**
```bash
uv pip install -e ./frameworks/deer-flow-main/backend/packages/harness
```

See `docs/DEERFLOW-INTEGRATION-PLAN.md` for the full deployment plan.

## OpenClaw-RL Integration

OpenClaw-RL is the RL framework enabling agent self-evolution through live conversation feedback:

- **Adapter:** `core/oas_core/adapters/openclaw_rl.py` — OpenClaw-RL proxy client with session headers
- **Rollout collector:** `core/oas_core/middleware/rl_rollout.py` — captures every conversation as JSONL training data
- **Training pipeline:** `core/oas_core/rl/training_pipeline.py` — rollout loading, PRM scoring, batch assembly
- **Promotion gate:** `core/oas_core/rl/promotion_gate.py` — 4-gate checkpoint validation (min score, baseline regression, previous promoted, catastrophic failure)
- **A/B comparison:** `core/oas_core/rl/ab_comparison.py` — side-by-side evaluation of RL vs baseline
- **Data manager:** `core/oas_core/rl/data_manager.py` — retention policy for rollouts and checkpoints
- **Tinker client:** `core/oas_core/rl/tinker_client.py` — cloud training API with circuit breaker
- **Per-agent LoRA:** Each of the 18 agent types gets its own LoRA adapter to prevent cross-task interference
- **Model routing:** `RL_EVOLVED` tier in `model_router.py` — routes to LoRA-adapted proxy when available, falls back to EXECUTION
- **Commands:** `/rl-train`, `/rl-status`, `/rl-rollback`, `/rl-freeze` via `cluster/agents/leader/rl_commands.py`
- **Import guard:** `OPENCLAW_RL_AVAILABLE` — OAS works without OpenClaw-RL proxy running
- **Config:** `DARKLAB_RL_ENABLED`, `DARKLAB_TINKER_API_KEY`, `DARKLAB_RL_TRAINING_METHOD` (see Settings)
- **48 tests** covering rollouts, promotion gate, training pipeline, transcript conversion, data management, A/B comparison, E2E cycles

## MiroShark Integration

MiroShark provides synthetic debate scenarios for accelerated agent training:

- **Adapter:** `core/oas_core/adapters/miroshark.py` — simulation engine client with 6 debate scenarios
- **Transcript converter:** `core/oas_core/rl/transcript_converter.py` — multi-agent debate → single-agent rollout format
- **Command:** `/debate <topic>` — generates multi-agent debate (peer-review, hypothesis, methodology, literature-dispute, cross-domain, budget)
- **Skill:** `cluster/skills/darklab-debate/SKILL.md` — debate skill definition
- **Reward signal:** MiroShark's belief state (stance/confidence/trust) feeds into OpenClaw-RL PRM as next-state signals
- **Docker:** `miroshark` + `neo4j-miroshark` in `docker-compose.services.yml` (profile: miroshark)
- **Requires:** Neo4j 5.15+ for knowledge graph, Ollama or cloud API for simulation rounds
- **Import guard:** `MIROSHARK_AVAILABLE` — OAS works without MiroShark installed
- **Config:** `DARKLAB_MIROSHARK_ENABLED`, `DARKLAB_MIROSHARK_URL`, `DARKLAB_DEBATE_DEFAULT_ROUNDS`

See `docs/OPENCLAW-RL-MIROSHARK-INTEGRATION-PLAN.md` for the full strategy.

## Deep Research Pipeline

Iterative deep research with academic source search and convergence evaluation:

- **Orchestrator:** `core/oas_core/deep_research/orchestrator.py` — multi-phase pipeline (search → synthesize → evaluate → iterate)
- **Academic search:** `core/oas_core/deep_research/sources.py` — parallel search across 7 databases (arXiv, Semantic Scholar, bioRxiv, PubMed, OpenAlex, CrossRef, EuropePMC)
- **Knowledge base:** `core/oas_core/deep_research/knowledge_base.py` — JSONL persistence for cross-run learning (knowledge entries + lessons)
- **Evaluator:** `core/oas_core/deep_research/evaluator.py` — 5-metric scoring (completeness 25%, source quality 25%, structure 20%, novelty 15%, accuracy 15%)
- **Command:** `/deepresearch <topic>` — iterates until quality >= 0.75 threshold (max 5 iterations)
- **Handler:** `cluster/agents/leader/deep_research_cmd.py` — Task/TaskResult bridge
- **DRVP events:** 5 new types (`deep_research.started/iteration/search/scored/completed`)
- **Config:** `ResearchConfig` (max_iterations, threshold, source limits)

See `docs/MEMENTO-CODEX-INTEGRATION-PLAN.md` for the full deployment plan.

## TurboQuant KV Cache Compression

Enables ~6x memory reduction for multi-agent long-context reasoning on Mac hardware (16-24GB):

- **PolarQuant:** `core/oas_core/turbo_quant/polar_quant.py` — random Hadamard rotation + per-channel scalar quantization (2-8 bit)
- **QJL:** `core/oas_core/turbo_quant/qjl.py` — 1-bit Johnson-Lindenstrauss residual correction
- **KV Cache:** `core/oas_core/turbo_quant/kv_cache.py` — compressed container with on-demand decompression per attention head
- **Memory Pool:** `core/oas_core/turbo_quant/memory_pool.py` — multi-agent pool with priority-based eviction
- **Middle-Out:** `core/oas_core/turbo_quant/middle_out.py` — attention-aware adaptive precision (high-importance tokens → 6-bit, medium → 3-bit, low → 2-bit)
- **Runtime Adapter:** `core/oas_core/turbo_quant/runtime_adapter.py` — Ollama/MLX integration hooks with capacity estimation
- **Command:** `/turboq-status` — pool status, compression ratios, capacity estimates
- **Config:** `DARKLAB_TURBOQUANT_ENABLED`, `DARKLAB_TURBOQUANT_BITS`, `DARKLAB_TURBOQUANT_POOL_MB`
- **Capacity (4GB pool, 4-bit):** ~120k tokens total / ~12k per agent (10 agents) / ~2.4k per agent (50 agents)

See `docs/TURBOQUANT-INTEGRATION-PLAN.md` for the full architecture.

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
