---
name: darklab-plan-authoring
description: OAS v2 plan-file YAML schema, PlanFile parser, PlanStoreWatcher dual-mode polling, OrchestratorAgent TAO loop, and mission lifecycle.
origin: OAS
---

# Plan Authoring (v2)

Plan files are the primary entry point for v2 missions. Boss expresses intent → OAS → Plan Store → Leader `PlanStoreWatcher` → `OrchestratorAgent`.

## When to Activate

- Writing or editing plan files for missions
- Working on `core/oas_core/plan_file.py` or `plan_store_client.py`
- Modifying `OrchestratorAgent` TAO loop
- Debugging plan parsing errors or watcher polling issues

## Plan File Schema

```yaml
# Required fields
id: "mission-2026-04-ionic-liquids"
title: "Ionic Liquid EIT Electrode Research"
objective: |
  Investigate BMIM-based ionic liquids for EIT sensor electrodes.
  Focus on conductivity, stability, and biocompatibility.

steps:
  - id: literature
    type: LITERATURE
    prompt: "Survey BMIM ionic liquid electrode literature 2020-2026"
    depends_on: []

  - id: simulate
    type: SIMULATE
    prompt: "DFT simulation of BMIM adsorption on Pt(111)"
    depends_on: [literature]

  - id: synthesize
    type: SYNTHESIZE
    prompt: "Synthesize findings into actionable electrode design recommendations"
    depends_on: [literature, simulate]

# v2 fields
sonnet_cap_usd: 2.00        # Per-mission Sonnet budget (SonnetBudgetRule)
opus_allowed: false          # Boss pre-approval for Opus (OpusGateRule)
confidential: false          # true = block all cloud tiers
max_parallel: 2              # Max concurrent campaign steps
research_mode: parallel      # sequential | parallel | hybrid (ResearchRouter)
```

## PlanFile Parser

`core/oas_core/plan_file.py` — validates and normalizes plan YAML:

```python
from oas_core.plan_file import PlanFile

plan = PlanFile.from_yaml(yaml_text)
plan.validate()   # raises PlanValidationError on schema violations
```

Validates: required fields, step ID uniqueness, dependency graph (no cycles), enum values for `type` and `research_mode`.

## PlanStoreWatcher

`core/oas_core/plan_store_client.py` + `cluster/agents/leader/plan_watcher_service.py`

**Dual-mode**: filesystem watcher (legacy) OR HTTP Plan Store poller (v2):

```python
# HTTP mode — polls OAS Plan Store API every 5s
watcher = PlanWatcherService(settings, orchestrator)
await watcher.start()  # non-blocking
```

HTTP poller uses cursor-based `fetch_new()` + `mark_accepted()` to prevent double-processing. Idempotent receipt written per plan ID.

## OrchestratorAgent TAO Loop

`cluster/agents/leader/orchestrator.py`

```
Think  → PlanFile.parse() → build RoutingContext → route_v2()
Act    → CampaignEngine.run() → delegate/borrow/escalate
Observe → Reflector.reflect() → emit DRVP events → write back to Plan Store
```

`routing_context_factory` wires `ModelRouter.route_v2()` for every campaign step. DRVP events emitted at each TAO phase.

## Mission Lifecycle

```
plan.detected → plan.parsed → orchestrator.started
  → orchestrator.step_dispatched (×N)
  → orchestrator.completed | orchestrator.failed
```

Failure modes:
- `plan.error` — YAML parse/validation failure
- `orchestrator.failed` — step cascade failure or budget exhaustion
- `"blocked: needs_boss"` — Opus gate triggered, waiting for approval

## Step Types → TaskType Mapping

| Plan step type | TaskType | Routed to |
|---------------|----------|-----------|
| RESEARCH | RESEARCH | Academic |
| LITERATURE | LITERATURE | Academic |
| SIMULATE | SIMULATE | Experiment |
| ANALYZE | ANALYZE | Experiment |
| SYNTHESIZE | SYNTHESIZE | Leader |
| DEEP_RESEARCH | DEEP_RESEARCH | Leader |
| DOE | DOE | Academic |
