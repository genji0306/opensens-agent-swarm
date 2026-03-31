# OAS Roadmap Development Plan

**Generated:** 2026-03-30
**Baseline:** 581 tests passing, 88 tasks complete (Phases 1-19), 22 DRVP event types, 25 dispatch routes

---

## Status Summary

| Phase | Roadmap Target | Status | Coverage |
|-------|----------------|--------|----------|
| OAS-1 | Stabilization & contract hardening | **Done** | Schema registry, module adapters, contract tests, cost ledger, retry policies |
| OAS-2 | Darklab protocol hub | **Done** | RIP/KA/SIP/EIP/RR schemas, versioning, event normalization, provenance, confidence scoring |
| OAS-3 | Campaign intelligence & decision engine | **Partial** | Evaluation loop done; decision policy, readiness scoring, reflection layer missing |
| OAS-4 | Governance, memory, audit maturity | **Mostly done** | Three-layer memory, approvals, audit trail done; campaign journal, templates, lineage graph missing |
| OAS-5 | Multi-node & multi-site orchestration | **Not started** | Module health exists; scheduler, queue, discovery, failure isolation all missing |
| OAS-6 | External platformization | **Minimal** | Basic REST API + RBAC; webhooks, templates, SDK, partner console missing |

---

## Phase 20 — Campaign Intelligence (OAS-3 completion)

**Target:** 4-6 weeks
**Goal:** Upgrade OAS from reactive router to proactive decision engine

### Task 89: Decision Policy Engine
**File:** `core/oas_core/decision/policy_engine.py`
**LOC estimate:** ~300

Build a `DecisionPolicyEngine` that evaluates (confidence, cost, risk, readiness) to choose the next campaign action:
- Input: `CampaignSchema` current state + `KnowledgeArtifact[]` accumulated evidence
- Output: `DecisionRecommendation` (next_action, target_module, confidence, reasoning, alternatives)
- Actions: `STAY_IN_MODULE`, `HANDOFF_TO`, `ESCALATE_TO_HUMAN`, `STOP_INSUFFICIENT_EVIDENCE`, `RETRY_WITH_REFINEMENT`
- Policy rules defined as composable `PolicyRule` objects (threshold-based + heuristic)
- Default policies: cost ceiling, confidence floor, max retries, human escalation threshold
- Tests: 10+ covering each action type, edge cases, policy composition

### Task 90: Multi-Layer Readiness Scoring
**File:** `core/oas_core/decision/readiness.py`
**LOC estimate:** ~250

Four readiness dimensions scored 0.0-1.0:
- **Knowledge readiness:** source count, confidence of findings, coverage of research intent
- **Simulation readiness:** parameter completeness, model spec quality, compute budget available
- **Experiment readiness:** protocol defined, materials listed, safety reviewed, approval obtained
- **Infrastructure readiness:** target module healthy, budget remaining, queue depth acceptable

Each readiness function takes `CampaignSchema` + module registry state and returns `ReadinessScore` with breakdown.
- Tests: 8+ covering each dimension, threshold behavior

### Task 91: Campaign Reflection Layer
**File:** `core/oas_core/decision/reflection.py`
**LOC estimate:** ~200

Post-stage analysis that runs after each campaign step completes:
- Compares step output against step intent (from campaign plan)
- Scores delta: what was learned, what's still unknown, what changed
- Feeds into `DecisionPolicyEngine` for next-step selection
- Emits DRVP event: `campaign.reflection.completed` (step_id, scores, recommendation)
- Stores reflection in knowledge base for cross-campaign learning
- Tests: 6+ covering reflection scoring, DRVP emission, knowledge persistence

### Task 92: Uncertainty-Aware Routing
**File:** `core/oas_core/decision/uncertainty_router.py`
**LOC estimate:** ~180

