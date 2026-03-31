"""Contract tests for OAS-1 module capability protocol and registry.

Tests cover:
- ModuleCapability protocol compliance
- Module registration and discovery
- Health checking
- Cost-based module selection
- Task execution via registry
- Unregistration
"""

from __future__ import annotations

import pytest
from typing import Any

from oas_core.registry.capability import (
    ModuleCapability,
    ModuleHealth,
    ModuleStatus,
    CostEstimate,
)
from oas_core.registry.module_registry import ModuleRegistry


# ── Test Fixtures ────────────────────────────────────────────


class MockResearchModule:
    """Mock module implementing ModuleCapability for testing."""

    @property
    def name(self) -> str:
        return "mock_research"

    @property
    def supported_task_types(self) -> list[str]:
        return ["research", "literature", "deep_research"]

    async def health(self) -> ModuleHealth:
        return ModuleHealth(status=ModuleStatus.HEALTHY, latency_ms=5.0)

    async def estimate_cost(self, task_type: str, payload: dict[str, Any]) -> CostEstimate:
        return CostEstimate(estimated_cost_usd=0.05, estimated_duration_seconds=10.0)

    async def execute(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"output": f"Mock result for {task_type}", "status": "ok"}


class MockSimulationModule:
    """Mock simulation module — slightly more expensive."""

    @property
    def name(self) -> str:
        return "mock_simulation"

    @property
    def supported_task_types(self) -> list[str]:
        return ["simulate", "analyze"]

    async def health(self) -> ModuleHealth:
        return ModuleHealth(status=ModuleStatus.HEALTHY, latency_ms=10.0)

    async def estimate_cost(self, task_type: str, payload: dict[str, Any]) -> CostEstimate:
        return CostEstimate(estimated_cost_usd=0.10, estimated_duration_seconds=30.0)

    async def execute(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"output": f"Simulation result for {task_type}", "status": "ok"}


