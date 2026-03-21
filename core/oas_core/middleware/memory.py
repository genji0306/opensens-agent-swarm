"""OpenViking memory middleware.

Before execution: searches for relevant context at L1 (overview) and
injects it into the task payload as ``prior_context``.
After execution: stores findings at L2 (full detail) under
``viking://agent/memories/cases/{task_id}``.
"""

from __future__ import annotations

import logging
from typing import Any

from oas_core.memory import SCOPE_AGENT, MemoryClient, MemoryError
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

__all__ = ["MemoryMiddleware"]

logger = logging.getLogger("oas.middleware.memory")


class MemoryMiddleware:
    """Middleware that loads/stores context via OpenViking.

    Usage::

        mw = MemoryMiddleware(memory_client)
        context = await mw.pre_load(request_id, agent_name, device, query)
        # ... agent work ...
        await mw.post_store(request_id, agent_name, device, task_id, findings)
    """

    def __init__(
        self,
        memory: MemoryClient | None,
        *,
        search_limit: int = 5,
        score_threshold: float = 0.5,
    ):
        self.memory = memory
        self._search_limit = search_limit
        self._score_threshold = score_threshold

    async def pre_load(
        self,
        request_id: str,
        agent_name: str,
        device: str,
        query: str,
    ) -> list[dict[str, Any]]:
        """Search for relevant prior context before agent execution.

        Returns a list of context snippets (L1 overviews) that the agent
        can use to inform its work.
        """
        if not self.memory:
            return []

        await emit(DRVPEvent(
            event_type=DRVPEventType.MEMORY_READ,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"query": query, "scope": SCOPE_AGENT},
        ))

        try:
            results = await self.memory.search(
                query=query,
                target_uri=SCOPE_AGENT,
                limit=self._search_limit,
                score_threshold=self._score_threshold,
            )
            logger.info(
                "memory_pre_load",
                extra={"query": query[:80], "results": len(results)},
            )
            return results
        except MemoryError as e:
            logger.warning("memory_pre_load_failed", extra={"error": str(e)})
            return []

    async def post_store(
        self,
        request_id: str,
        agent_name: str,
        device: str,
        task_id: str,
        findings: dict[str, Any],
    ) -> None:
        """Store agent findings as a new memory case after execution.

        Writes to ``viking://agent/memories/cases/{task_id}`` with the
        full result as L2 content.
        """
        if not self.memory:
            return

        uri = f"{SCOPE_AGENT}/memories/cases/{task_id}"
        content = {
            "agent_name": agent_name,
            "task_id": task_id,
            "request_id": request_id,
            **findings,
        }

        await emit(DRVPEvent(
            event_type=DRVPEventType.MEMORY_WRITE,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"uri": uri, "keys": list(findings.keys())},
        ))

        try:
            await self.memory.write(uri, content, level=2)
            logger.info("memory_post_store", extra={"uri": uri, "task_id": task_id})
        except MemoryError as e:
            logger.warning("memory_post_store_failed", extra={"error": str(e)})