Wraps `dispatch.py` routing with uncertainty awareness:
- Before routing: check readiness scores for target module
- If readiness < threshold: suggest prerequisite steps (e.g., "run literature search before simulation")
- If multiple modules viable: rank by (readiness * confidence / cost)
- If all modules below threshold: recommend human consultation
- Wire into `dispatch.py` as optional pre-routing check
- Tests: 6+ covering routing decisions under various readiness states

### Task 93: DRVP Events + Office Integration
- 4 new DRVP event types: `decision.recommended`, `readiness.scored`, `campaign.reflection.completed`, `uncertainty.routing`
- Office `drvp-consumer.ts` handlers for new events
- `DecisionPanel.tsx` component showing latest recommendation + readiness radar
- Tests: 4+ for event emission, 2+ for consumer mapping

**Phase 20 totals:** ~1,200 LOC Python, ~200 LOC TypeScript, ~36 new tests

---

## Phase 21 — Governance Maturity (OAS-4 completion)

**Target:** 3-4 weeks
**Goal:** Close remaining OAS-4 gaps for audit-grade operations

### Task 94: Campaign Journal
**File:** `core/oas_core/campaign_journal.py`
**LOC estimate:** ~200

Persistent campaign journal (append-only JSONL per campaign):
- Records every state transition, decision, reflection, cost event, approval
- Format: `{timestamp, campaign_id, event_type, actor, payload, hash_chain}`
- Hash chain: each entry includes SHA-256 of previous entry (tamper detection)
- `JournalReader` for querying by campaign, time range, event type
- Integrates with `CampaignEngine` — auto-writes on step start/complete/fail
- Tests: 8+ covering write, read, hash chain integrity, replay

### Task 95: Campaign Template Library
**File:** `core/oas_core/campaign_templates.py`
**LOC estimate:** ~180

YAML-defined campaign templates for common research patterns:
- Template format: name, description, steps[] (with task_type, device, config_defaults)
- Built-in templates: `literature-review`, `hypothesis-test`, `simulation-validate`, `full-pipeline`
- `TemplateRegistry.load_from_dir()` — scans `cluster/templates/` directory
- `TemplateRegistry.instantiate(name, overrides)` → `CampaignSchema`
- Paperclip integration: store templates per company, list via API
- Tests: 6+ covering load, instantiate, override, validation

### Task 96: Artifact Lineage Graph
**File:** `core/oas_core/lineage.py`
**LOC estimate:** ~250

Queryable provenance graph connecting campaigns → steps → artifacts:
- `LineageGraph` in-memory graph (dict-based adjacency list)
- Node types: `Campaign`, `Step`, `Artifact`, `Approval`, `CostEvent`
- Edge types: `produced_by`, `depends_on`, `approved_by`, `derived_from`
- `build_from_journal(campaign_id)` — reconstructs graph from campaign journal
- Query methods: `ancestors(node)`, `descendants(node)`, `path(from, to)`, `artifacts_by_evidence_type()`
- Export: `to_dot()` for Graphviz, `to_json()` for Office visualization
- Tests: 8+ covering graph construction, queries, export

### Task 97: Audit Export Bundle
**File:** `core/oas_core/audit_export.py`
**LOC estimate:** ~150

One-command export of a complete campaign audit trail:
- Collects: campaign journal, lineage graph, cost attributions, approval records, DRVP events
- Output: ZIP file with JSON manifests + raw data files
- Includes SHA-256 checksum manifest for integrity verification
- `export_campaign_audit(campaign_id, output_path)` → ZIP path
- Tests: 4+ covering export, integrity, missing data handling

### Task 98: Signed Approval Records
**File:** Update `core/oas_core/middleware/governance.py`
**LOC estimate:** ~80 additions

Add Ed25519 digital signatures to approval records:
- `ApprovalRecord` gains `signature` and `signer_public_key` fields
- Sign on approve/reject with agent or user key
- Verify chain: approval → issue → campaign
- Tests: 4+ covering sign, verify, reject signature

