# OAS Development Plan v2 — From Platform to Control Plane

> **Version:** 2.0
> **Date:** 2026-03-29
> **Baseline:** 88 tasks complete, 581 tests, 19 phases shipped
> **Strategic frame:** `roadmap_oas.md` — OAS as the Darklab control plane

---

## Where We Are

OAS has crossed the prototype-to-platform threshold. The foundation is solid:

| Capability | Status | Evidence |
|------------|--------|----------|
| Dispatch routing | Production | 25 slash commands, dual-mode (command + swarm) |
| Budget enforcement | Production | File-locked spend, Paperclip pre-check, daily limits |
| DRVP event streaming | Production | 25 event types, Redis Pub/Sub, SSE, Office consumers |
| Memory (OpenViking) | Production | L0/L1/L2 tiered, session continuity, semantic search |
| Campaign engine | Production | DAG execution, parallel steps, governance gates |
| RL self-evolution | Integrated | Rollout collector, training pipeline, promotion gate |
| Deep research | Integrated | 9 academic sources, iterative convergence, knowledge base |
| TurboQuant | Integrated | PolarQuant + QJL + Middle-Out, memory pool, ~12k tokens/agent |
| Office visualization | Production | 2D/3D floor plan, 17 Zustand stores, console pages |
| Paperclip governance | Production | 37 tables, issues, approvals, costs, org chart |
| Security | Hardened | Ed25519 signing, domain allowlist, code review (63 findings fixed) |
| Tests | 581 passing | 403 core + 150 cluster + 28 office, 0 failures |

**What's missing is not more features — it's formalization, contracts, and operational maturity.**

The roadmap (`roadmap_oas.md`) defines six strategic phases. Below is the concrete development plan to execute them, mapped against what already exists.

---

## Phase OAS-1 — Stabilization and Contract Hardening
**Timeline:** Weeks 1–8 | **Priority:** Critical

### Why first
Everything downstream depends on stable contracts. Modules can't register themselves, campaigns can't be replayed, and costs can't be attributed if the schemas drift.

### 1.1 Campaign Schema Registry
**Goal:** One canonical schema for campaign objects across all modules.

| Task | Description | Est. |
|------|-------------|------|
| 1.1.1 | Extract `CampaignSchema` from `campaign.py` into `core/oas_core/schemas/campaign.py` — Pydantic v2 model with versioned `schema_version` field | 1d |
| 1.1.2 | Add `CampaignStep` schema with typed inputs/outputs, cost fields, provenance ID | 1d |
| 1.1.3 | Create schema registry (`core/oas_core/schemas/registry.py`) — register/validate/version schemas at startup | 2d |
| 1.1.4 | Migrate existing campaign code to use registered schemas | 2d |
| 1.1.5 | Add schema validation tests (forward/backward compat) | 1d |

### 1.2 Module Adapter Interface
**Goal:** Standardized interface for Parallax / OAE / OPAD / DAMD to register as routable capabilities.

| Task | Description | Est. |
|------|-------------|------|
| 1.2.1 | Define `ModuleCapability` protocol: `name`, `supported_task_types`, `health()`, `execute(task)`, `estimate_cost(task)` | 1d |
| 1.2.2 | Create `ModuleRegistry` in `core/oas_core/registry/` — dynamic registration, capability discovery, health tracking | 2d |
| 1.2.3 | Refactor existing adapters (Paperclip, OpenClaw, DeerFlow) to implement `ModuleCapability` | 2d |
| 1.2.4 | Add capability-based routing in `dispatch.py` — modules self-declare what they can handle | 2d |
| 1.2.5 | Stub adapters for Parallax, OAE, OPAD, DAMD with interface compliance tests | 1d |

### 1.3 Contract Tests
**Goal:** Formalized tests for every inter-module boundary.

| Task | Description | Est. |
|------|-------------|------|
| 1.3.1 | Handoff contract tests — verify task shape in/out across all handoff pairs | 2d |
| 1.3.2 | Campaign transition tests — valid state machine transitions (pending→approved→running→done/failed) | 1d |
| 1.3.3 | DRVP event emission tests — every middleware stage emits correct events with correct payload shapes | 2d |
| 1.3.4 | Budget/approval rule tests — exhaustion blocks, approval gates open/close correctly | 1d |

### 1.4 Cost Ledger Enhancement
**Goal:** Real token + compute attribution per campaign, per step, per model.