class MockUnhealthyModule:
    """Module that always reports unhealthy."""

    @property
    def name(self) -> str:
        return "mock_unhealthy"

    @property
    def supported_task_types(self) -> list[str]:
        return ["research"]

    async def health(self) -> ModuleHealth:
        return ModuleHealth(status=ModuleStatus.UNHEALTHY, error="Connection refused")

    async def estimate_cost(self, task_type: str, payload: dict[str, Any]) -> CostEstimate:
        return CostEstimate()

    async def execute(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Module is unhealthy")


class MockCheapResearchModule:
    """Cheaper alternative for research tasks."""

    @property
    def name(self) -> str:
        return "mock_cheap_research"

    @property
    def supported_task_types(self) -> list[str]:
        return ["research"]

    async def health(self) -> ModuleHealth:
        return ModuleHealth(status=ModuleStatus.HEALTHY)

    async def estimate_cost(self, task_type: str, payload: dict[str, Any]) -> CostEstimate:
        return CostEstimate(estimated_cost_usd=0.01)

    async def execute(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"output": "Cheap research result", "status": "ok"}


# ── Protocol Compliance ──────────────────────────────────────


class TestModuleCapabilityProtocol:
    def test_mock_implements_protocol(self):
        mod = MockResearchModule()
        assert isinstance(mod, ModuleCapability)

    def test_mock_simulation_implements_protocol(self):
        mod = MockSimulationModule()
        assert isinstance(mod, ModuleCapability)


# ── Module Registry ──────────────────────────────────────────


class TestModuleRegistry:
    def test_register(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        assert reg.module_count == 1

    def test_register_multiple(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        reg.register(MockSimulationModule())
        assert reg.module_count == 2
        assert reg.task_type_count == 5  # research, literature, deep_research, simulate, analyze

    def test_get(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        mod = reg.get("mock_research")
        assert mod is not None
        assert mod.name == "mock_research"

    def test_get_nonexistent(self):
        reg = ModuleRegistry()
        assert reg.get("nonexistent") is None

    def test_unregister(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        assert reg.unregister("mock_research") is True
        assert reg.module_count == 0
        assert reg.get("mock_research") is None

    def test_unregister_nonexistent(self):
        reg = ModuleRegistry()
        assert reg.unregister("nonexistent") is False

    def test_find_by_task_type(self):
        reg = ModuleRegistry()
        mod = MockResearchModule()
        reg.register(mod)
        # Mark as healthy first
        reg._modules["mock_research"].last_health = ModuleHealth(status=ModuleStatus.HEALTHY)
        found = reg.find_by_task_type("research")
        assert len(found) == 1
        assert found[0].name == "mock_research"

    def test_find_by_task_type_excludes_unhealthy(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        reg.register(MockUnhealthyModule())
        # Set health status
        reg._modules["mock_research"].last_health = ModuleHealth(status=ModuleStatus.HEALTHY)
        reg._modules["mock_unhealthy"].last_health = ModuleHealth(status=ModuleStatus.UNHEALTHY)
        found = reg.find_by_task_type("research")
        names = [m.name for m in found]
        assert "mock_research" in names
        assert "mock_unhealthy" not in names

    def test_find_by_task_type_no_matches(self):
        reg = ModuleRegistry()
        assert reg.find_by_task_type("nonexistent") == []

    def test_list_modules(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        reg.register(MockSimulationModule())
        modules = reg.list_modules()
        assert len(modules) == 2
        names = {m["name"] for m in modules}
        assert names == {"mock_research", "mock_simulation"}

    def test_replace_module(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        reg.register(MockResearchModule())  # Replace
        assert reg.module_count == 1


# ── Health Checking ──────────────────────────────────────────


class TestModuleHealth:
    @pytest.mark.asyncio
    async def test_check_health(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        health = await reg.check_health("mock_research")
        assert health.status == ModuleStatus.HEALTHY
        assert health.latency_ms == 5.0

    @pytest.mark.asyncio
    async def test_check_health_unknown_module(self):
        reg = ModuleRegistry()
        health = await reg.check_health("nonexistent")
        assert health.status == ModuleStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_check_all_health(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        reg.register(MockSimulationModule())
        results = await reg.check_all_health()
        assert len(results) == 2
        assert results["mock_research"].status == ModuleStatus.HEALTHY
        assert results["mock_simulation"].status == ModuleStatus.HEALTHY


# ── Cost-Based Selection ─────────────────────────────────────


class TestBestModuleSelection:
    @pytest.mark.asyncio
    async def test_best_module_single_candidate(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        reg._modules["mock_research"].last_health = ModuleHealth(status=ModuleStatus.HEALTHY)
        best = await reg.best_module_for("research", {})
        assert best is not None
        assert best.name == "mock_research"

    @pytest.mark.asyncio
    async def test_best_module_picks_cheapest(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())  # $0.05
        reg.register(MockCheapResearchModule())  # $0.01
        reg._modules["mock_research"].last_health = ModuleHealth(status=ModuleStatus.HEALTHY)
        reg._modules["mock_cheap_research"].last_health = ModuleHealth(status=ModuleStatus.HEALTHY)
        best = await reg.best_module_for("research", {})
        assert best is not None
        assert best.name == "mock_cheap_research"

    @pytest.mark.asyncio
    async def test_best_module_no_candidates(self):
        reg = ModuleRegistry()
        best = await reg.best_module_for("nonexistent", {})
        assert best is None


# ── Execution via Registry ───────────────────────────────────


class TestRegistryExecution:
    @pytest.mark.asyncio
    async def test_execute_via_registry(self):
        reg = ModuleRegistry()
        reg.register(MockResearchModule())
        reg._modules["mock_research"].last_health = ModuleHealth(status=ModuleStatus.HEALTHY)
        result = await reg.execute("research", {"query": "test"})
        assert result["status"] == "ok"
        assert reg._modules["mock_research"].execution_count == 1

    @pytest.mark.asyncio
    async def test_execute_unknown_task_type_raises(self):
        reg = ModuleRegistry()
        with pytest.raises(KeyError, match="No module registered"):
            await reg.execute("nonexistent", {})

    @pytest.mark.asyncio
    async def test_execute_tracks_failures(self):
        reg = ModuleRegistry()
        reg.register(MockUnhealthyModule())
        reg._modules["mock_unhealthy"].last_health = ModuleHealth(status=ModuleStatus.HEALTHY)  # Force healthy to test execution failure
        with pytest.raises(RuntimeError):
            await reg.execute("research", {})
        assert reg._modules["mock_unhealthy"].failure_count == 1