**Phase 21 totals:** ~860 LOC Python, ~30 new tests

---

## Phase 22 — Multi-Node Foundation (OAS-5 start)

**Target:** 6-8 weeks
**Goal:** Lay infrastructure for distributed campaign execution

### Task 99: Redis Task Queue
**File:** `core/oas_core/scheduler/task_queue.py`
**LOC estimate:** ~300

Redis-backed priority task queue:
- `TaskQueue.enqueue(task, priority, device_affinity)` → queued task ID
- `TaskQueue.dequeue(device, capabilities)` → next matching task (blocking pop with timeout)
- `TaskQueue.ack(task_id)` / `TaskQueue.nack(task_id, reason)` — completion/failure signals
- Priority levels: CRITICAL (0), HIGH (1), NORMAL (2), LOW (3), BACKGROUND (4)
- Visibility timeout: tasks auto-requeue if not ack'd within timeout (prevents stuck tasks)
- Dead letter queue for repeatedly failed tasks
- Redis keys: `oas:queue:{priority}`, `oas:inflight:{task_id}`, `oas:dlq`
- Tests: 10+ covering enqueue, dequeue, priority, affinity, timeout, DLQ

### Task 100: Node Health Heartbeat
**File:** `core/oas_core/scheduler/heartbeat.py`
**LOC estimate:** ~200

Node health heartbeat and lease model:
- `HeartbeatService.register(node_id, capabilities, address)` — register on startup
- `HeartbeatService.heartbeat(node_id)` — periodic heartbeat (every 10s)
- `HeartbeatService.lease(node_id, task_id, duration)` — claim task lease
- `HeartbeatService.get_healthy_nodes()` → list of nodes with last heartbeat < 30s
- Redis keys: `oas:node:{node_id}` (hash: capabilities, address, last_heartbeat, status)
- Node states: ONLINE, DEGRADED (missed 1 heartbeat), OFFLINE (missed 3)
- DRVP events: `node.registered`, `node.offline`, `node.degraded`
- Tests: 8+ covering register, heartbeat, lease, expiry, state transitions

### Task 101: Resource-Aware Scheduler
**File:** `core/oas_core/scheduler/scheduler.py`
**LOC estimate:** ~350

Central scheduler that dispatches campaign steps to available nodes:
- `Scheduler.schedule(campaign_step)` — finds best node based on:
  - Task type capability match
  - Current queue depth per node
  - Budget remaining for the campaign
  - Node health status
  - Data locality hints (prefer node where prior steps ran)
- `Scheduler.rebalance()` — periodic check for stuck/failed tasks, reassign to healthy nodes
- Degraded mode: if target device offline, queue with backoff; if all offline, pause campaign
- Wire into `CampaignEngine` — replace direct dispatch with scheduler
- Tests: 10+ covering scheduling, rebalance, degraded mode, affinity

### Task 102: Node Capability Discovery
**File:** `core/oas_core/scheduler/discovery.py`
**LOC estimate:** ~180

Dynamic node registration replacing hardcoded 3-node topology:
- Each node runs a discovery agent that registers capabilities on startup
- Capabilities: supported task types, available models, memory (GB), GPU presence
- `DiscoveryService.discover()` — returns all registered nodes with capabilities
- `DiscoveryService.find_capable(task_type)` — returns nodes that can handle a task type
- Auto-deregister on node offline (heartbeat expiry)
- Tests: 6+ covering registration, discovery, deregistration

### Task 103: Failure Isolation
**File:** `core/oas_core/scheduler/isolation.py`
**LOC estimate:** ~200

Failure containment for partial cluster outages:
- `IsolationPolicy.on_node_failure(node_id)` — handles node going offline mid-task:
  - In-flight tasks: requeue to other healthy nodes (if retryable)
  - Campaign steps: mark as `PENDING_RETRY`, update campaign state
  - Budget: release reserved budget for failed tasks