| Task | Description | Est. |
|------|-------------|------|
| 1.4.1 | Add `CostAttribution` model: `campaign_id`, `step_id`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms` | 1d |
| 1.4.2 | Wire cost attribution into `llm.call.completed` DRVP events | 1d |
| 1.4.3 | Aggregate cost per campaign in Paperclip (`/api/campaigns/{id}/costs`) | 2d |
| 1.4.4 | Office cost-per-campaign panel in `CostPieChart` | 1d |

### 1.5 Session Recovery
**Goal:** Interrupted campaigns can be resumed safely.

| Task | Description | Est. |
|------|-------------|------|
| 1.5.1 | Persist campaign state to Redis (or JSONL fallback) after each step completion | 2d |
| 1.5.2 | Add `resume_campaign(campaign_id)` to `CampaignEngine` — skip completed steps, restart from last incomplete | 2d |
| 1.5.3 | `/resume <campaign_id>` dispatch command | 1d |
| 1.5.4 | Resume integration tests (kill mid-step, verify restart) | 1d |

### OAS-1 Success Criteria
- [ ] Any downstream module can register itself via `ModuleCapability` protocol
- [ ] Campaign schemas are versioned and validated at creation
- [ ] Cost is visible per campaign, per step, per model
- [ ] Interrupted campaigns resume from last checkpoint
- [ ] 40+ new contract tests

**Estimated effort:** ~30 developer-days

---

## Phase OAS-2 — Darklab Protocol Hub
**Timeline:** Months 2–4 | **Priority:** High

### Why now
OAS needs to own the vocabulary. Without shared intent packages, each module reinvents its own task format.

### 2.1 Intent & Artifact Schemas

| Schema | Purpose | Fields |
|--------|---------|--------|
| **Research Intent Package (RIP)** | Describes a research objective | `objective`, `constraints`, `budget_limit`, `deadline`, `evidence_requirements`, `priority` |
| **Knowledge Artifact (KA)** | Output of research/analysis | `findings`, `sources[]`, `confidence`, `evidence_type`, `provenance_id`, `campaign_id` |
| **Simulation Intent Package (SIP)** | Describes a simulation task | `model_spec`, `parameters`, `validation_criteria`, `compute_budget` |
| **Experiment Intent Package (EIP)** | Describes a physical experiment | `protocol`, `materials`, `safety_requirements`, `approval_required` |
| **Run Record (RR)** | Output of simulation/experiment | `results`, `metrics`, `artifacts[]`, `duration`, `compute_used` |
| **Compute Request/Receipt** | Resource allocation contract | `requested_resources`, `allocated_resources`, `start_time`, `end_time`, `cost` |

| Task | Description | Est. |
|------|-------------|------|
| 2.1.1 | Define all 6 schemas in `core/oas_core/schemas/intents.py` as Pydantic v2 models | 3d |
| 2.1.2 | Schema versioning policy: semver in `schema_version`, backward-compat validation | 1d |
| 2.1.3 | Wire RIP into `/research`, `/deepresearch`, `/deerflow`, `/swarmresearch` commands | 2d |
| 2.1.4 | Wire KA into knowledge base output (replace ad-hoc dicts) | 2d |
| 2.1.5 | Wire SIP/EIP into `/simulate`, `/doe` commands | 2d |

### 2.2 Campaign State Machine v1

| Task | Description | Est. |
|------|-------------|------|
| 2.2.1 | Formal state machine: `DRAFT → PENDING_APPROVAL → APPROVED → RUNNING → PAUSED → COMPLETED / FAILED / CANCELLED` | 2d |
| 2.2.2 | Transition guards (only valid transitions allowed, with reasons) | 1d |
| 2.2.3 | State persistence in Redis + Paperclip issue sync | 2d |
| 2.2.4 | Campaign replay: reconstruct execution from stored events | 3d |

### 2.3 Event Normalization Layer

| Task | Description | Est. |
|------|-------------|------|
| 2.3.1 | `EventNormalizer` — converts all module events to `UnifiedEvent` with stable campaign/step IDs | 2d |
| 2.3.2 | Per-campaign provenance graph (DAG of events linked by `campaign_id` + `step_id`) | 3d |
| 2.3.3 | Evidence scoring fields on campaign records (`confidence`, `evidence_strength`, `source_count`) | 1d |

### OAS-2 Success Criteria
- [ ] OAS tracks one campaign across multiple modules with stable IDs
- [ ] Artifacts are queryable by campaign, stage, and evidence type
- [ ] Campaign replay from stored events produces consistent output
- [ ] All research/simulation/experiment commands use typed intent packages

**Estimated effort:** ~25 developer-days

---

## Phase OAS-3 — Campaign Intelligence and Decision Engine
**Timeline:** Months 4–7 | **Priority:** High

### Why now
OAS currently routes based on explicit commands or simple swarm routing. The next level: OAS recommends the next step based on evidence quality, cost, and risk.

### 3.1 Readiness Scoring

| Readiness Type | Inputs | Output |
|----------------|--------|--------|
| Knowledge Readiness | source count, confidence, coverage gaps, contradiction rate | 0.0–1.0 score + gap list |
| Simulation Readiness | model availability, parameter completeness, validation baseline | 0.0–1.0 score + missing items |
| Experiment Readiness | protocol completeness, material availability, safety approval | 0.0–1.0 score + blockers |
| Infrastructure Readiness | compute availability, budget remaining, node health | 0.0–1.0 score + constraints |

| Task | Description | Est. |
|------|-------------|------|
| 3.1.1 | `ReadinessScorer` in `core/oas_core/intelligence/readiness.py` — calculates all 4 readiness types | 3d |
| 3.1.2 | Knowledge readiness: leverage existing 5-metric convergence evaluator from deep research | 1d |
| 3.1.3 | Infrastructure readiness: query module registry health + budget middleware | 1d |
| 3.1.4 | Readiness dashboard panel in Office | 2d |

### 3.2 Decision Policy Engine

| Task | Description | Est. |
|------|-------------|------|
| 3.2.1 | `DecisionEngine` in `core/oas_core/intelligence/decision.py` — rule-based policy for next-step recommendation | 3d |
| 3.2.2 | Decision heuristics: stay-in-Parallax / move-to-OAE / move-to-OPAD / escalate-to-human | 2d |
| 3.2.3 | Cost-aware routing: integrate `estimate_cost()` from module registry into decision | 1d |
| 3.2.4 | Uncertainty routing: high-uncertainty → more research; low-uncertainty → proceed to simulation | 2d |
| 3.2.5 | Stop conditions: "insufficient evidence" path that halts campaign with explanation | 1d |
| 3.2.6 | Campaign reflection layer: post-step analysis that adjusts remaining plan | 2d |

### 3.3 Explainable Routing

| Task | Description | Est. |
|------|-------------|------|
| 3.3.1 | Decision audit trail: every routing decision logged with reasons, readiness scores, alternatives considered | 2d |
| 3.3.2 | `/explain <campaign_id>` command — shows decision history for a campaign | 1d |
| 3.3.3 | Decision checkpoint UI in Office (user sees recommendation before execution) | 2d |

### OAS-3 Success Criteria
- [ ] OAS can explain why it routed a campaign to a specific module
- [ ] Cost per campaign reduced via better stage selection (measurable A/B)
- [ ] Users see decision checkpoints, not black-box routing
- [ ] Campaigns stop when evidence is insufficient (no wasted compute)

**Estimated effort:** ~23 developer-days

---

## Phase OAS-4 — Governance, Memory, and Audit Maturity
**Timeline:** Months 7–12 | **Priority:** Medium-High

### 4.1 Three-Layer Memory

Upgrade from single OpenViking tier to structured memory:

| Layer | Purpose | Storage | Retention |
|-------|---------|---------|-----------|
| **Episodic** | Raw conversation/task history | OpenViking L0 (existing) | 30 days |
| **Semantic** | Extracted facts, entities, relationships | Knowledge base (existing JSONL → upgrade to structured store) | Permanent |
| **Reflective** | Lessons learned, meta-patterns, strategy adjustments | New `reflections.jsonl` with campaign linkage | Permanent |

| Task | Description | Est. |
|------|-------------|------|
| 4.1.1 | Formalize episodic/semantic/reflective separation in `memory.py` | 2d |
| 4.1.2 | Reflective memory: auto-extract lessons after campaign completion | 3d |
| 4.1.3 | Memory contamination guard: reflective memory tagged with provenance, never injected as "evidence" | 2d |
| 4.1.4 | Cross-campaign memory search: find relevant lessons from past campaigns | 1d |

### 4.2 Approval Policy Engine

| Task | Description | Est. |
|------|-------------|------|
| 4.2.1 | Policy rules DSL: define approval requirements by cost threshold, task type, risk level | 3d |
| 4.2.2 | Digital signature on approvals (Ed25519, reuse existing crypto) | 1d |
| 4.2.3 | Approval delegation: CEO can pre-approve categories below threshold | 2d |
| 4.2.4 | Approval audit export: per-campaign bundle with all approvals, overrides, and reasons | 2d |

### 4.3 Artifact Provenance

| Task | Description | Est. |
|------|-------------|------|
| 4.3.1 | Artifact lineage graph: link every output to its input campaign steps | 3d |
| 4.3.2 | Authorship model: human vs. AI attribution on every artifact | 1d |
| 4.3.3 | Audit export bundle: JSON + PDF for a complete campaign with all artifacts, events, approvals, costs | 3d |
| 4.3.4 | Campaign journal: persistent narrative log of what happened and why | 2d |

### 4.4 Alerting & Intervention

| Task | Description | Est. |
|------|-------------|------|
| 4.4.1 | Intervention queue: human review tasks triggered by budget warnings, low-confidence results, safety flags | 2d |
| 4.4.2 | Telegram alert integration (reuse PicoClaw channel) for critical interventions | 1d |
| 4.4.3 | Intervention UI panel in Office console | 2d |

### OAS-4 Success Criteria
- [ ] Any completed campaign can be audited with full provenance
- [ ] Reflective memory improves future campaigns without contaminating evidence
- [ ] Approvals and overrides are preserved as first-class signed records
- [ ] Critical events trigger human alerts within 60 seconds

**Estimated effort:** ~30 developer-days

---

## Phase OAS-5 — Multi-Node and Multi-Site Orchestration
**Timeline:** Months 12–18 | **Priority:** Medium

### Why this matters
The Mac mini cluster already has 3 nodes (Leader, Academic, Experiment). But dispatch is static — the Leader hardcodes which node handles which task. True multi-site means dynamic scheduling based on capacity, health, and data locality.

### 5.1 Resource-Aware Scheduler

| Task | Description | Est. |
|------|-------------|------|
| 5.1.1 | Node capability model: each node declares its available skills, compute, memory, GPU | 2d |
| 5.1.2 | `ResourceScheduler` in `core/oas_core/scheduler/` — matches tasks to nodes by capability + availability | 3d |
| 5.1.3 | Health heartbeat: nodes report status every 30s, scheduler marks unhealthy after 3 misses | 2d |
| 5.1.4 | Priority queue: campaigns ordered by priority, deadline, cost-efficiency | 2d |

### 5.2 Failure Isolation

| Task | Description | Est. |
|------|-------------|------|
| 5.2.1 | Node lease model: tasks assigned with lease duration, auto-reassigned on expiry | 2d |
| 5.2.2 | Partial failure handling: campaign continues on remaining nodes, skips unavailable steps | 2d |
| 5.2.3 | Degraded-mode execution: run with reduced capability when nodes are down | 2d |
| 5.2.4 | Circuit breaker per node (reuse RL circuit breaker pattern) | 1d |

### 5.3 Site-Aware Routing

| Task | Description | Est. |
|------|-------------|------|
| 5.3.1 | Data locality: prefer node that already has the relevant data/model loaded | 2d |
| 5.3.2 | Compute affinity: GPU tasks → GPU nodes, memory-heavy → high-RAM nodes | 1d |
| 5.3.3 | Local-first policy: prefer local cluster before remote compute | 1d |
| 5.3.4 | Multi-site dashboard panel in Office | 3d |

### OAS-5 Success Criteria
- [ ] Campaigns run across multiple nodes without manual routing
- [ ] Single node failure doesn't collapse the workflow
- [ ] Scheduling respects both capability and governance constraints
- [ ] Node health visible in real-time dashboard

**Estimated effort:** ~25 developer-days

---

## Phase OAS-6 — External Platformization
**Timeline:** Months 18+ | **Priority:** Future

### 6.1 API & SDK

| Task | Description | Est. |
|------|-------------|------|
| 6.1.1 | Stable REST API: `/api/v1/campaigns`, `/api/v1/artifacts`, `/api/v1/modules` | 5d |
| 6.1.2 | Webhook layer: campaign lifecycle events pushed to external endpoints | 2d |
| 6.1.3 | Python SDK: `oas-client` package for programmatic campaign creation | 3d |
| 6.1.4 | CLI: `oas campaign create`, `oas campaign status`, `oas artifact list` | 3d |

### 6.2 Multi-Tenant

| Task | Description | Est. |
|------|-------------|------|
| 6.2.1 | RBAC: role-based access control on campaigns, artifacts, budgets | 3d |
| 6.2.2 | Tenant separation: isolated campaign namespaces, budgets, and data | 3d |
| 6.2.3 | Partner-facing console: stripped-down Office view for external users | 5d |

### 6.3 Campaign Templates

| Task | Description | Est. |
|------|-------------|------|
| 6.3.1 | Template library: common campaign patterns (literature review, DOE, simulation) | 3d |
| 6.3.2 | Template marketplace: share/discover campaign templates | 2d |
| 6.3.3 | One-click campaign launch from template | 1d |

### OAS-6 Success Criteria
- [ ] External users can launch campaigns via API/SDK
- [ ] Tenant isolation prevents data leakage
- [ ] Campaign templates reduce time-to-first-research by 80%

**Estimated effort:** ~30 developer-days

---

## Implementation Priority Matrix

```
Impact ↑
  │
  │  ★ Schema Registry (1.1)     ★ Decision Engine (3.2)
  │  ★ Module Registry (1.2)     ★ Readiness Scoring (3.1)
  │  ★ Session Recovery (1.5)
  │
  │  ● Intent Schemas (2.1)      ● Three-Layer Memory (4.1)
  │  ● State Machine (2.2)       ● Approval Engine (4.2)
  │  ● Contract Tests (1.3)
  │
  │  ○ Cost Ledger (1.4)         ○ Resource Scheduler (5.1)
  │  ○ Event Normalization (2.3) ○ API/SDK (6.1)
  │
  └───────────────────────────────────→ Effort
      Low                              High

