---
name: darklab-drvp-events
description: DRVP event types, emission patterns, consumer handling, and event flow architecture for the Opensens Agent Swarm.
origin: OAS
---

# DRVP (Dynamic Request Visualization Protocol)

79+ event types emitted by the middleware pipeline. Events flow via Redis Pub/Sub (`drvp:{company_id}`) and persist to the Paperclip activity log.

## When to Activate

- Working on DRVP event types or emission code
- Modifying middleware pipeline event emission
- Adding new event types to `core/oas_core/protocols/drvp.py`
- Working on Office DRVP consumer (`office/src/drvp/drvp-consumer.ts`)
- Wiring Paperclip issue-linker responses to DRVP events

## Event Flow Architecture

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

## Event Type Categories (79+)

### Request Lifecycle
- `request.created` / `request.routed` / `request.completed` / `request.failed`

### Agent Lifecycle
- `agent.activated` / `agent.thinking` / `agent.speaking` / `agent.idle` / `agent.error`

### Handoff
- `handoff.started` / `handoff.completed`

### Tool Usage
- `tool.call.started` / `tool.call.completed` / `tool.call.failed`

### LLM Calls
- `llm.call.started` / `llm.call.completed` / `llm.call.boosted` / `llm.stream.token`

### Memory
- `memory.read` / `memory.write`

### Budget
- `budget.check` / `budget.warning` / `budget.exhausted`

### Browser
- `browser.navigate` / `browser.action` / `browser.blocked`

### Campaign
- `campaign.step.started` / `campaign.step.completed` / `campaign.step.retrying`
- `campaign.step.cascade_failed` / `campaign.step.routed`
- `campaign.approval.required` / `campaign.approved`

### RL Training
- `rl.rollout.collected` / `rl.training.step` / `rl.checkpoint.saved`
- `rl.evaluation.completed` / `rl.checkpoint.promoted` / `rl.checkpoint.rolledback`

### Deep Research
- `deep_research.started` / `deep_research.iteration` / `deep_research.search`
- `deep_research.scored` / `deep_research.completed`

### Debate
- `debate.started` / `debate.round.completed` / `debate.completed` / `debate.transcript.ready`

### Decision Engine
- `decision.recommended` / `readiness.scored` / `campaign.reflection.completed` / `uncertainty.routing`

### Plan-File Orchestrator (v2)
- `plan.detected` / `plan.parsed` / `plan.error`
- `orchestrator.started` / `orchestrator.step_dispatched` / `orchestrator.completed` / `orchestrator.failed`

### KAIROS Daemon (v2)
- `kairos.started` / `kairos.stopped` / `kairos.heartbeat` / `kairos.heartbeat.tick`
- `kairos.blocked` / `kairos.autodream.started` / `kairos.autodream.completed`
- `kairos.proactive.suggestion` / `kairos.proactive.suggested` / `kairos.rollout.curated`

### Research Router (v2)
- `research.router.mode_chosen` / `research.backend.started` / `research.backend.completed`
- `research.backend.failed` / `research.synthesis.started` / `research.synthesis.completed`

### Compute Borrowing (v2)
- `compute.borrow.requested` / `compute.borrow.accepted` / `compute.borrow.rejected`
- `compute.borrow.completed` / `compute.capability.published` / `compute.priority_floor.changed`

### Knowledge System (Phase 25)
- `knowledge.ingested` / `knowledge.conflict.detected` / `knowledge.conflict.auto_resolved`
- `knowledge.page.compiled` / `wiki.lint.completed` / `wiki.sync.completed`

### Eval System (Phase 25)
- `eval.run.completed` / `eval.regression.detected`

### Memory Compression
- `memory.pool.status` / `memory.pool.eviction` / `memory.compression.stats`

## Emission Pattern

```python
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

await emit(DRVPEvent(
    event_type=DRVPEventType.REQUEST_CREATED,
    request_id=request_id,
    agent_name=agent_name,
    device=device,
    payload={"title": "...", "source": "..."},
))
```

- `LLM_STREAM_TOKEN` events are rate-limited to 1 per 500ms per agent
- All emits are fire-and-forget (best-effort, never block the pipeline)
- Redis and Paperclip backends configured via `configure()` at startup

## Office Consumer Patterns

TypeScript consumer (`office/src/drvp/drvp-consumer.ts`):
- Maps DRVP events to Zustand store updates
- Visual status: `agent.thinking` → spinning indicator, `agent.speaking` → speech bubble
- Handoff animation: from-agent gets `handing_off` status, to-agent gets `receiving`
- Budget events refresh Paperclip dashboard
- Campaign step events update progress bars

## Adding New Event Types

1. Add enum value to `DRVPEventType` in `core/oas_core/protocols/drvp.py`
2. Add TypeScript type to `office/src/drvp/drvp-types.ts`
3. Add consumer handler in `office/src/drvp/drvp-consumer.ts`
4. Add issue-linker handler in `paperclip/server/src/services/drvp-issue-linker.ts` (if it creates/updates issues)
5. Emit from the relevant middleware or agent code
