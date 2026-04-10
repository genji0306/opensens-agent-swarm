---
name: darklab-kairos-ops
description: KAIROS daemon architecture, heartbeat loop, autoDream consolidation, proactive suggestion system, and forked subprocess isolation.
origin: OAS
---

# KAIROS Daemon

KAIROS runs at OS-level idle priority (`nice 19`) on Leader. Never calls Sonnet/Opus. Subject to `IdleBudgetRule` (20% daily spend cap).

## When to Activate

- Modifying heartbeat or autoDream logic
- Adding new proactive suggestion types
- Working on `cluster/agents/leader/kairos.py` (dispatch entry)
- Adding KAIROS-triggered DRVP events

## Architecture

```
KairosDaemon (leader process, nice 19)
├── heartbeat()          60s scan
├── auto_dream()         nightly 03:00 → forked subprocess
├── proactive()          gap detection → suggestions
└── DRVP emitter         kairos.* events → Redis → Office KairosPanel
```

Core: `core/oas_core/kairos/` (heartbeat, autodream, proactive, forked_worker)
Leader daemon: `cluster/agents/leader/kairos.py`

## Heartbeat (60s)

`core/oas_core/kairos/heartbeat.py` — checks in order:
1. Budget ratio > 20% → `kairos.blocked`, skip remaining
2. Expired leases → request renewal or release
3. Stuck campaigns (no step activity > 10 min) → `kairos.blocked`
4. DEV health → poll `InferenceEndpoint /v1/health`

## autoDream (nightly 03:00)

`core/oas_core/kairos/autodream.py` — runs in forked subprocess:
1. SHA-256 dedup (exact duplicates)
2. Prune stale (confidence < 0.3, age > 90 days)
3. Merge similar (prefix matching; Phase 25: cosine > 0.92)
4. Atomic write-back (temp → rename)

**Never** writes to OpenViking or DEV during autoDream — local KB only.

## Forked Worker

`core/oas_core/kairos/forked_worker.py`

```python
proc = subprocess.Popen([sys.executable, worker_script], ...)
os.setpriority(os.PRIO_PROCESS, proc.pid, 19)
```

I/O via temp JSON files. Parent waits with timeout, kills on overrun.

## Proactive Suggestions

Three types (`core/oas_core/kairos/proactive.py`):
- `research_gap` — topic with < 3 sources
- `low_confidence` — claims with confidence < 0.5
- `rl_curation` — rollouts ready for promotion review

## Hard Rules

| Rule | Value |
|------|-------|
| Cloud LLM | NEVER |
| Daily spend gate | 20% |
| Nice level | 19 |
| autoDream isolation | Forked subprocess only |

## DRVP Events

```
kairos.started / kairos.stopped
kairos.heartbeat / kairos.heartbeat.tick
kairos.blocked
kairos.autodream.started / kairos.autodream.completed
kairos.proactive.suggestion / kairos.proactive.suggested
kairos.rollout.curated
```
