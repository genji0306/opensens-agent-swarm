"""KAIROS — ambient intelligence daemon for Leader (§9).

KAIROS runs at OS-level idle priority on Leader and performs:

1. **Heartbeat loop** (60s) — scan idle budget, expired leases, stuck campaigns
2. **autoDream** (nightly 03:00) — knowledge base consolidation in a forked subprocess
3. **Proactive suggestions** — gap detection, follow-up research queueing
4. **RL rollout curation** — identify high-quality training traces

Hard rules (non-negotiable):

- **Never calls Sonnet or Opus.** KAIROS is local-only by policy.
- Uses ``BorrowedInferenceClient`` to hit DEV's Gemma pool for any
  inference need.
- Subject to ``IdleBudgetRule``: refuses to act if today's spend > 20%
  of daily cap.
- All actions emit ``kairos.*`` DRVP events for Boss visibility.
- ``dev-forge`` identity is strictly read-only for KAIROS.
"""
from __future__ import annotations

from .autodream import AutoDream
from .forked_worker import ForkedWorker
from .heartbeat import KairosHeartbeat
from .proactive import ProactiveSuggester

__all__ = [
    "AutoDream",
    "ForkedWorker",
    "KairosHeartbeat",
    "ProactiveSuggester",
]