★ = Do first (OAS-1/2)  ● = Do next (OAS-2/3/4)  ○ = Plan for later (OAS-5/6)
```

---

## KPI Tracking

### Phase OAS-1 KPIs
| Metric | Current | Target |
|--------|---------|--------|
| Contract test count | 0 | 40+ |
| Campaign resume success rate | 0% | 95% |
| Cost attribution coverage | Partial | 100% of LLM calls |
| Registered module count | 0 (hardcoded) | 3+ (dynamic) |

### Phase OAS-2 KPIs
| Metric | Current | Target |
|--------|---------|--------|
| Campaigns with typed intents | 0% | 100% |
| Campaign replay success rate | 0% | 90% |
| Schema validation coverage | 0% | 100% of inputs |

### Phase OAS-3 KPIs
| Metric | Current | Target |
|--------|---------|--------|
| Decision explainability | None | 100% of routing decisions logged with reasons |
| Wasted compute (unnecessary module calls) | Unknown | -30% vs. baseline |
| Human intervention frequency | High | -50% via better auto-routing |

### Phase OAS-4 KPIs
| Metric | Current | Target |
|--------|---------|--------|
| Campaigns with complete provenance | ~0% | 100% |
| Audit export success rate | 0% | 100% |
| Alert-to-human latency | N/A | <60s |

---

## Dependency Map

```
OAS-1 (Contracts) ─────────────► OAS-2 (Protocol Hub)
    │                                  │
    │                                  ▼
    │                           OAS-3 (Intelligence)
    │                                  │
    ▼                                  ▼
