---
name: darklab-model-routing
description: OAS v2 7-tier model taxonomy, degradation chain, OpusGate policy, SonnetBudget rule, and ModelRouter.route_v2() usage patterns.
origin: OAS
---

# Model Routing (v2)

`core/oas_core/model_router.py` — 7-tier taxonomy with automatic degradation chain.

## When to Activate

- Adding or modifying model routing logic
- Implementing new campaign steps that need `route_v2()`
- Debugging tier escalation or degradation
- Working on compute borrowing (`inference/client.py`)
- Configuring OpusGate / SonnetBudget policy rules

## 7-Tier Taxonomy

| Tier | Location | Gate |
|------|----------|------|
| `PLANNING_LOCAL` | Leader (Gemma 4 E4B) | Automatic |
| `REASONING_LOCAL` | DEV (Gemma 4 27B MoE Q4, borrowed) | Automatic |
| `WORKER_LOCAL` | DEV (3× Gemma 4 E4B pool, borrowed) | Automatic, time-sliced |
| `CODE_LOCAL` | DEV (Qwen2.5-Coder 7B) | DEV task delegation |
| `RL_EVOLVED` | DEV (Qwen3 + per-agent LoRA) | Automatic when LoRA available |
| `CLAUDE_SONNET` | Cloud (Anthropic) | Per-mission budget cap |
| `CLAUDE_OPUS` | Cloud (Anthropic) | **Per-call Boss approval — no bypass** |

Default path never touches Anthropic. Sonnet handles ~10% of cases.

## Degradation Chain

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

**Confidential missions** (`mission.confidential=true`) block all cloud tiers at the router — run entirely on Leader + DEV local compute.

## route_v2() Usage

```python
from oas_core.model_router import ModelRouter

router = ModelRouter(settings)
tier = await router.route_v2(
    task_type=TaskType.RESEARCH,
    routing_context=ctx,          # RoutingContext from orchestrator
    mission_config=mission,       # PlanFile with confidential/sonnet_cap_usd
)
```

`RoutingContext` captures: dev_priority_floor, dev_reachable, quality_threshold, prior_tier_failed, mission_confidential, budget_remaining_usd.

## Policy Rules

### OpusGateRule
- Blocks `CLAUDE_OPUS` unless Boss has approved this specific call
- Emits `decision.opus_requested` → pauses mission → OAS approval queue
- `OpusGate` disabling requires Boss approval + 24-hour cooldown
- **Never bypass** — no timeout grant, no environment override

### SonnetBudgetRule
- Tracks per-mission Sonnet spend against `plan.sonnet_cap_usd`
- Blocks `CLAUDE_SONNET` once cap is hit (not just warns)
- Cap is per-PlanFile instance; resets on new plan

### IdleBudgetRule (KAIROS gating)
- Blocks cloud tiers if daily spend ratio ≥ 20% during KAIROS-initiated work
- Only applies when `routing_context.triggered_by == "kairos"`

## Compute Borrowing

Leader borrows DEV inference via HTTP (not task delegation):

```python
from oas_core.inference.client import BorrowedInferenceClient
from oas_core.inference.types import BorrowRequest

client = BorrowedInferenceClient(settings)
response = await client.borrow(BorrowRequest(
    prompt=prompt,
    model_hint="gemma4:27b",
    max_tokens=2048,
    priority=1,
))
# response.outcome in {COMPLETED, REJECTED_FLOOR, REJECTED_CAPACITY, TIMEOUT, ...}
```

Rejections are `BorrowResponse` (not exceptions) — only transport faults raise.

## DRVP Events

- `research.router.mode_chosen` — tier selected
- `compute.borrow.requested` / `.accepted` / `.rejected` / `.completed`
- `compute.priority_floor.changed` — DEV backpressure update
- `decision.opus_requested` — Boss approval needed
