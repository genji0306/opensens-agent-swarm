"""Tinker cloud training API wrapper.

Wraps the Tinker API for LoRA-based RL training operations. Handles
job submission, status polling, checkpoint download, and error recovery.

When Tinker is unavailable, training operations gracefully degrade
(agents continue serving on the base model).
"""
from __future__ import annotations

import logging
import time
from typing import Any

__all__ = ["TinkerClient", "CircuitBreaker", "TINKER_AVAILABLE"]

logger = logging.getLogger("oas.rl.tinker_client")

# Optional dependency — aiohttp for async HTTP
try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

TINKER_AVAILABLE = _AIOHTTP_AVAILABLE


class CircuitBreaker:
    """Simple circuit breaker for external API calls.

    States:
    - CLOSED: normal operation, requests pass through
    - OPEN: too many failures, requests are rejected immediately
    - HALF_OPEN: after cooldown, allow one test request

    Usage::

        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        if not cb.allow_request():
            raise RuntimeError("Tinker API circuit breaker is open")
        try:
            result = await tinker_call()
            cb.record_success()
        except Exception:
            cb.record_failure()
            raise
    """

    def __init__(self, *, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._state: str = "closed"  # "closed" | "open" | "half_open"

    @property
    def state(self) -> str:
        if self._state == "open":
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = "half_open"
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        s = self.state
        if s == "closed":
            return True
        if s == "half_open":
            return True  # Allow one test request
        return False  # open

    def record_success(self) -> None:
        """Record a successful request."""
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                "circuit_breaker_opened",
                failures=self._failure_count,
                recovery_timeout=self.recovery_timeout,
            )

    def reset(self) -> None:
        """Force reset to closed state."""
        self._failure_count = 0
        self._state = "closed"


class TinkerClient:
    """Async client for the Tinker cloud training API.

    Usage::

        client = TinkerClient(api_key="tk-...", base_url="https://api.tinker.ai")
        job = await client.submit_training_job(
            model="Qwen/Qwen3-4B-Instruct-2507",
            method="combine",
            lora_rank=32,
            rollout_data=[...],
        )
        status = await client.get_job_status(job["job_id"])
        if status["state"] == "completed":
            checkpoint = await client.download_checkpoint(job["job_id"])
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.thinkingmachines.ai/tinker/v1",
        timeout: float = 300.0,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    async def submit_training_job(
        self,
        model: str,
        method: str = "combine",
        lora_rank: int = 32,
        batch_size: int = 16,
        rollout_data: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit a LoRA training job to Tinker cloud.

        Returns job metadata including job_id for status polling.
        """
        if not TINKER_AVAILABLE:
            raise RuntimeError("aiohttp required for Tinker client")
        if not self.circuit_breaker.allow_request():
            raise RuntimeError("Tinker API circuit breaker is open — too many recent failures")

        payload = {
            "model": model,
            "method": method,
            "lora_rank": lora_rank,
            "batch_size": batch_size,
            "rollout_data": rollout_data or [],
            **kwargs,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/training/jobs",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Poll the status of a training job.

        Returns dict with "state" (queued|training|completed|failed),
        "progress" (0.0-1.0), and "metrics" (loss, etc.).
        """
        if not TINKER_AVAILABLE:
            raise RuntimeError("aiohttp required for Tinker client")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/training/jobs/{job_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def download_checkpoint(self, job_id: str) -> dict[str, Any]:
        """Download the LoRA checkpoint from a completed training job.

        Returns checkpoint metadata including download URL and adapter config.
        """
        if not TINKER_AVAILABLE:
            raise RuntimeError("aiohttp required for Tinker client")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/training/jobs/{job_id}/checkpoint",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def health_check(self) -> bool:
        """Check if the Tinker API is reachable."""
        if not TINKER_AVAILABLE:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
