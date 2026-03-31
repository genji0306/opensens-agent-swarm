"""Multi-agent compressed memory pool.

Manages compressed KV caches across multiple agents with:
- Per-agent memory slots with configurable budgets
- Priority-based eviction when pool is full
- Shared context region for cross-agent knowledge
- Statistics and monitoring
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from oas_core.turbo_quant.kv_cache import CompressedKVCache, TurboQuantConfig, CacheStats

__all__ = ["MemoryPool", "AgentSlot", "PoolStats"]

logger = logging.getLogger("oas.turbo_quant.memory_pool")


@dataclass
class AgentSlot:
    """A memory slot for a single agent within the pool."""

    agent_id: str
    agent_type: str  # "research" | "coding" | "creative" etc.
    cache: CompressedKVCache
    priority: float = 1.0  # Higher = harder to evict
    last_access: float = field(default_factory=time.monotonic)
    access_count: int = 0

    def touch(self) -> None:
        """Update access metadata."""
        self.last_access = time.monotonic()
        self.access_count += 1


@dataclass
class PoolStats:
    """Aggregate statistics for the memory pool."""

    total_agents: int = 0
    total_memory_bytes: int = 0
    budget_bytes: int = 0
    utilization: float = 0.0
    total_tokens: int = 0
    avg_compression_ratio: float = 0.0
    agents: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_agents": self.total_agents,
            "total_memory_mb": round(self.total_memory_bytes / (1024 * 1024), 2),
            "budget_mb": round(self.budget_bytes / (1024 * 1024), 2),
            "utilization_pct": round(self.utilization * 100, 1),
            "total_tokens": self.total_tokens,
            "avg_compression_ratio": round(self.avg_compression_ratio, 2),
            "agents": self.agents,
        }


class MemoryPool:
    """Multi-agent compressed KV cache memory pool.

    Allocates and manages compressed KV caches for multiple agents,
    with a global memory budget and priority-based eviction.

    Usage::

        pool = MemoryPool(budget_mb=4096)  # 4GB pool

        # Allocate a slot for an agent
        slot = pool.allocate("research-agent-1", "research")

        # Agent uses its cache
        slot.cache.append(k_per_head, v_per_head)
        slot.touch()

        # Check pool status
        stats = pool.stats

        # Evict lowest-priority agent when over budget
        pool.evict_if_needed()
    """

    def __init__(
        self,
        budget_mb: int = 4096,
        config: TurboQuantConfig | None = None,
    ):
        self.budget_bytes = budget_mb * 1024 * 1024
        self.config = config or TurboQuantConfig()
        self._slots: dict[str, AgentSlot] = {}

    def allocate(self, agent_id: str, agent_type: str = "research", priority: float = 1.0) -> AgentSlot:
        """Allocate a compressed KV cache slot for an agent.

        If the agent already has a slot, returns the existing one.
        """
        if agent_id in self._slots:
            slot = self._slots[agent_id]
            slot.touch()
            return slot

        cache = CompressedKVCache(self.config)
        slot = AgentSlot(
            agent_id=agent_id,
            agent_type=agent_type,
            cache=cache,
            priority=priority,
        )
        self._slots[agent_id] = slot

        logger.debug("pool_allocated", agent_id=agent_id, agent_type=agent_type)
        return slot

    def release(self, agent_id: str) -> bool:
        """Release an agent's memory slot.

        Returns True if the slot existed and was released.
        """
        slot = self._slots.pop(agent_id, None)
        if slot:
            slot.cache.clear()
            logger.debug("pool_released", agent_id=agent_id)
            return True
        return False

    def get(self, agent_id: str) -> AgentSlot | None:
        """Get an agent's slot, or None if not allocated."""
        slot = self._slots.get(agent_id)
        if slot:
            slot.touch()
        return slot

    def evict_if_needed(self) -> list[str]:
        """Evict lowest-priority agents until memory is within budget.

        Returns list of evicted agent IDs.
        """
        evicted: list[str] = []
        total = self._total_memory()

        while total > self.budget_bytes and self._slots:
            # Find lowest priority, oldest access
            victim_id = min(
                self._slots,
                key=lambda aid: (self._slots[aid].priority, -self._slots[aid].last_access),
            )
            victim = self._slots[victim_id]
            victim_mem = victim.cache.stats.memory_bytes

            self.release(victim_id)
            evicted.append(victim_id)
            total -= victim_mem

            logger.info("pool_evicted", agent_id=victim_id, freed_bytes=victim_mem)

        return evicted

    def _total_memory(self) -> int:
        """Compute total memory usage across all slots."""
        return sum(slot.cache.stats.memory_bytes for slot in self._slots.values())

    @property
    def stats(self) -> PoolStats:
        """Compute aggregate pool statistics."""
        total_mem = 0
        total_tokens = 0
        ratios: list[float] = []
        agent_stats: list[dict[str, Any]] = []

        for slot in self._slots.values():
            cs = slot.cache.stats
            total_mem += cs.memory_bytes
            total_tokens += cs.seq_len
            if cs.compression_ratio > 0:
                ratios.append(cs.compression_ratio)
            agent_stats.append({
                "agent_id": slot.agent_id,
                "agent_type": slot.agent_type,
                "seq_len": cs.seq_len,
                "memory_mb": round(cs.memory_bytes / (1024 * 1024), 2),
                "compression_ratio": round(cs.compression_ratio, 2),
                "priority": slot.priority,
                "access_count": slot.access_count,
            })

        return PoolStats(
            total_agents=len(self._slots),
            total_memory_bytes=total_mem,
            budget_bytes=self.budget_bytes,
            utilization=total_mem / self.budget_bytes if self.budget_bytes > 0 else 0.0,
            total_tokens=total_tokens,
            avg_compression_ratio=sum(ratios) / len(ratios) if ratios else 0.0,
            agents=agent_stats,
        )

    @property
    def agent_count(self) -> int:
        return len(self._slots)

    @property
    def agent_ids(self) -> list[str]:
        return sorted(self._slots.keys())
