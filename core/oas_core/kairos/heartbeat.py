"""KairosHeartbeat — 60-second scan loop for ambient housekeeping.

Checks:
1. Idle budget ratio — if daily spend > 20% of cap, block all KAIROS work
2. Expired task leases — surface to Boss via DRVP
3. Stuck campaigns — campaigns with no progress for > threshold minutes
4. DEV health — whether borrowed inference is available
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

__all__ = ["KairosHeartbeat", "HeartbeatSnapshot"]

logger = logging.getLogger("oas.kairos.heartbeat")


@dataclass(frozen=True)
class HeartbeatSnapshot:
    """Point-in-time housekeeping scan result."""

    timestamp: float
    budget_blocked: bool = False
    budget_ratio: float = 0.0
    expired_leases: int = 0
    stuck_campaigns: int = 0
    dev_reachable: bool = False
    actions_taken: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "budget_blocked": self.budget_blocked,
            "budget_ratio": round(self.budget_ratio, 3),
            "expired_leases": self.expired_leases,
            "stuck_campaigns": self.stuck_campaigns,
            "dev_reachable": self.dev_reachable,
            "actions_taken": self.actions_taken,
        }


class KairosHeartbeat:
    """Runs a single housekeeping scan.

    Meant to be called every 60 seconds by the ``KairosDaemon`` loop.
    The heartbeat itself is synchronous/fast; any remediation actions
    are returned as a list for the daemon to execute.
    """

    def __init__(
        self,
        *,
        idle_budget_cap: float = 0.2,
        stuck_threshold_minutes: float = 30.0,
        get_daily_spend: Callable[[], tuple[float, float]] | None = None,
        get_expired_leases: Callable[[], list[Any]] | None = None,
        get_stuck_campaigns: Callable[[], list[Any]] | None = None,
        check_dev_health: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._idle_cap = idle_budget_cap
        self._stuck_threshold = stuck_threshold_minutes
        self._get_spend = get_daily_spend
        self._get_leases = get_expired_leases
        self._get_stuck = get_stuck_campaigns
        self._check_dev = check_dev_health
        self._last_snapshot: HeartbeatSnapshot | None = None

    async def scan(self) -> HeartbeatSnapshot:
        """Execute one housekeeping scan. Returns snapshot."""
        now = time.time()
        actions: list[str] = []

        # 1. Budget check
        budget_blocked = False
        budget_ratio = 0.0
        if self._get_spend is not None:
            try:
                spent, budget = self._get_spend()
                budget_ratio = spent / budget if budget > 0 else 0.0
                budget_blocked = budget_ratio > self._idle_cap
                if budget_blocked:
                    actions.append(f"budget_blocked: {budget_ratio:.0%} > {self._idle_cap:.0%}")
            except Exception as exc:
                logger.warning("kairos_budget_check_failed", extra={"error": str(exc)})

        # 2. Expired leases
        expired_count = 0
        if self._get_leases is not None:
            try:
                expired = self._get_leases()
                expired_count = len(expired)
                if expired_count > 0:
                    actions.append(f"expired_leases: {expired_count}")
            except Exception as exc:
                logger.warning("kairos_lease_check_failed", extra={"error": str(exc)})

        # 3. Stuck campaigns
        stuck_count = 0
        if self._get_stuck is not None:
            try:
                stuck = self._get_stuck()
                stuck_count = len(stuck)
                if stuck_count > 0:
                    actions.append(f"stuck_campaigns: {stuck_count}")
            except Exception as exc:
                logger.warning("kairos_stuck_check_failed", extra={"error": str(exc)})

        # 4. DEV health
        dev_reachable = False
        if self._check_dev is not None:
            try:
                dev_reachable = await self._check_dev()
            except Exception:
                dev_reachable = False

        snapshot = HeartbeatSnapshot(
            timestamp=now,
            budget_blocked=budget_blocked,
            budget_ratio=budget_ratio,
            expired_leases=expired_count,
            stuck_campaigns=stuck_count,
            dev_reachable=dev_reachable,
            actions_taken=actions,
        )
        self._last_snapshot = snapshot
        return snapshot

    @property
    def last_snapshot(self) -> HeartbeatSnapshot | None:
        return self._last_snapshot

    @property
    def is_blocked(self) -> bool:
        """Whether KAIROS is currently budget-blocked."""
        if self._last_snapshot is None:
            return False
        return self._last_snapshot.budget_blocked
