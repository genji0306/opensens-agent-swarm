"""OpenClaw-RL API proxy client.

Wraps the OpenClaw-RL proxy server (port 30000) which serves as an
OpenAI-compatible API endpoint with RL training headers for session
tracking and rollout collection.

The proxy selects the correct LoRA adapter based on the X-Agent-Name
header injected by the rollout middleware.
"""
from __future__ import annotations

import logging
from typing import Any

__all__ = ["OpenClawRLAdapter", "OPENCLAW_RL_AVAILABLE"]

logger = logging.getLogger("oas.adapters.openclaw_rl")

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

OPENCLAW_RL_AVAILABLE = _AIOHTTP_AVAILABLE


class OpenClawRLAdapter:
    """Client for the OpenClaw-RL API proxy.

    The proxy serves RL-trained LoRA-adapted models as an OpenAI-compatible
    API. It intercepts conversations for rollout collection and selects
    the appropriate LoRA adapter per agent.

    Usage::

        adapter = OpenClawRLAdapter(proxy_url="http://localhost:30000/v1")
        response = await adapter.chat_completion(
            agent_name="research",
            messages=[{"role": "user", "content": "..."}],
            session_id="req-123",
        )
    """

    def __init__(
        self,
        proxy_url: str,
        *,
        api_key: str = "darklab-internal",
        timeout: float = 120.0,
    ):
        self.proxy_url = proxy_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def chat_completion(
        self,
        agent_name: str,
        messages: list[dict[str, str]],
        *,
        session_id: str = "",
        turn_type: str = "main",
        session_done: bool = False,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Send a chat completion request through the RL proxy.

        The proxy adds OpenClaw-RL session tracking headers and routes
        to the correct LoRA adapter.
        """
        if not OPENCLAW_RL_AVAILABLE:
            raise RuntimeError("aiohttp required for OpenClaw-RL adapter")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Agent-Name": agent_name,
            "X-Session-Id": session_id,
            "X-Turn-Type": turn_type,
        }
        if session_done:
            headers["X-Session-Done"] = "true"

        payload: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if model:
            payload["model"] = model

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.proxy_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def list_adapters(self) -> list[dict[str, Any]]:
        """List available LoRA adapters on the proxy."""
        if not OPENCLAW_RL_AVAILABLE:
            raise RuntimeError("aiohttp required for OpenClaw-RL adapter")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.proxy_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("data", [])

    async def health_check(self) -> bool:
        """Check if the OpenClaw-RL proxy is reachable."""
        if not OPENCLAW_RL_AVAILABLE:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.proxy_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
