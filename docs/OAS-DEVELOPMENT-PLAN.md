# Opensens Agent Swarm (OAS) — Comprehensive Development Plan

> **Version:** 1.0
> **Date:** 2026-03-18
> **Author:** Opensens DarkLab Engineering
> **Status:** Draft — Pending Team Review

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis](#2-current-state-analysis)
3. [Merge Strategy: darklab-installer → Opensens Agent Swarm](#3-merge-strategy)
4. [OAS Unified Architecture](#4-oas-unified-architecture)
5. [Leader Agent Roadmap (Mac Mini)](#5-leader-agent-roadmap)
6. [Paperclip Governance Expansion](#6-paperclip-governance-expansion)
7. [Agent Office ↔ Paperclip Integration](#7-agent-office--paperclip-integration)
8. [Dynamic Request Visualization Protocol (DRVP)](#8-dynamic-request-visualization-protocol)
9. [Implementation Phases](#9-implementation-phases)
10. [Risk Mitigation](#10-risk-mitigation)

---

## 1. Executive Summary

**Opensens Agent Swarm (OAS)** is the next-generation agentic platform that unifies the DarkLab research cluster with the broader Opensens Swarm ecosystem. The merger combines:

- **DarkLab's proven agent infrastructure** (dispatch routing, budget enforcement, multi-AI cross-validation, 14 research skills) with
- **Swarm's agentic frameworks** (LangGraph handoff, deep agents, OpenViking context memory, NemoClaw sandboxing, agency-agents persona library)

under **Paperclip governance** and **Agent Office visualization**.

The result is a self-governing AI research lab where every request — from a Telegram command to a multi-step campaign — flows through a governed pipeline with real-time visual feedback on both the Agent Office floor plan and the Paperclip dashboard.

---

## 2. Current State Analysis

### 2.1 What Each Component Brings

| Component | Strength | Gap |
|-----------|----------|-----|
| **darklab-installer** | 14 working skills, dispatch routing, budget enforcement, Ed25519 audit, EIP contracts, 56 tests | No swarm handoff, static routing table, no agent memory, no sandboxing |
| **LangGraph Swarm** | Dynamic agent handoff via tool calls, shared state graph, multi-turn memory | No budget/governance, no domain agents, library only |
| **deepagents** | Sub-agent spawning, auto-summarization, todo planning, middleware stack, MCP support | No domain-specific agents, single-user CLI focus |
| **OpenViking** | Tiered context (L0/L1/L2), virtual filesystem, 43% task improvement, OpenClaw memory plugin | No budget system, complex setup (Rust+Go+Python+C++) |
| **NemoClaw** | Secure sandbox (Landlock+seccomp), NVIDIA inference routing, policy governance | Requires k3s/Docker, NVIDIA-specific |
| **agency-agents** | 70+ curated agent personas, multi-tool installation, standardized format | Personas only — no runtime, no state |
| **OpenClaw** | Gateway (:18789), channels (Telegram/WhatsApp/Slack), skills system, TUI | Already deployed at DarkLab, but acts as passive relay |
| **Paperclip** | Org chart, issues, approvals, budgets, heartbeat runs, cost ledger, WebSocket events | Disconnected from Agent Office, no real-time task visualization |
| **Agent Office** | 2D/3D floor plan, speech bubbles, token charts, network graph, WS event stream | Monitors OpenClaw only, no Paperclip awareness |
| **Claude Code Skill** | Programmatic Claude Code access, session management, agent teams, streaming | Backend API dependency, thin HTTP wrapper |

### 2.2 Key Insight

The DarkLab cluster already runs the three critical services — **OpenClaw** (:18789), **Paperclip** (:3100), **Agent Office** (:5180) — but they operate as silos. The Swarm folder contains the missing pieces to connect them: LangGraph for dynamic handoff, OpenViking for persistent memory, agency-agents for specialized personas, and deepagents for sub-agent orchestration.

---

## 3. Merge Strategy

### 3.1 Folder Restructure

Rename `Opensens Swarm/` → `Opensens Agent Swarm/` and absorb `darklab-installer/` as the `cluster/` subdirectory:

```
Opensens Agent Swarm/                    # Root (formerly Opensens Swarm)
├── CLAUDE.md                            # Unified project guide
├── OAS-ARCHITECTURE.md                  # This plan, evolved into living architecture doc
├── pyproject.toml                       # Unified Python workspace
├── package.json                         # pnpm workspace root
│
├── cluster/                             # ← darklab-installer (moved here)
│   ├── install.sh
│   ├── roles/
│   ├── common/
│   ├── configs/
│   ├── scripts/
│   ├── agents/
│   │   ├── shared/                      # models, config, llm_client, node_bridge, audit, crypto
│   │   ├── leader/                      # dispatch, synthesis, media_gen, notebooklm, serve
│   │   ├── academic/                    # research, literature, doe, paper, perplexity, browser_agent
│   │   └── experiment/                  # simulation, analysis, synthetic, report_data, autoresearch
│   ├── skills/
│   ├── tests/
│   ├── docker/
│   └── DARKLAB-PLAN.md
│
├── core/                                # NEW — shared OAS framework
│   ├── oas_core/
│   │   ├── swarm.py                     # LangGraph swarm builder (wraps langgraph-swarm)
│   │   ├── handoff.py                   # Handoff tool factory with Paperclip awareness
│   │   ├── memory.py                    # OpenViking integration layer
│   │   ├── persona.py                   # Agency-agents persona loader
│   │   ├── sandbox.py                   # NemoClaw sandbox manager (optional)
│   │   ├── middleware/                   # Adapted from deepagents middleware
│   │   │   ├── budget.py                # Paperclip budget enforcement middleware
│   │   │   ├── audit.py                 # Ed25519 audit middleware
│   │   │   ├── memory.py                # OpenViking memory middleware
│   │   │   └── summarization.py         # Context window management
│   │   ├── protocols/                   # NEW — visualization protocols
│   │   │   ├── drvp.py                  # Dynamic Request Visualization Protocol
│   │   │   └── events.py                # Unified event schema (OpenClaw + Paperclip)
│   │   └── adapters/
│   │       ├── paperclip.py             # Paperclip REST/WS client
│   │       └── openclaw.py              # OpenClaw gateway client
│   └── pyproject.toml
│
├── office/                              # ← Agent Office (moved from cluster/Agent office/)
│   ├── src/
│   │   ├── gateway/                     # Existing OpenClaw WS adapter
│   │   ├── paperclip/                   # NEW — Paperclip WS + REST adapter
│   │   ├── drvp/                        # NEW — DRVP event consumer
│   │   ├── store/
│   │   ├── components/
│   │   │   ├── panels/
│   │   │   │   ├── PaperclipPanel.tsx   # NEW — governance overview
│   │   │   │   ├── RequestFlowGraph.tsx # NEW — live request DAG visualization
│   │   │   │   └── BudgetGauge.tsx      # NEW — real-time budget meters
│   │   │   └── overlays/
│   │   │       └── TaskBadge.tsx        # NEW — issue ID badge on agent avatar
│   │   └── pages/
│   │       └── RequestView.tsx          # NEW — full-screen request flow page
│   └── package.json
│
├── paperclip/                           # ← paperclip-master (reference/fork)
│   ├── server/
│   ├── ui/
│   ├── packages/
│   └── skills/
│
├── frameworks/                          # Reference frameworks (read-only)
│   ├── langgraph-swarm/                 # LangGraph Swarm library
│   ├── deepagents/                      # Deep agents harness
│   ├── openviking/                      # OpenViking context DB
│   ├── nemoclaw/                        # NemoClaw sandbox
│   ├── agency-agents/                   # Agent persona library
│   ├── openclaw/                        # OpenClaw core (reference)
│   └── claude-code-skill/              # Claude Code skill
│
└── docs/
    ├── OAS-DEVELOPMENT-PLAN.md          # This document
    ├── DRVP-SPEC.md                     # Protocol specification
    └── INTEGRATION-GUIDE.md             # How to add new agents
```

### 3.2 Merge Steps

1. **Create `Opensens Agent Swarm/` at the Darklab project root**
2. **Move `darklab-installer/` → `Opensens Agent Swarm/cluster/`**, preserving git history with `git mv`
3. **Move existing Swarm subfolders → `frameworks/`** (read-only reference copies)
4. **Copy `paperclip-master/` → `paperclip/`** (active fork for customization)
5. **Move Agent Office → `office/`** with a symlink back to `cluster/Agent office/` for Docker compatibility
6. **Create `core/` as a new Python package** (`oas-core`) that imports from both `cluster/agents/shared/` and `frameworks/`
7. **Update `pyproject.toml`** at root as a uv workspace spanning `core/` and `cluster/`
8. **Update all Docker Compose** references to use new paths
9. **Update `CLAUDE.md`** to reflect the unified project structure

### 3.3 Backward Compatibility

- `cluster/` continues to work standalone — `install.sh`, all 14 skills, all tests
- OpenClaw at `:18789` sees no change — skill SKILL.md files stay in `cluster/skills/`
- Paperclip at `:3100` sees no change — adapter configs unchanged
- Agent Office at `:5180` continues to work — just moves to `office/`

---

## 4. OAS Unified Architecture

### 4.1 The Stack

```
┌─────────────────────────────────────────────────────────────────────┐
│                        VISUALIZATION LAYER                         │
│   Agent Office (:5180)              Paperclip UI (:3100)           │
│   ┌─────────────────────┐          ┌─────────────────────┐        │
│   │ 2D/3D Floor Plan    │◄─DRVP──►│ Dashboard + Kanban   │        │
│   │ Request Flow Graph  │          │ Live Run Widget      │        │
│   │ Budget Gauges       │          │ Org Chart + Costs    │        │
│   └────────┬────────────┘          └────────┬────────────┘        │
│            │ WS                              │ WS + REST           │
├────────────┼────────────────────────────────┼─────────────────────┤
│                     ORCHESTRATION LAYER                            │
│                                                                    │
│   ┌─────────────────────────────────────────────────────────┐     │
│   │                  OAS Core (oas-core)                     │     │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │     │
│   │  │ Swarm    │ │ Handoff  │ │ Memory   │ │ Persona   │  │     │
│   │  │ Builder  │ │ Factory  │ │ (Viking) │ │ Loader    │  │     │
│   │  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │     │
│   │  ┌────────────────────────────────────────────────────┐ │     │
│   │  │  Middleware Pipeline                                │ │     │
│   │  │  Budget → Audit → Memory → Summarization → DRVP   │ │     │
│   │  └────────────────────────────────────────────────────┘ │     │
│   └─────────────────────┬───────────────────────────────────┘     │
│                         │                                          │
│   ┌─────────────────────┼──────────────────────────────────┐      │
│   │         Paperclip Governance (:3100)                    │      │
│   │  Issues ← Approvals ← Budgets ← Cost Events ← Runs   │      │
│   └─────────────────────┬──────────────────────────────────┘      │
│                         │                                          │
├─────────────────────────┼─────────────────────────────────────────┤
│                     EXECUTION LAYER                                │
│                                                                    │
│   ┌─────────────────────┼──────────────────────────────────┐      │
│   │         OpenClaw Gateway (:18789)                       │      │
│   │  ┌────────┐  ┌─────────┐  ┌────────────┐              │      │
│   │  │Dispatch│  │ Skills  │  │ Channels   │              │      │
│   │  │(Smart) │  │ (14+)   │  │ TG/WA/Slack│              │      │
│   │  └───┬────┘  └────┬────┘  └────────────┘              │      │
│   │      │             │                                    │      │
│   │  ┌───┴─────────────┴──────────────────────────────┐    │      │
│   │  │  LangGraph Swarm (dynamic handoff)              │    │      │
│   │  │  ┌────────┐ ┌──────────┐ ┌────────────┐        │    │      │
│   │  │  │Leader  │↔│Academic  │↔│Experiment  │        │    │      │
│   │  │  │Agents  │ │Agents    │ │Agents      │        │    │      │
│   │  │  └────────┘ └──────────┘ └────────────┘        │    │      │
│   │  └────────────────────────────────────────────────┘    │      │
│   └────────────────────────────────────────────────────────┘      │
│                                                                    │
│   ┌────────────────────────────────────────────────────────┐      │
│   │         Supporting Services                             │      │
│   │  LiteLLM (:4000)  Redis (:6379)  OpenViking (:1933)   │      │
│   │  PicoClaw (TG)    Liaison (:8000) Cloudflared          │      │
│   └────────────────────────────────────────────────────────┘      │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│                     HARDWARE LAYER                                 │
│   Leader Mac mini (192.168.23.25)                                  │
│   Academic Mac mini (TBD)                                          │
│   Experiment Mac mini (TBD)                                        │
│   Boss MacBook (remote)                                            │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 Data Flow for a Typical Request

```
User sends "/research quantum dots for EIT electrodes" via Telegram
    │
    ▼
PicoClaw (Telegram bot) → Liaison Broker (:8000)
    │
    ▼
Leader dispatch.py → recognizes "research" command
    │
    ├──► DRVP: emit RequestCreated event → Agent Office + Paperclip
    │
    ▼
Paperclip: create issue DL-47 "Research: quantum dots for EIT electrodes"
    │    assign to DarkLab Academic, checkout heartbeat_run
    │
    ├──► DRVP: emit IssueAssigned event → Agent Office shows badge on Academic avatar
    │
    ▼
OAS Core Swarm: active_agent = "academic.research"
    │    middleware: budget_check → audit_log → memory_load → DRVP_start
    │
    ▼
academic.research.handle(task):
    │    1. call_perplexity("quantum dots EIT electrodes")
    │       ├──► DRVP: emit ToolCall("perplexity") → Agent Office shows tool panel
    │       └──► Paperclip: POST /cost-events {provider: "perplexity", cost: 0.002}
    │
    │    2. call_multi_ai(claude + gemini) for cross-validation
    │       ├──► DRVP: emit ToolCall("claude") → speech bubble streams response
    │       └──► Paperclip: POST /cost-events {provider: "anthropic", cost: 0.045}
    │
    │    3. OpenViking: store findings at viking://research/quantum-dots-eit/
    │       ├──► DRVP: emit MemoryWrite → Agent Office shows memory icon
    │
    │    4. LangGraph handoff → "academic.literature" for deep review
    │       ├──► DRVP: emit HandoffStarted → Agent Office animates walk to Literature desk
    │
    ▼
academic.literature.handle(task):  [swarm state preserved]
    │    ... (3-stage pipeline: Perplexity → Gemini → Claude)
    │    ... (more DRVP events, more cost events)
    │
    │    5. Handoff back → "leader.synthesis" for final report
    │       ├──► DRVP: emit HandoffStarted → Agent Office animates walk to Leader desk
    │
    ▼
leader.synthesis.handle(task):
    │    Merge all research into narrative (Claude Opus)
    │    Save artifact: synthesis_abc123.json
    │
    ├──► Paperclip: heartbeat_run status=done, attach artifact
    ├──► DRVP: emit RequestCompleted → Agent Office returns to idle, shows checkmark
    │
    ▼
Reply flows back through Telegram to user with synthesis summary
```

---

## 5. Leader Agent Roadmap (Mac Mini)

The Leader agent is the orchestration brain running on the Leader Mac mini (192.168.23.25). This roadmap evolves it from a static command router to an intelligent swarm coordinator.

### Stage 1: Foundation Hardening (Week 1-2)

**Objective:** Stabilize the existing Leader and prepare for swarm integration.

| Task | Details |
|------|---------|
| **1.1 HTTP-first dispatch** | Ensure `dispatch.py` reliably uses HTTP direct transport (`_forward_to_node()`) to Academic (:8200) and Experiment (:8300) as the primary path, with OpenClaw `node.invoke` as fallback. Currently both paths exist; make HTTP the default by always setting `DARKLAB_ACADEMIC_HOST`/`DARKLAB_EXPERIMENT_HOST` in the Docker environment. |
| **1.2 Health aggregation** | Extend `serve.py GET /health` to poll Academic/Experiment health endpoints and return a cluster-wide health object: `{leader: {status, uptime, tasks_today}, academic: {status, uptime, agents_available}, experiment: {status, uptime, gpu_load}}`. This becomes the heartbeat source for Paperclip. |
| **1.3 Structured logging** | Replace `print()` and `logging.info()` calls in all agents with structured JSON logs using `structlog`. Each log line carries `task_id`, `agent_name`, `event_type`, `timestamp`. This is the foundation for DRVP event emission. |
| **1.4 Config migration** | Move `shared/config.py` Settings to support both `.env` file and Paperclip secrets API (`GET /api/companies/:id/secrets`). Leader checks Paperclip first, falls back to `.env`. This lets Boss manage API keys from the Paperclip dashboard instead of SSH-ing into the Mac mini. |

### Stage 2: Swarm Integration (Week 3-5)

**Objective:** Replace the static routing table with a LangGraph swarm that dynamically hands off between agents.

| Task | Details |
|------|---------|
| **2.1 Install LangGraph Swarm** | Add `langgraph-swarm` as a dependency in `pyproject.toml`. The library provides `create_swarm()` and `create_handoff_tool()` — exactly matching the DarkLab pattern where Leader dispatches to Academic/Experiment. |
| **2.2 Wrap agents as LangGraph nodes** | Each existing agent handler (e.g., `academic.research.handle`) becomes a LangGraph node. The wrapper: (a) receives `SwarmState.messages`, (b) extracts the last `HumanMessage`, (c) calls the existing `handle(task)`, (d) appends the `TaskResult` as an `AIMessage`, (e) returns updated state. This preserves all existing agent logic while enabling handoff. |
| **2.3 Create handoff tools** | For each route in `ROUTING_TABLE`, create a handoff tool: `handoff_to_research = create_handoff_tool(agent_name="academic.research", description="Hand off to the Academic Research agent for literature search and research framework generation")`. The Leader LLM can now call these tools dynamically instead of relying on regex parsing. |
| **2.4 Smart dispatch** | Replace the regex-based command parser in `dispatch.py` with a two-tier strategy: (a) Fast path: if the message starts with a known slash command (`/research`, `/simulate`, etc.), directly invoke the corresponding handoff tool — no LLM call needed. (b) Smart path: for free-form text, the Leader LLM (Claude Opus) decides which handoff tool(s) to call based on the message content. This subsumes `plan_campaign()` — the LLM naturally produces a plan by calling handoff tools in sequence with `depends_on` relationships encoded in the swarm state. |
| **2.5 Multi-step campaigns** | For complex requests requiring multiple agents, the swarm state graph enables chained handoffs: Leader → Academic.research → Academic.doe → Experiment.simulation → Leader.synthesis. Each handoff preserves the conversation history in `SwarmState.messages`, so downstream agents have full context of what happened upstream. The `parent_task_id` field in `Task` links the steps for audit. |

### Stage 3: Memory and Context (Week 6-7)

**Objective:** Give the Leader persistent memory across research sessions using OpenViking.

| Task | Details |
|------|---------|
| **3.1 Deploy OpenViking** | Add OpenViking server (:1933) to the Leader's Docker Compose stack. Configure it as the OpenClaw memory plugin (replace or augment the existing `memory-lancedb` extension). Storage backend: SQLite + vector engine (`.dylib` included for macOS ARM64). |
| **3.2 Memory middleware** | Create `core/oas_core/middleware/memory.py` that wraps every agent call: before execution, load relevant context from `viking://research/{topic}/` at L1 (overview) level; after execution, store findings at L2 (full detail). This means if you research "quantum dots" today, the next research task about "EIT electrodes" automatically gets the quantum dots context if relevant. |
| **3.3 Research knowledge graph** | Use OpenViking's hierarchical structure to build a research knowledge graph: `viking://research/{topic}/{subtopic}/` with L0 (title + one-line summary), L1 (abstract + key findings), L2 (full data + citations + artifacts). The Leader's `synthesis.py` queries this graph when merging multi-source results, producing better cross-study connections. |
| **3.4 Session continuity** | When a user sends a follow-up message ("now simulate the top 3 candidates"), the Leader checks OpenViking for the recent research context, automatically loads the relevant `viking://research/` entries, and populates the swarm state with them. No need for the user to re-specify context. |

### Stage 4: Persona System (Week 8-9)

**Objective:** Load specialized personas from agency-agents to enhance agent behavior.

| Task | Details |
|------|---------|
| **4.1 Persona loader** | Create `core/oas_core/persona.py` that reads agent persona files from `frameworks/agency-agents/` and converts them into system prompt extensions. Each DarkLab agent gets a domain-appropriate persona layered on top of its existing system prompt. |
| **4.2 Role-persona mapping** | Map DarkLab agents to agency-agents personas: Academic.research → `academic-researcher.md`, Academic.literature → `academic-literature-reviewer.md`, Experiment.simulation → `engineering-ai-engineer.md` + `academic-data-scientist.md` (merged), Leader.synthesis → `strategy-business-analyst.md`. |
| **4.3 Dynamic persona selection** | For free-form requests, the Leader LLM can select the best persona from the library dynamically. Example: a user asks about firmware optimization → the Leader loads `engineering-embedded-firmware-engineer.md` (which covers ESP32/STM32/Nordic — directly relevant to the ADuCM350 work). |

### Stage 5: Advanced Orchestration (Week 10-12)

**Objective:** Full autonomous research campaigns with human-in-the-loop governance.

| Task | Details |
|------|---------|
| **5.1 Campaign engine** | Build a campaign manager in `leader/campaign.py` that maintains a persistent campaign state (stored in OpenViking): goal, steps, completed steps, current step, blockers. When a step requires approval, it creates a Paperclip approval request and pauses the campaign until Boss approves via the dashboard. |
| **5.2 Parallel execution** | When campaign steps have no dependencies, dispatch them concurrently using `asyncio.gather()`. Example: "Research material A" and "Research material B" run on Academic simultaneously while "Simulate baseline" runs on Experiment. The swarm state graph supports this via independent branches that merge at synthesis. |
| **5.3 Self-evaluation loop** | After each campaign step, the Leader evaluates the result quality using a separate LLM call (Claude Haiku for speed). If quality is below threshold, it either retries with modified parameters or hands off to a different agent. This prevents garbage-in-garbage-out cascades. |
| **5.4 Claude Code sub-agent** | Integrate the Claude Code Skill for code-heavy tasks: when a research step requires data analysis code, simulation scripting, or report generation that goes beyond the existing agents' capabilities, the Leader spawns a Claude Code session via the Claude Code Skill API (:18795). Results flow back into the swarm state. |
| **5.5 deepagents integration** | For truly complex, multi-file tasks that require the full "batteries-included" agent harness (filesystem access, sub-agent spawning, todo planning), the Leader delegates to a deepagents instance. This is configured as an additional LangGraph node in the swarm, connected via the deepagents `create_deep_agent()` API. |

---

## 6. Paperclip Governance Expansion

### 6.1 Current State

Paperclip is deployed at `:3100` with the "Opensens DarkLab" company (prefix DL), 4 agents (Boss, Leader, Academic, Experiment), and 2 goals. The system uses `authenticated` mode with `better-auth`. Budget tracking exists but is dual: file-locked JSON in `llm_client.py` (local) and `cost_events` table (Paperclip DB).

### 6.2 Unification: Single Source of Budget Truth

**Problem:** Currently, budget enforcement happens locally in `llm_client.py` via `_check_and_record_spend()` with `fcntl.LOCK_EX`, while Paperclip maintains a separate `cost_events` table. These can drift.

**Solution:** Make Paperclip the single source of truth:

1. **Agent-side**: After each LLM call, the agent POSTs to `POST /api/companies/:companyId/cost-events` with `{provider, model, inputTokens, outputTokens, costCents}`. The local spend JSON becomes a write-ahead cache (still file-locked for atomicity), but the authoritative check queries Paperclip's `GET /api/companies/:companyId/costs/summary`.

2. **Pre-call budget check**: Before making an LLM call, query Paperclip `GET /api/agents/:agentId` to read `spentMonthlyCents` vs `budgetMonthlyCents`. If at limit, raise `BudgetExhaustedError` immediately. Cache the result for 60 seconds to avoid hammering Paperclip on every call.

3. **Hard stop**: Paperclip's existing `auto-pause` feature (agent status → `paused` when budget exceeded) becomes the enforcement mechanism. When an agent is paused, `node_bridge.py` checks agent status before dispatching and returns an error `TaskResult` with `status="budget_exhausted"`.

### 6.3 Issue-Driven Research Workflow

Transform every research request into a Paperclip issue with full lifecycle tracking:

```
User request via Telegram
    → Leader creates issue: POST /api/companies/:companyId/issues
      {title: "Research: quantum dots for EIT", priority: "high",
       assigneeAgentId: academic_agent_id, goalId: research_goal_id}
    → Issue gets identifier: DL-47
    → Leader checks out issue: POST /api/issues/DL-47/checkout
    → heartbeat_run created (status: running)
    → Agent executes...
    → On completion: PATCH /api/issues/DL-47 {status: "done"}
    → heartbeat_run updated (status: done)
    → Artifacts attached: POST /api/issues/DL-47/attachments
```

**Benefits:**
- Every research task is traceable in the Paperclip Kanban board
- Boss can see all active/completed research from the dashboard
- Cost per research task is tracked (sum of `cost_events` linked to `issueId`)
- Comments and discussions per task via `POST /api/issues/:id/comments`

### 6.4 Approval Gates for Campaigns

When `dispatch.py`'s `plan_campaign()` generates a multi-step plan, instead of just returning `requires_approval: True`:

1. Create a Paperclip approval request: `POST /api/companies/:companyId/approvals {type: "campaign_plan", requestedByAgentId: leader_id, payload: {steps, estimated_cost, estimated_time}}`
2. Boss gets notified via Telegram (PicoClaw sends the plan summary)
3. Boss approves/rejects from the Paperclip dashboard or replies "approved" in Telegram
4. On approval: `POST /api/approvals/:id/resolve {status: "approved"}`
5. Leader wakes up, reads the approval status, and begins executing the campaign steps
6. Each step creates its own issue (with `parentId` linking to a parent campaign issue)

### 6.5 Goal Hierarchy for Research Programs

Structure DarkLab's research programs as a Paperclip goal tree:

```
Objective: "Advance EIT sensing technology" (level: objective)
  ├── Milestone: "Electrode material optimization" (level: milestone)
  │   ├── Task: "Literature review: quantum dot electrodes" (level: task, → DL-47)
  │   ├── Task: "DOE: QD synthesis parameters" (level: task, → DL-48)
  │   └── Task: "Simulation: QD-EIT impedance model" (level: task, → DL-49)
  │
  ├── Milestone: "Firmware V2 bring-up" (level: milestone)
  │   ├── Task: "ADuCM350 register configuration" (level: task)
  │   └── Task: "EIT measurement validation" (level: task)
  │
  └── Milestone: "iOS app EIT reconstruction" (level: milestone)
      ├── Task: "BackProjection algorithm validation" (level: task)
      └── Task: "Real-time heatmap rendering" (level: task)
```

Created via `POST /api/companies/:companyId/goals` with `parentId` for nesting.

### 6.6 New Paperclip Adapter: OAS Swarm

Create a new adapter type `adapter-oas-swarm` in `paperclip/packages/adapters/` that:

1. Connects to the OAS Core swarm (not directly to OpenClaw)
2. Translates Paperclip issue checkout → OAS Task → LangGraph swarm invocation
3. Streams heartbeat events back to Paperclip during execution
4. Reports cost events from the middleware pipeline
5. Attaches artifacts on completion

This adapter replaces the current `adapter-openclaw-gateway` with a richer integration that understands the swarm's multi-step, multi-agent nature.

---

## 7. Agent Office ↔ Paperclip Integration

### 7.1 Current Disconnect

Agent Office connects to OpenClaw via WebSocket at `:18789` and renders agent status in a 2D/3D floor plan. Paperclip runs independently at `:3100` with its own UI. There is no cross-communication.

### 7.2 Integration Architecture

```
Agent Office (React, :5180)
    │
    ├── WS to OpenClaw (:18789)          [existing — agent events]
    │
    ├── WS to Paperclip (:3100)          [NEW — governance events]
    │   ws://192.168.23.25:3100/api/companies/:companyId/events/ws
    │
    └── REST to Paperclip (:3100)        [NEW — data queries]
        GET /api/companies/:companyId/dashboard
        GET /api/companies/:companyId/issues
        GET /api/companies/:companyId/costs/summary
        GET /api/companies/:companyId/costs/by-agent
        GET /api/agents/:agentId
        GET /api/heartbeat-runs/:runId/issues
```

### 7.3 New Agent Office Components

#### 7.3.1 Paperclip Gateway Adapter

Create `office/src/paperclip/paperclip-adapter.ts`:

```typescript
interface PaperclipAdapter {
  // Auth
  connect(url: string, apiKey: string): Promise<void>;
  disconnect(): void;

  // Dashboard
  getDashboard(): Promise<DashboardData>;

  // Issues
  getIssues(filters?: IssueFilters): Promise<Issue[]>;
  getIssue(id: string): Promise<Issue>;

  // Costs
  getCostSummary(from: Date, to: Date): Promise<CostSummary>;
  getCostsByAgent(): Promise<AgentCost[]>;

  // Agents
  getAgents(): Promise<PaperclipAgent[]>;
  getAgentRuns(agentId: string): Promise<HeartbeatRun[]>;

  // Real-time
  onLiveEvent(handler: (event: LiveEvent) => void): void;
}
```

This adapter connects to Paperclip's WebSocket endpoint for live events and uses REST for data queries. It authenticates with an agent API key (created in Paperclip for the "Agent Office" service).

#### 7.3.2 PaperclipPanel Component

A new panel in the Agent Office metrics area showing:

- **Budget gauges**: Circular progress meters for each agent (spent/budget), colored green→yellow→red. Data from `GET /costs/by-agent`. Updates on `cost_event.created` WS events.
- **Active issues**: List of in-progress issues with agent avatar, issue identifier (DL-47), title, and time elapsed. Data from `GET /issues?status=in_progress`.
- **Pending approvals count**: Badge showing number of pending approvals. Links to Paperclip approval page.
- **Cost trend**: Small sparkline showing daily cost trend (last 7 days). Data from `GET /costs/summary`.

#### 7.3.3 TaskBadge Overlay

When an agent is working on a Paperclip issue, its avatar in the 2D/3D floor plan shows a small badge with the issue identifier (e.g., "DL-47"). Implementation:

- On `heartbeat_run.started` WS event from Paperclip, query `GET /heartbeat-runs/:runId/issues` to get the linked issue
- Store `{agentId → issueIdentifier}` in the Zustand store
- Render as a small rounded rectangle above the SpeechBubble component
- Click opens the Paperclip issue detail page in a new tab

#### 7.3.4 RequestFlowGraph Component

A new page (`/request/:requestId`) showing a live DAG (directed acyclic graph) of the current request flow:

```
[User Request]
      │
      ▼
[DL-47: Research QD]  ─status: done, 45s, $0.05──►  [DL-48: DOE QD params]
      │                                                       │
      │                                                       ▼
      └──────────────────────────────────── [DL-49: Simulate QD-EIT]
                                                       │
                                                       ▼
                                              [DL-50: Synthesis]
                                                  status: running
```

Each node shows:
- Issue identifier and title
- Agent avatar (who's working on it)
- Status (pending/running/done) with color coding
- Duration and cost
- Animated pulsing border when running

Data source: Paperclip issues with `parentId` linking + `heartbeat_runs` status. Updated in real-time via WS events.

#### 7.3.5 Unified Event Stream

Merge OpenClaw agent events and Paperclip live events into a single `EventTimeline` component:

```typescript
// In office-store.ts, add:
paperclipEvents: LiveEvent[];
mergedTimeline: TimelineEvent[]; // union of OpenClaw + Paperclip events

// TimelineEvent:
type TimelineEvent = {
  timestamp: Date;
  source: "openclaw" | "paperclip";
  type: string;
  agentName: string;
  summary: string;
  metadata: Record<string, unknown>;
};
```

The timeline shows interleaved events: "Academic started research task" (OpenClaw), "DL-47 checked out by Academic" (Paperclip), "Perplexity API called, $0.002" (OpenClaw), "Cost event recorded" (Paperclip), etc.

---

## 8. Dynamic Request Visualization Protocol (DRVP)

### 8.1 Purpose

DRVP is a lightweight event protocol that enables any OAS request to be visualized in real-time on both Agent Office and Paperclip. It defines a standard set of events emitted by the OAS Core middleware pipeline, consumed by both frontends.

### 8.2 Event Schema

```python
# core/oas_core/protocols/drvp.py

from pydantic import BaseModel
from enum import Enum
from datetime import datetime
from typing import Any

class DRVPEventType(str, Enum):
    # Request lifecycle
    REQUEST_CREATED = "request.created"
    REQUEST_ROUTED = "request.routed"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"

    # Agent lifecycle
    AGENT_ACTIVATED = "agent.activated"
    AGENT_THINKING = "agent.thinking"
    AGENT_SPEAKING = "agent.speaking"
    AGENT_IDLE = "agent.idle"
    AGENT_ERROR = "agent.error"

    # Handoff
    HANDOFF_STARTED = "handoff.started"
    HANDOFF_COMPLETED = "handoff.completed"

    # Tool usage
    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_COMPLETED = "tool.call.completed"
    TOOL_CALL_FAILED = "tool.call.failed"

    # LLM calls
    LLM_CALL_STARTED = "llm.call.started"
    LLM_CALL_COMPLETED = "llm.call.completed"
    LLM_STREAM_TOKEN = "llm.stream.token"

    # Memory
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"

    # Budget
    BUDGET_CHECK = "budget.check"
    BUDGET_WARNING = "budget.warning"
    BUDGET_EXHAUSTED = "budget.exhausted"

    # Campaign
    CAMPAIGN_STEP_STARTED = "campaign.step.started"
    CAMPAIGN_STEP_COMPLETED = "campaign.step.completed"
    CAMPAIGN_APPROVAL_REQUIRED = "campaign.approval.required"
    CAMPAIGN_APPROVED = "campaign.approved"

class DRVPEvent(BaseModel):
    event_id: str                    # UUID
    event_type: DRVPEventType
    timestamp: datetime
    request_id: str                  # Groups all events for one request
    task_id: str | None = None       # DarkLab task ID
    issue_id: str | None = None      # Paperclip issue identifier (e.g., "DL-47")
    agent_name: str                  # Which agent emitted this
    device: str                      # "leader" | "academic" | "experiment"
    payload: dict[str, Any] = {}     # Event-specific data
    parent_event_id: str | None = None  # For nested events (tool inside LLM call)
```

### 8.3 Event Payloads by Type

```python
# REQUEST_CREATED
payload = {
    "source": "telegram" | "api" | "paperclip" | "campaign",
    "user_id": "steve@opensens.io",
    "text": "Research quantum dots for EIT electrodes",
    "estimated_steps": 3,
}

# HANDOFF_STARTED
payload = {
    "from_agent": "leader.dispatch",
    "to_agent": "academic.research",
    "reason": "User requested research task",
    "context_size_tokens": 1500,
}

# LLM_CALL_STARTED
payload = {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "input_tokens": 2400,
    "purpose": "Generate research framework",
}

# LLM_CALL_COMPLETED
payload = {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "input_tokens": 2400,
    "output_tokens": 1800,
    "cost_usd": 0.034,
    "duration_ms": 3200,
}

# TOOL_CALL_STARTED
payload = {
    "tool_name": "perplexity_search",
    "arguments": {"query": "quantum dot electrode EIT impedance"},
}

# BUDGET_WARNING
payload = {
    "agent_name": "DarkLab Academic",
    "spent_today_usd": 27.50,
    "daily_limit_usd": 30.00,
    "utilization_percent": 91.7,
}

# CAMPAIGN_STEP_COMPLETED
payload = {
    "step_number": 2,
    "total_steps": 5,
    "step_title": "Literature review complete",
    "artifacts": ["synthesis_abc123.json"],
    "quality_score": 0.87,
}
```

### 8.4 Transport

DRVP events are published to **two channels** simultaneously:

1. **Redis Pub/Sub** (channel: `drvp:{company_id}`): For intra-cluster real-time distribution. Agent Office subscribes via a thin WebSocket relay (a new 50-line Express middleware added to the Agent Office server). Paperclip subscribes via its existing `publishLiveEvent()` system — a new listener maps DRVP events to `LiveEventType` values.

2. **Paperclip REST API**: Every DRVP event is also persisted as an `activity_log` entry via `POST /api/companies/:companyId/activity` (or a new dedicated endpoint `POST /api/companies/:companyId/drvp-events`). This ensures the full request flow is auditable and queryable after the fact.

### 8.5 Emission Points

DRVP events are emitted by the OAS Core middleware pipeline:

```python
# core/oas_core/middleware/budget.py
class BudgetMiddleware:
    async def __call__(self, task, next_handler):
        emit(DRVPEvent(event_type=BUDGET_CHECK, ...))
        if over_budget:
            emit(DRVPEvent(event_type=BUDGET_EXHAUSTED, ...))
            raise BudgetExhaustedError()
        result = await next_handler(task)
        return result

# core/oas_core/protocols/drvp.py
async def emit(event: DRVPEvent):
    # Publish to Redis
    await redis.publish(f"drvp:{company_id}", event.model_dump_json())
    # Post to Paperclip
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{paperclip_url}/api/companies/{company_id}/drvp-events",
            json=event.model_dump(),
            headers={"Authorization": f"Bearer {agent_api_key}"},
        )
```

### 8.6 Consumption in Agent Office

```typescript
// office/src/drvp/drvp-consumer.ts

class DRVPConsumer {
  private ws: WebSocket;

  connect(redisRelayUrl: string) {
    this.ws = new WebSocket(redisRelayUrl);
    this.ws.onmessage = (msg) => {
      const event: DRVPEvent = JSON.parse(msg.data);
      this.dispatch(event);
    };
  }

  dispatch(event: DRVPEvent) {
    const store = useOfficeStore.getState();

    switch (event.event_type) {
      case "request.created":
        store.addRequest(event.request_id, event.payload);
        break;
      case "agent.activated":
        store.setAgentStatus(event.agent_name, "working");
        break;
      case "handoff.started":
        store.animateHandoff(event.payload.from_agent, event.payload.to_agent);
        break;
      case "llm.stream.token":
        store.appendSpeechBubble(event.agent_name, event.payload.token);
        break;
      case "tool.call.started":
        store.showToolPanel(event.agent_name, event.payload.tool_name);
        break;
      case "budget.warning":
        store.flashBudgetGauge(event.agent_name, "warning");
        break;
      case "campaign.step.completed":
        store.updateRequestFlow(event.request_id, event.payload);
        break;
      case "request.completed":
        store.setAgentStatus(event.agent_name, "idle");
        store.markRequestDone(event.request_id);
        break;
    }
  }
}
```

### 8.7 Consumption in Paperclip

A new Paperclip service `drvp-bridge.ts` subscribes to the Redis `drvp:*` channels and:

1. Maps `REQUEST_CREATED` → auto-create Paperclip issue (if not already created by the Leader)
2. Maps `LLM_CALL_COMPLETED` → auto-create `cost_event` entry
3. Maps `CAMPAIGN_APPROVAL_REQUIRED` → auto-create Paperclip approval request
4. Maps `REQUEST_COMPLETED` → update issue status to `done`
5. All events → publish as Paperclip `LiveEvent` on the company WS channel

This means the Paperclip dashboard updates in real-time without any changes to the Paperclip UI code — the existing `LiveRunWidget`, `ActiveAgentsPanel`, and `ActivityCharts` components automatically render the new events.

---

## 9. Implementation Phases

### Phase 1: Merge & Foundation (Weeks 1-3)

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 1 | Create OAS folder structure, move darklab-installer → cluster/ | P0 | 1 day |
| 2 | Move frameworks to frameworks/ | P0 | 0.5 day |
| 3 | Create core/ Python package with empty module structure | P0 | 0.5 day |
| 4 | Update Docker Compose paths | P0 | 1 day |
| 5 | Leader Stage 1: health aggregation, structured logging | P0 | 3 days |
| 6 | Leader Stage 1: config migration (Paperclip secrets) | P1 | 2 days |
| 7 | Budget unification (Paperclip as SSOT) | P1 | 3 days |
| 8 | Update CLAUDE.md and all documentation | P0 | 1 day |
| 9 | Verify all 56 tests still pass | P0 | 0.5 day |

**Deliverable:** OAS folder exists, all existing functionality preserved, structured logging in place.

### Phase 2: Swarm & Governance (Weeks 4-6)

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 10 | Leader Stage 2: LangGraph Swarm integration | P0 | 5 days |
| 11 | Wrap all 14 agents as LangGraph nodes | P0 | 3 days |
| 12 | Smart dispatch (slash command fast path + LLM smart path) | P0 | 3 days |
| 13 | Issue-driven research workflow in Paperclip | P1 | 3 days |
| 14 | Approval gates for campaigns | P1 | 2 days |
| 15 | DRVP protocol implementation (core/oas_core/protocols/) | P0 | 3 days |
| 16 | Redis Pub/Sub DRVP transport | P0 | 1 day |
| 17 | DRVP emission in middleware pipeline | P0 | 2 days |

**Deliverable:** Dynamic swarm routing works, every request emits DRVP events, campaigns go through Paperclip approval.

### Phase 3: Visualization (Weeks 7-9)

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 18 | Agent Office: Paperclip WebSocket adapter | P0 | 2 days |
| 19 | Agent Office: DRVP consumer | P0 | 2 days |
| 20 | Agent Office: PaperclipPanel (budget gauges, active issues) | P1 | 3 days |
| 21 | Agent Office: TaskBadge overlay on agent avatars | P1 | 1 day |
| 22 | Agent Office: RequestFlowGraph (live DAG) | P1 | 4 days |
| 23 | Agent Office: Unified event timeline | P2 | 2 days |
| 24 | Paperclip: DRVP bridge service | P0 | 2 days |
| 25 | Paperclip: Auto-issue creation from DRVP events | P1 | 2 days |

**Deliverable:** Full visual pipeline — request flows visible in both Agent Office (floor plan + DAG) and Paperclip (dashboard + Kanban + costs).

### Phase 4: Memory & Personas (Weeks 10-12)

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 26 | Deploy OpenViking to Docker stack | P1 | 2 days |
| 27 | Leader Stage 3: memory middleware | P1 | 3 days |
| 28 | Research knowledge graph structure | P2 | 3 days |
| 29 | Session continuity (follow-up context loading) | P2 | 2 days |
| 30 | Leader Stage 4: persona loader | P2 | 2 days |
| 31 | Role-persona mapping for all agents | P2 | 1 day |
| 32 | Goal hierarchy for research programs | P2 | 2 days |

**Deliverable:** Agents remember past research, use specialized personas, research programs tracked as Paperclip goal trees.

### Phase 5: Advanced Orchestration (Weeks 13-16)

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 33 | Leader Stage 5: campaign engine | P1 | 5 days |
| 34 | Parallel campaign step execution | P1 | 3 days |
| 35 | Self-evaluation loop | P2 | 3 days |
| 36 | Claude Code sub-agent integration | P2 | 3 days |
| 37 | deepagents integration for complex tasks | P3 | 3 days |
| 38 | NemoClaw sandboxing for untrusted code execution | P3 | 3 days |
| 39 | OAS adapter for Paperclip | P1 | 3 days |
| 40 | End-to-end testing: full campaign with visualization | P0 | 3 days |

**Deliverable:** Full autonomous research campaigns with parallel execution, quality control, governed by Paperclip, visualized in Agent Office.

---

## 10. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| **LangGraph Swarm breaks existing routing** | High | Dual-mode dispatch: slash commands use fast path (no LLM), free-form uses swarm. Existing `ROUTING_TABLE` preserved as fallback. |
| **OpenViking build complexity** (Rust+Go+C++) | Medium | Use Python-only mode initially (skip AGFS Go binary, use SQLite backend). Full native build deferred to Phase 4. |
| **DRVP event flood** | Medium | Rate-limit `LLM_STREAM_TOKEN` events to 1/100ms. Batch `TOOL_CALL_*` events for rapid tool sequences. Redis TTL on DRVP channel: 300s. |
| **Budget drift between local and Paperclip** | High | Local file-locked JSON becomes write-ahead log only. Paperclip is authoritative. Reconciliation script runs hourly. |
| **Docker Compose path changes break deployment** | High | Symlinks for backward compatibility. CI test that verifies all Docker services start correctly after restructure. |
| **Agent Office perf with dual WebSocket** | Medium | Throttle Paperclip WS events to 5/second max. Use `requestAnimationFrame` for DOM updates. Batch Zustand store mutations. |

---

## Appendix A: Key File Paths (Post-Merge)

```
Opensens Agent Swarm/
├── core/oas_core/swarm.py               # LangGraph Swarm builder
├── core/oas_core/protocols/drvp.py      # DRVP event schema + emitter
├── core/oas_core/middleware/budget.py    # Paperclip-aware budget middleware
├── core/oas_core/middleware/memory.py    # OpenViking memory middleware
├── core/oas_core/adapters/paperclip.py  # Paperclip REST/WS client
├── cluster/agents/leader/dispatch.py    # Smart dispatch (swarm + fast path)
├── cluster/agents/leader/campaign.py    # Campaign engine (new)
├── cluster/agents/leader/serve.py       # FastAPI server (:8100)
├── cluster/agents/shared/llm_client.py  # LLM calls with DRVP emission
├── office/src/paperclip/adapter.ts      # Paperclip adapter for Agent Office
├── office/src/drvp/consumer.ts          # DRVP event consumer
├── office/src/components/panels/PaperclipPanel.tsx
├── office/src/components/panels/RequestFlowGraph.tsx
├── paperclip/server/src/services/drvp-bridge.ts  # DRVP → Paperclip events
```

## Appendix B: New Docker Services (Post-Merge)

Added to `~/darklab/docker-compose.yml`:

| Service | Port | Image | Purpose |
|---------|------|-------|---------|
| OpenViking | 1933 | `./frameworks/openviking` | Context memory server |
| DRVP Relay | 18800 | `./core` | Redis→WS bridge for Agent Office |

Total services: 13 existing + 2 new = **15 services**.

## Appendix C: Dependency Versions

| Package | Version | Purpose |
|---------|---------|---------|
| `langgraph` | >=1.0 | State graph framework |
| `langgraph-swarm` | >=0.1.0 | Multi-agent handoff |
| `langchain-anthropic` | >=0.3 | Claude LLM binding for swarm |
| `openviking` | >=0.1.0 | Context memory (installed from local) |
| `structlog` | >=24.0 | Structured JSON logging |
| `redis[hiredis]` | >=5.0 | DRVP Pub/Sub transport |
| `httpx` | >=0.27 | Async HTTP (Paperclip API calls) |
| `pydantic` | >=2.0 | Data models (existing) |
