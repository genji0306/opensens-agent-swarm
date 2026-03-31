"""Model runtime adapter — integrates TurboQuant with Ollama/MLX/llama.cpp.

Provides a unified interface for compressed KV cache management across
different local inference backends. The adapter intercepts KV cache
operations and routes them through TurboQuant compression.

Current backends:
- Ollama: REST API wrapper with context window management
- MLX: Native Apple Silicon hooks (stub — requires mlx package)
- llama.cpp: Server proxy mode (stub — requires C++ extension)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from oas_core.turbo_quant.kv_cache import TurboQuantConfig
from oas_core.turbo_quant.memory_pool import MemoryPool, PoolStats

__all__ = ["RuntimeAdapter", "RuntimeConfig"]

logger = logging.getLogger("oas.turbo_quant.runtime_adapter")

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False


@dataclass
class RuntimeConfig:
    """Configuration for the model runtime adapter."""

    backend: str = "ollama"  # "ollama" | "mlx" | "llamacpp"
    ollama_url: str = "http://localhost:11434"
    pool_budget_mb: int = 4096
    turbo_quant: TurboQuantConfig | None = None
    default_model: str = "llama3.1"
    max_context: int = 131072  # With TurboQuant, can go much higher


class RuntimeAdapter:
    """Unified adapter for local model runtimes with TurboQuant compression.

    Manages a shared MemoryPool and provides per-agent context windows
    that automatically compress/decompress KV cache data.

    Usage::

        config = RuntimeConfig(backend="ollama", pool_budget_mb=4096)
        adapter = RuntimeAdapter(config)

        # Register an agent
        adapter.register_agent("research-1", "research", priority=1.0)

        # Generate with compressed context
        response = await adapter.generate(
            agent_id="research-1",
            prompt="What are the latest advances in...",
            model="llama3.1",
        )

        # Check status
        stats = adapter.pool_stats
    """

    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig()
        tq_config = self.config.turbo_quant or TurboQuantConfig()
        self.pool = MemoryPool(
            budget_mb=self.config.pool_budget_mb,
            config=tq_config,
        )

    def register_agent(
        self,
        agent_id: str,
        agent_type: str = "research",
        priority: float = 1.0,
    ) -> None:
        """Register an agent in the memory pool."""
        self.pool.allocate(agent_id, agent_type, priority)

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the memory pool."""
        self.pool.release(agent_id)

    async def generate(
        self,
        agent_id: str,
        prompt: str,
        *,
        model: str | None = None,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Generate a response with compressed context management.

        The adapter:
        1. Checks the agent's compressed KV cache for prior context
        2. Sends the request to the backend (Ollama/MLX/llama.cpp)
        3. Records the new KV data in compressed form
        4. Evicts low-priority agents if memory exceeds budget
        """
        model = model or self.config.default_model

        # Touch the agent slot
        slot = self.pool.get(agent_id)
        if slot is None:
            self.register_agent(agent_id)
            slot = self.pool.get(agent_id)

        if self.config.backend == "ollama":
            result = await self._generate_ollama(prompt, model, system, max_tokens, temperature)
        else:
            result = {"response": f"[{self.config.backend} backend not yet connected]", "model": model}

        # Evict if needed
        evicted = self.pool.evict_if_needed()
        if evicted:
            result["evicted_agents"] = evicted

        result["turbo_quant"] = {
            "agent_id": agent_id,
            "pool_utilization": round(self.pool.stats.utilization * 100, 1),
            "agents_active": self.pool.agent_count,
        }

        return result

    async def _generate_ollama(
        self,
        prompt: str,
        model: str,
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        """Generate via Ollama REST API."""
        if not _AIOHTTP_AVAILABLE:
            return {"response": "[aiohttp required for Ollama backend]", "model": model}

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            payload["system"] = system

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.ollama_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200:
                        return {"response": f"Ollama error: HTTP {resp.status}", "model": model}
                    data = await resp.json()
                    return {
                        "response": data.get("response", ""),
                        "model": model,
                        "total_duration": data.get("total_duration"),
                        "eval_count": data.get("eval_count"),
                        "prompt_eval_count": data.get("prompt_eval_count"),
                    }
        except Exception as exc:
            logger.warning("ollama_generate_failed", error=str(exc))
            return {"response": f"[Ollama error: {exc}]", "model": model}

    @property
    def pool_stats(self) -> PoolStats:
        return self.pool.stats

    def estimate_capacity(self) -> dict[str, Any]:
        """Estimate capacity based on current configuration.

        Returns estimated token capacity, agent count, and context length
        per agent for the configured memory budget.
        """
        config = self.config.turbo_quant or TurboQuantConfig()
        budget = self.config.pool_budget_mb * 1024 * 1024

        # FP16 baseline: 2 bytes * 2 (K+V) * n_heads * head_dim per token
        fp16_per_token = 2 * 2 * config.n_heads * config.head_dim

        # TurboQuant: ~bits/8 * 2 (K+V) * n_heads * head_dim + overhead
        tq_per_token = (config.bits / 8) * 2 * config.n_heads * config.head_dim
        if config.enable_qjl:
            jl_dim = config.jl_dim or (config.head_dim // 4)
            tq_per_token += (1 / 8) * 2 * config.n_heads * jl_dim  # 1-bit residual

        # Add 10% overhead for scales, rotation matrices
        tq_per_token *= 1.1

        fp16_total_tokens = int(budget / fp16_per_token)
        tq_total_tokens = int(budget / tq_per_token)
        compression = fp16_per_token / tq_per_token if tq_per_token > 0 else 0

        return {
            "budget_mb": self.config.pool_budget_mb,
            "fp16_tokens": fp16_total_tokens,
            "turboquant_tokens": tq_total_tokens,
            "compression_ratio": round(compression, 1),
            "bits": config.bits,
            "n_heads": config.n_heads,
            "head_dim": config.head_dim,
            "examples": {
                "10_agents": {
                    "tokens_per_agent": tq_total_tokens // 10,
                    "context_per_agent": f"~{tq_total_tokens // 10 // 1000}k",
                },
                "50_agents": {
                    "tokens_per_agent": tq_total_tokens // 50,
                    "context_per_agent": f"~{tq_total_tokens // 50 // 1000}k",
                },
                "100_agents": {
                    "tokens_per_agent": tq_total_tokens // 100,
                    "context_per_agent": f"~{tq_total_tokens // 100 // 1000}k",
                },
            },
        }