OAS-4 (Governance)              OAS-5 (Multi-Site)
    │                                  │
    └──────────────┬───────────────────┘
                   ▼
            OAS-6 (Platform)
```

OAS-1 is prerequisite for everything. OAS-2 and OAS-4 can partially overlap. OAS-3 requires OAS-2 schemas. OAS-5 and OAS-6 are independent of each other but both need OAS-1–3.

---

## First Milestone

> **"One campaign object, one schema registry, one provenance graph."**
>
> When a `/deepresearch` command produces a `CampaignSchema` with typed `ResearchIntentPackage` input, versioned steps, attributed costs, and a replayable event trail — OAS-1 and OAS-2 are done.

---

## Total Effort Estimate

| Phase | Developer-Days | Timeline |
|-------|---------------|----------|
| OAS-1 | ~30 | Weeks 1–8 |
| OAS-2 | ~25 | Months 2–4 |
| OAS-3 | ~23 | Months 4–7 |
| OAS-4 | ~30 | Months 7–12 |
| OAS-5 | ~25 | Months 12–18 |
| OAS-6 | ~30 | Months 18+ |
| **Total** | **~163** | **~18 months** |

This is a single-developer estimate. With parallel work on independent phases (e.g., OAS-4 governance in parallel with OAS-3 intelligence), total calendar time compresses to ~12 months.
