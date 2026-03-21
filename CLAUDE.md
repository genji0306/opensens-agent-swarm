# Opensens Agent Swarm (OAS) — Claude Code Project Guide

## What This Is

**Opensens Agent Swarm** is the unified agentic research platform for the DarkLab distributed AI research cluster. It merges the DarkLab agent infrastructure (dispatch routing, budget enforcement, 14 research skills, multi-AI cross-validation) with a suite of agentic frameworks (LangGraph Swarm, OpenViking memory, agency-agents personas, deepagents harness) under Paperclip governance and Agent Office visualization.

The system runs autonomous scientific research on a Mac mini cluster, where every request flows through a governed pipeline with real-time visual feedback.

See `docs/OAS-DEVELOPMENT-PLAN.md` for the comprehensive roadmap (5 phases, 40 tasks).

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
│       ├── protocols/
│       │   ├── drvp.py           # 22 event types, Redis Pub/Sub transport
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
├── frameworks/                   # Reference frameworks (read-only)
│   ├── langgraph-swarm/          # LangGraph multi-agent handoff
│   ├── openviking/               # Context database for AI agents
│   ├── agency-agents/            # 70+ curated agent persona definitions
│   ├── deepagents/               # Batteries-included agent harness
│   ├── nemoclaw/                 # NVIDIA sandbox wrapper
│   ├── openclaw/                 # OpenClaw core (reference)
│   ├── claude-code-skill/        # Claude Code MCP skill
│   ├── browser-use/              # Browser automation
│   └── AIClient-2-API-main/      # Client-account-to-API proxy (Gemini/Kiro/Codex/Grok)
│
└── docs/
    ├── OAS-DEVELOPMENT-PLAN.md           # Full roadmap
    ├── AICLIENT-INTEGRATION-PLAN.md      # AIClient boost tier strategy
    └── SECURITY-AND-INTEGRATION-PLAN.md  # OneCLI security audit + PicoClaw↔Paperclip integration
```

## Running Tests

```bash
cd "Opensens Agent Swarm"
.venv/bin/pytest cluster/tests/ -q   # 123 tests
.venv/bin/pytest core/tests/ -q      # 279 tests (7 skipped without langgraph)
cd office && npx vitest run           # 28 tests
```

**Total: 430 passing** (run cluster and core separately — conftest collision). Use `.venv/bin/pytest` directly — system `VIRTUAL_ENV` can conflict with uv workspace.

## Key Modules

### cluster/agents/shared/
- **`models.py`** — `Task`, `TaskResult`, `TaskType` (15 enum values: 5 academic + 5 experiment + 4 leader + STATUS), `AgentInfo`
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

**Sub-agents:**
- **`subagents/claude_code.py`** (250 LOC) — Spawns Claude Code CLI as subprocess. Strips CLAUDECODE env, model/tool overrides, JSON output parsing.

**Integration:**
- **`deep_agent.py`** (175 LOC) — Deepagents subprocess wrapper: `DeepAgentRunner` with isolated workspaces, timeout, file seeding
- **`sandbox.py`** (185 LOC) — NemoClaw sandbox manager: `create()`, `destroy()`, `run_code()` with Linux/macOS fallback

### cluster/agents/leader/
- **`dispatch.py`** — Dual-mode dispatch with 5 lazy-init middleware singletons (sentinel pattern). Slash commands → ROUTING_TABLE; free-form → swarm → campaign. Memory pre-loading, audit logging, CampaignEngine execution.
- **`serve.py`** — FastAPI (:8100): `/health`, `/drvp/events/{company_id}` (SSE), `/dispatch`, `/synthesize`, `/media`, `/task`
- **`swarm_registry.py`** — Maps 12-13 DarkLab agents (notebooklm optional) to handlers for the LangGraph swarm router

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
| synthesize | leader | darklab-synthesis | SYNTHESIZE |
| report | leader | darklab-media-gen | MEDIA_GEN |
| notebooklm | leader | darklab-notebooklm | NOTEBOOKLM |

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

25 event types emitted by the middleware pipeline. Events flow via Redis Pub/Sub (`drvp:{company_id}`) and persist to the Paperclip activity log.

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
- Optional deps guarded: langgraph (`SWARM_AVAILABLE`), websockets (`_WS_AVAILABLE`), PyNaCl (`_NACL_AVAILABLE`)
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

**44 of 44 tasks implemented.** Deployment tasks ready for SSH to Leader:

| # | Task | Status |
|---|------|--------|
| 26 | Deploy OpenViking to Docker stack | Docker config ready (`docker-compose.services.yml`), needs `docker compose up` on Leader |
| 28 | Research knowledge graph schema | Implemented in `memory.py`: `store_research()`, `find_research()`, `build_knowledge_context()` |
| 37 | deepagents integration | Implemented in `deep_agent.py`: `DeepAgentRunner` subprocess wrapper |
| 38 | NemoClaw sandboxing | Implemented in `sandbox.py`: `SandboxManager` with create/destroy/run_code, macOS fallback |
| 40 | E2E testing | 17 tests in `test_campaign_e2e.py`: plan validation, DAG, DRVP events, sandbox, deepagents |

**Proposed new tasks** (from AIClient integration plan, see `docs/AICLIENT-INTEGRATION-PLAN.md`):

| # | Task | Priority |
|---|------|----------|
| 41 | Deploy AIClient-2-API to Leader Docker stack | Docker config ready (`docker-compose.services.yml`), needs `docker compose up` on Leader |
| 42 | Add boost tier to model_router.py + call_aiclient() | **Complete** |
| 43 | Paperclip boost toggle + DRVP llm.call.boosted event | **Complete** |
| 44 | PicoClaw /boost command | **Complete** — `/boost on\|off\|status` in dispatch.py, syncs with Paperclip |

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
