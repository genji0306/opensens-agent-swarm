"""Module registry — dynamic module registration, discovery, and health tracking.

Modules register themselves at startup and the registry maintains their
health status, capability declarations, and routing information. The
dispatch layer queries the registry instead of a hardcoded routing table
to find the best module for a given task type.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from oas_core.registry.capability import (
    CostEstimate,
    ModuleCapability,
    ModuleHealth,
    ModuleStatus,
)

__all__ = ["ModuleRegistry", "get_module_registry"]

logger = logging.getLogger("oas.registry")


class _RegisteredModule:
    """Internal wrapper tracking a module and its health."""

    def __init__(self, module: ModuleCapability):
        self.module = module
        self.registered_at = datetime.now(timezone.utc)
        self.last_health = ModuleHealth(status=ModuleStatus.UNKNOWN)
        self.health_check_count = 0
        self.execution_count = 0
        self.failure_count = 0

    @property
    def name(self) -> str:
        return self.module.name

    @property
    def is_healthy(self) -> bool:
        return self.last_health.status in (ModuleStatus.HEALTHY, ModuleStatus.DEGRADED)


class ModuleRegistry:
    """Central registry for OAS modules.

    Manages registration, health tracking, and capability-based routing.

    Usage::

        registry = ModuleRegistry()
        registry.register(my_deerflow_module)
        registry.register(my_academic_module)

        # Find modules that can handle a task type
        modules = registry.find_by_task_type("research")

        # Get the best module (healthy + lowest cost)
        module = await registry.best_module_for("research", payload)

        # Execute via the registry
        result = await registry.execute("research", payload)
    """

    def __init__(self) -> None:
        self._modules: dict[str, _RegisteredModule] = {}
        self._task_type_index: dict[str, list[str]] = {}

    def register(self, module: ModuleCapability) -> None:
        """Register a module with the registry."""
        name = module.name

        if name in self._modules:
            logger.warning("module_replaced", extra={"module_name": name})

        entry = _RegisteredModule(module)
        self._modules[name] = entry

        # Index by supported task types
        for task_type in module.supported_task_types:
            if task_type not in self._task_type_index:
                self._task_type_index[task_type] = []
            if name not in self._task_type_index[task_type]:
                self._task_type_index[task_type].append(name)

        logger.info(
            "module_registered",
            extra={
                "module_name": name,
                "task_types": module.supported_task_types,
            },
        )

    def unregister(self, name: str) -> bool:
        """Remove a module from the registry."""
        entry = self._modules.pop(name, None)
        if entry is None:
            return False

        # Clean up task type index
        for task_type, modules in self._task_type_index.items():
            if name in modules:
                modules.remove(name)

        logger.info("module_unregistered", extra={"module_name": name})
        return True

    def get(self, name: str) -> ModuleCapability | None:
        """Get a module by name."""
        entry = self._modules.get(name)
        return entry.module if entry else None

    def find_by_task_type(self, task_type: str) -> list[ModuleCapability]:
        """Find all modules that support a given task type."""
        names = self._task_type_index.get(task_type, [])
        result = []
        for name in names:
            entry = self._modules.get(name)
            if entry and entry.is_healthy:
                result.append(entry.module)
        return result

    async def check_health(self, name: str) -> ModuleHealth:
        """Check health of a specific module."""
        entry = self._modules.get(name)
        if entry is None:
            return ModuleHealth(status=ModuleStatus.UNKNOWN, error="Module not found")

        try:
            health = await entry.module.health()
            entry.last_health = health
            entry.health_check_count += 1
        except Exception as e:
            health = ModuleHealth(
                status=ModuleStatus.UNHEALTHY,
                error=str(e)[:200],
            )
            entry.last_health = health

        return health

    async def check_all_health(self) -> dict[str, ModuleHealth]:
        """Check health of all registered modules concurrently."""
        tasks = {name: self.check_health(name) for name in self._modules}
        results = {}
        for name, coro in tasks.items():
            results[name] = await coro
        return results

    async def best_module_for(
        self, task_type: str, payload: dict[str, Any]
    ) -> ModuleCapability | None:
        """Find the best module for a task type based on health and cost."""
        candidates = self.find_by_task_type(task_type)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # Rank by estimated cost
        estimates: list[tuple[ModuleCapability, CostEstimate]] = []
        for module in candidates:
            try:
                estimate = await module.estimate_cost(task_type, payload)
                estimates.append((module, estimate))
            except Exception:
                estimates.append((module, CostEstimate()))

        estimates.sort(key=lambda x: x[1].estimated_cost_usd)
        return estimates[0][0]

    async def execute(
        self, task_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a task via the best available module.

        Raises KeyError if no module supports the task type.
        """
        module = await self.best_module_for(task_type, payload)
        if module is None:
            raise KeyError(f"No module registered for task type '{task_type}'")

        entry = self._modules.get(module.name)
        if entry:
            entry.execution_count += 1

        try:
            return await module.execute(task_type, payload)
        except Exception:
            if entry:
                entry.failure_count += 1
            raise

    def list_modules(self) -> list[dict[str, Any]]:
        """List all registered modules with health and stats."""
        return [
            {
                "name": entry.name,
                "task_types": entry.module.supported_task_types,
                "health": entry.last_health.status.value,
                "registered_at": entry.registered_at.isoformat(),
                "executions": entry.execution_count,
                "failures": entry.failure_count,
            }
            for entry in self._modules.values()
        ]

    @property
    def module_count(self) -> int:
        return len(self._modules)

    @property
    def task_type_count(self) -> int:
        return len(self._task_type_index)


@lru_cache(maxsize=1)
def get_module_registry() -> ModuleRegistry:
    """Get the singleton module registry."""
    return ModuleRegistry()