- `IsolationPolicy.on_task_failure(task_id, error)` — handles individual task failure:
  - Classify: transient (retry), permanent (fail step), resource (requeue with backoff)
  - Circuit breaker per (node, task_type) pair
- Degraded mode execution: campaigns continue with available nodes, skip unavailable steps
- Tests: 8+ covering node failure, task failure, classification, degraded mode

### Task 104: Multi-Site Dashboard Updates
**File:** Update `office/src/components/panels/` + new `ClusterStatusPanel.tsx`
**LOC estimate:** ~300 TypeScript

- `ClusterStatusPanel.tsx`: node list with health status, queue depth, active tasks
- DRVP consumer handlers for `node.*` events
- Scheduler status in DashboardPage (queue size, inflight count, DLQ size)
- Tests: 4+ for panel rendering

**Phase 22 totals:** ~1,530 LOC Python, ~300 LOC TypeScript, ~46 new tests

---

## Phase 23 — Platformization Foundation (OAS-6 start)

**Target:** 4-6 weeks
**Goal:** Minimum viable external platform

### Task 105: Webhook Event Layer
**Files:** `core/oas_core/webhooks/` (dispatcher, registry, retry)
**LOC estimate:** ~350

- `WebhookRegistry`: CRUD for webhook subscriptions (URL, event_types[], secret, active)
- `WebhookDispatcher`: async delivery with HMAC-SHA256 signature header
- Retry: exponential backoff (1s, 5s, 30s, 5m), max 5 attempts
- Dead letter log for permanently failed deliveries
- Event filter: subscribe to specific DRVP event types
- Paperclip integration: webhook subscriptions per company
- Tests: 10+ covering register, dispatch, signature, retry, filter

### Task 106: Campaign Template CRUD API
**Files:** Update Paperclip server routes + DB schema
**LOC estimate:** ~200

- Drizzle migration: `campaign_templates` table (id, company_id, name, description, steps_json, created_at, updated_at)
- REST endpoints: `GET/POST/PUT/DELETE /api/companies/{id}/campaign-templates`
- Validation: steps must reference valid TaskTypes
- Import/export: JSON format for template sharing
- Tests: 6+ for CRUD operations

### Task 107: Structured Campaign Creation API
**Files:** Update `cluster/agents/leader/serve.py`
**LOC estimate:** ~150

New endpoint `POST /campaign` accepting structured campaign objects:
- Input: `CampaignCreateRequest` (template_id or steps[], objective, budget_limit, priority)
- Validates against schema registry
- Creates Paperclip issue automatically
- Returns campaign_id + status
- Replaces text-command-only interface for programmatic use
- Tests: 6+ covering creation, validation, template-based, error cases

### Task 108: Python SDK
**Files:** `sdk/opensens_oas/` (client, models, exceptions)
**LOC estimate:** ~400

Minimal Python SDK for external campaign management:
- `OASClient(base_url, api_key)` — authenticated client
- Methods: `create_campaign()`, `get_campaign()`, `list_campaigns()`, `cancel_campaign()`
- Methods: `subscribe_webhook()`, `list_templates()`, `get_results()`
- Async support via `AsyncOASClient`
- Published as `opensens-oas` package (pyproject.toml)
- Tests: 8+ with mocked HTTP

### Task 109: API Key Management
**Files:** Update Paperclip server
**LOC estimate:** ~150

- `api_keys` table: id, company_id, name, key_hash, scopes[], rate_limit, created_at, expires_at
- REST endpoints: `GET/POST/DELETE /api/companies/{id}/api-keys`
- Rate limiting middleware: token bucket per API key
- Scope enforcement: read-only, campaign-create, admin
- Tests: 6+ covering key CRUD, rate limiting, scope enforcement

### Task 110: Partner Console Differentiation
**Files:** Update Office + Paperclip UI
**LOC estimate:** ~200 TypeScript

