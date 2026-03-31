"""Module capability protocol — standard interface for routable modules.

Any module that wants to receive work from OAS must implement this
protocol. This replaces hardcoded routing tables with self-declaring
modules that register their capabilities at startup.

Existing adapters (Paperclip, OpenClaw, DeerFlow) can implement this
protocol to become first-class routable targets.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

__all__ = [
    "ModuleCapability",
    "ModuleHealth",
    "ModuleStatus",
    "CostEstimate",
]


class ModuleStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ModuleHealth(BaseModel):
    """Health status of a registered module."""

    status: ModuleStatus = ModuleStatus.UNKNOWN
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostEstimate(BaseModel):
    """Estimated cost for executing a task on this module."""

    estimated_cost_usd: float = 0.0
    estimated_duration_seconds: float = 0.0
    confidence: float = 0.5
    model: str = ""
    notes: str = ""


@runtime_checkable
class ModuleCapability(Protocol):
    """Protocol that routable modules must implement.

    Modules self-declare their name, supported task types, and provide
    health checks, cost estimates, and execution. The module registry
    discovers and routes to modules via this interface.

    Example::

        class DeerFlowModule:
            @property
            def name(self) -> str:
                return "deerflow"

            @property
            def supported_task_types(self) -> list[str]:
                return ["deerflow", "deep_research"]

            async def health(self) -> ModuleHealth:
                return ModuleHealth(status=ModuleStatus.HEALTHY)

            async def estimate_cost(self, task_type: str, payload: dict) -> CostEstimate:
                return CostEstimate(estimated_cost_usd=0.05)

            async def execute(self, task_type: str, payload: dict) -> dict:
                result = await self.adapter.run_research(...)
                return result
    """

    @property
    def name(self) -> str:
        """Unique module identifier."""
        ...

    @property
    def supported_task_types(self) -> list[str]:
        """Task types this module can handle."""
        ...

    async def health(self) -> ModuleHealth:
        """Check if the module is operational."""
        ...

    async def estimate_cost(
        self, task_type: str, payload: dict[str, Any]
    ) -> CostEstimate:
        """Estimate cost for executing this task type."""
        ...

    async def execute(
        self, task_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a task and return the result."""
        ...
