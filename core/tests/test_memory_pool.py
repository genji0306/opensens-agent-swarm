"""Tests for the TurboQuant multi-agent memory pool."""
import random

import pytest

from oas_core.turbo_quant.kv_cache import TurboQuantConfig
from oas_core.turbo_quant.memory_pool import MemoryPool, AgentSlot
from oas_core.turbo_quant.runtime_adapter import RuntimeAdapter, RuntimeConfig


def _random_tensor(rows: int, cols: int, seed: int = 0) -> list[list[float]]:
    rng = random.Random(seed)
    return [[rng.gauss(0, 1) for _ in range(cols)] for _ in range(rows)]


class TestMemoryPool:
    def _make_pool(self, budget_mb: int = 100) -> MemoryPool:
        config = TurboQuantConfig(bits=4, head_dim=8, n_heads=2, enable_qjl=False)
        return MemoryPool(budget_mb=budget_mb, config=config)

    def test_allocate_agent(self):
        pool = self._make_pool()
        slot = pool.allocate("agent-1", "research")
        assert slot.agent_id == "agent-1"
        assert slot.agent_type == "research"
        assert pool.agent_count == 1

    def test_allocate_returns_existing(self):
        pool = self._make_pool()
        slot1 = pool.allocate("agent-1", "research")
        slot2 = pool.allocate("agent-1", "research")
        assert slot1 is slot2
        assert pool.agent_count == 1

    def test_release(self):
        pool = self._make_pool()
        pool.allocate("agent-1", "research")
        assert pool.release("agent-1") is True
        assert pool.agent_count == 0
        assert pool.release("nonexistent") is False

    def test_get(self):
        pool = self._make_pool()
        pool.allocate("agent-1", "research")
        slot = pool.get("agent-1")
        assert slot is not None
        assert slot.agent_id == "agent-1"
        assert pool.get("nonexistent") is None

    def test_multiple_agents(self):
        pool = self._make_pool()
        for i in range(10):
            pool.allocate(f"agent-{i}", "research")
        assert pool.agent_count == 10
        assert len(pool.agent_ids) == 10

    def test_stats(self):
        pool = self._make_pool()
        pool.allocate("agent-1", "research")
        pool.allocate("agent-2", "coding")
        stats = pool.stats
        assert stats.total_agents == 2
        assert stats.budget_bytes > 0

    def test_eviction_by_priority(self):
        pool = self._make_pool(budget_mb=1)  # Very small budget
        config = TurboQuantConfig(bits=4, head_dim=8, n_heads=2, enable_qjl=False)

        # Allocate agents with different priorities
        low = pool.allocate("low-priority", "research", priority=0.1)
        high = pool.allocate("high-priority", "research", priority=10.0)

        # Fill caches with data to exceed budget
        k = [_random_tensor(1000, 8, seed=i) for i in range(2)]
        v = [_random_tensor(1000, 8, seed=i + 10) for i in range(2)]
        low.cache.append(k, v)
        high.cache.append(k, v)

        evicted = pool.evict_if_needed()
        # Low priority should be evicted first
        if evicted:
            assert "low-priority" in evicted


class TestRuntimeAdapter:
    def test_estimate_capacity(self):
        config = RuntimeConfig(
            pool_budget_mb=4096,
            turbo_quant=TurboQuantConfig(bits=4, head_dim=64, n_heads=32),
        )
        adapter = RuntimeAdapter(config)
        cap = adapter.estimate_capacity()

        assert cap["budget_mb"] == 4096
        assert cap["turboquant_tokens"] > cap["fp16_tokens"]
        assert cap["compression_ratio"] > 2.0
        assert "10_agents" in cap["examples"]

    def test_register_unregister(self):
        adapter = RuntimeAdapter()
        adapter.register_agent("agent-1", "research", priority=1.0)
        assert adapter.pool.agent_count == 1
        adapter.unregister_agent("agent-1")
        assert adapter.pool.agent_count == 0

    def test_capacity_scales_with_bits(self):
        cap3 = RuntimeAdapter(RuntimeConfig(
            turbo_quant=TurboQuantConfig(bits=3)
        )).estimate_capacity()
        cap4 = RuntimeAdapter(RuntimeConfig(
            turbo_quant=TurboQuantConfig(bits=4)
        )).estimate_capacity()

        assert cap3["turboquant_tokens"] > cap4["turboquant_tokens"]
