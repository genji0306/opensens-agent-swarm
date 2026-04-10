---
name: darklab-kairos
description: >
  KAIROS autonomous background daemon — heartbeat monitoring, nightly
  autoDream knowledge consolidation, proactive research suggestions.
  Uses only local Gemma 4 ($0, no cloud calls).
metadata:
  {"openclaw": {"emoji": "clock", "requires": {"env": []}}}
---

# DarkLab KAIROS Daemon

KAIROS (Ancient Greek: "the right moment") is an ambient intelligence daemon that runs on Leader at idle priority. It performs continuous background housekeeping to keep the research swarm healthy and productive.

## Capabilities

- **Heartbeat monitoring** (every 60s) — check Ollama health, pending plans, daily budget, stuck campaigns
- **autoDream** (nightly at 03:00) — knowledge base consolidation: dedup, prune stale, merge similar
- **Proactive suggestions** — detect research gaps, low-confidence topics, high-quality RL training traces
- **RL rollout curation** — identify conversation traces suitable for LoRA training

## Resource Discipline

- Runs at OS idle priority (nice 19)
- Gated by IdleBudgetRule: refuses to act if daily spend > 20% of daily cap
- Uses ONLY local Gemma via Ollama — no cloud API calls, ever
- All actions emit kairos.* DRVP events for Boss visibility

## Subcommands

| Command | Description |
|---------|-------------|
| `/kairos status` | Daemon health, last heartbeat, budget status |
| `/kairos heartbeat` | Run one heartbeat scan manually |
| `/kairos autodream` | Run autoDream knowledge consolidation |
| `/kairos suggest` | Run proactive suggestion scan |
| `/kairos start` | Start background daemon loops |
| `/kairos stop` | Stop background daemon loops |

## DRVP Events

| Event | Trigger |
|-------|---------|
| `kairos.started` | Daemon started |
| `kairos.stopped` | Daemon stopped |
| `kairos.heartbeat.tick` | Each heartbeat scan |
| `kairos.blocked` | Budget exceeded, work blocked |
| `kairos.autodream.started` | autoDream begins |
| `kairos.autodream.completed` | autoDream finishes |
| `kairos.proactive.suggested` | Follow-up suggestion detected |

## Input

```json
{
  "text": "status"
}
```

## Output

```json
{
  "status": "ok",
  "action": "kairos_status",
  "running": true,
  "enabled": true,
  "budget_blocked": false,
  "last_heartbeat": {
    "budget_ratio": 0.05,
    "stuck_campaigns": 0,
    "dev_reachable": true
  }
}
```

## Example

```
/kairos status
/kairos heartbeat
/kairos autodream
/kairos suggest
```