- Role-aware sidebar: partners see campaigns, results, templates only
- Hide internal panels (RL status, TurboQuant, cluster) for non-admin roles
- Campaign creation wizard using template library
- Tests: 4+ for role-based rendering

**Phase 23 totals:** ~1,250 LOC Python, ~200 LOC TypeScript, ~40 new tests

---

## Development Timeline

```
Week 1-6     Phase 20: Campaign Intelligence (OAS-3)     +36 tests → 617
Week 7-10    Phase 21: Governance Maturity (OAS-4)        +30 tests → 647
Week 11-18   Phase 22: Multi-Node Foundation (OAS-5)      +46 tests → 693
Week 19-24   Phase 23: Platformization Foundation (OAS-6) +40 tests → 733
```

**Total new work:** ~4,840 LOC Python + ~700 LOC TypeScript + 152 new tests
**Projected test count:** 733 (from current 581)

---

## Priority Order

If time-constrained, implement in this order:

1. **Task 89: Decision Policy Engine** — highest impact on campaign quality
2. **Task 90: Readiness Scoring** — enables intelligent routing
3. **Task 99: Redis Task Queue** — foundation for all multi-node work
4. **Task 100: Node Heartbeat** — required for task queue reliability
5. **Task 94: Campaign Journal** — enables audit compliance
6. **Task 105: Webhook Layer** — enables external integrations
7. **Task 101: Scheduler** — ties queue + heartbeat into dispatch
8. **Task 108: Python SDK** — enables programmatic access

---

## KPIs to Track

### Phase 20 (Intelligence)
- % of campaigns where decision engine overrides naive routing
- Average cost reduction per campaign vs. pre-intelligence baseline
- Human escalation rate (target: <15% of campaigns)

### Phase 21 (Governance)
- % of campaigns with complete journal (target: 100%)
- Audit export success rate (target: 100%)
- Template reuse rate (target: >30% of new campaigns)

### Phase 22 (Multi-Node)
- Task queue throughput (tasks/minute)
- Node failure recovery time (target: <60s)
- Campaign completion rate under partial outage (target: >80%)

### Phase 23 (Platform)
- Webhook delivery success rate (target: >99%)
- External API adoption (target: 2+ external users within 4 weeks)
- SDK download count

---

## Dependencies & Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Redis single point of failure | Queue loss, heartbeat loss | Redis Sentinel or Redis Cluster in Phase 22 |
| Decision engine adds latency | Slower campaign start | Cache readiness scores, async reflection |
| Multi-node breaks existing tests | CI regression | Feature-flag scheduler behind `DARKLAB_SCHEDULER_ENABLED` |
| SDK API stability | Breaking changes for users | Semver from day 1, deprecation warnings |
| Template sprawl | Unmaintained templates | Template validation on load, usage tracking |

---

## Architecture Decisions

### ADR-1: Decision engine as middleware vs. standalone
**Decision:** Standalone module in `core/oas_core/decision/`
**Reason:** Middleware pipeline is already 5 stages deep; adding decision logic there would couple routing decisions to the request lifecycle. Standalone allows campaign-level decisions (not just per-request).

### ADR-2: Redis for task queue vs. PostgreSQL
**Decision:** Redis (sorted sets + streams)
**Reason:** Sub-millisecond dequeue latency, blocking pop support, natural fit with existing DRVP Redis transport. PostgreSQL `SKIP LOCKED` is viable but adds connection pressure.

### ADR-3: SDK as separate package vs. embedded
**Decision:** Separate `sdk/` directory, published as `opensens-oas`
**Reason:** External users should not need the full OAS codebase. SDK depends only on `httpx` + `pydantic`.

### ADR-4: Webhook delivery — push vs. pull
**Decision:** Push (HTTP POST to subscriber URL)
**Reason:** Standard pattern, matches existing DRVP event model. Pull (polling) would require additional API surface and client-side complexity.
