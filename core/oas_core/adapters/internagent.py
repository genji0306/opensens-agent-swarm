"""InternAgent adapter -- deep research graph traversal.

Wraps the InternAgent framework for use in OAS deep research campaigns.
When InternAgent is not installed, all methods return stub ``ResearchResult``
objects with ``available=False`` so the research router can skip gracefully.

Upstream: https://github.com/InternScience/InternAgent
Guard: ``INTERNAGENT_AVAILABLE`` (``try: import internagent``)
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from oas_core.adapters.research_result import ResearchResult

__all__ = [
    "InternAgentAdapter",
    "InternAgentConfig",
    "INTERNAGENT_AVAILABLE",
]

logger = logging.getLogger("oas.adapters.internagent")

# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------
try:
    import internagent  # type: ignore[import-untyped]

    INTERNAGENT_AVAILABLE = True
except ImportError:
    internagent = None  # type: ignore[assignment]
    INTERNAGENT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class InternAgentConfig(BaseModel):
    """Runtime configuration for the InternAgent adapter."""

    enabled: bool = False
    base_dir: Path = Path.home() / ".darklab" / "internagent"
    max_depth: int = 3
    timeout: float = 300.0


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class InternAgentAdapter:
    """Wraps InternAgent for OAS deep research graph traversal.

    When ``INTERNAGENT_AVAILABLE`` is ``False`` or ``config.enabled`` is
    ``False``, all methods return stub results with ``available=False`` so
    the research router can skip gracefully.

    In production, the adapter can be wired with an ``inference_fn`` that
    delegates LLM calls to DEV compute via ``BorrowedInferenceClient``.

    Parameters
    ----------
    config:
        Optional configuration.  Defaults are conservative (depth 3,
        300 s timeout).
    inference_fn:
        Optional callback for LLM calls inside the research graph.
        Wired to ``BorrowedInferenceClient.borrow()`` in production.
    """

    def __init__(
        self,
        config: InternAgentConfig | None = None,
        *,
        inference_fn: Any | None = None,
    ) -> None:
        self.config = config or InternAgentConfig()
        self.available = INTERNAGENT_AVAILABLE and self.config.enabled
        self._inference_fn = inference_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        query: str,
        *,
        context: str = "",
        max_depth: int | None = None,
        request_id: str = "",
        agent_name: str = "internagent",
        device: str = "leader",
    ) -> ResearchResult:
        """Run an InternAgent deep research graph traversal.

        When unavailable, returns a stub ``ResearchResult`` with
        ``available=False``.  When available, delegates to InternAgent in
        ``asyncio.to_thread()``.

        Parameters
        ----------
        query:
            The research question.
        context:
            Optional prior context to augment the query.
        max_depth:
            Override the default max-depth from config.
        request_id:
            OAS request identifier for DRVP event grouping.
        agent_name:
            Agent name for DRVP events.
        device:
            Device name for DRVP events.
        """
        depth = max_depth or self.config.max_depth
        effective_query = f"{context}\n\n{query}".strip() if context else query

        # Emit start event
        await self._emit_event(
            "research.backend.started",
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "backend": "internagent",
                "query": query[:200],
                "max_depth": depth,
            },
        )

        if not self.available:
            logger.debug("internagent_unavailable: returning stub result")
            result = ResearchResult(
                query=query,
                output="",
                sources=[],
                available=False,
                backend="internagent",
                duration_seconds=0.0,
                metadata={"reason": "internagent not available or not enabled"},
            )
            await self._emit_event(
                "research.backend.completed",
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={
                    "backend": "internagent",
                    "available": False,
                    "output_length": 0,
                },
            )
            return result

        t0 = time.monotonic()

        try:
            output, sources_raw = await asyncio.to_thread(
                self._run_sync, effective_query, depth
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.warning("internagent_run_failed: %s", exc)
            await self._emit_event(
                "research.backend.failed",
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={
                    "backend": "internagent",
                    "error": str(exc)[:300],
                    "duration_seconds": round(elapsed, 2),
                },
            )
            return ResearchResult(
                query=query,
                output=f"InternAgent error: {exc}",
                sources=[],
                available=True,
                backend="internagent",
                duration_seconds=round(elapsed, 2),
                metadata={"error": str(exc)},
            )

        elapsed = time.monotonic() - t0

        # Normalise sources into list[dict]
        sources: list[dict[str, Any]] = []
        if isinstance(sources_raw, list):
            for s in sources_raw:
                if isinstance(s, dict):
                    sources.append(s)
                else:
                    sources.append({"raw": str(s)})

        result = ResearchResult(
            query=query,
            output=str(output),
            sources=sources,
            available=True,
            backend="internagent",
            duration_seconds=round(elapsed, 2),
            metadata={"depth": depth},
        )

        await self._emit_event(
            "research.backend.completed",
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "backend": "internagent",
                "available": True,
                "output_length": len(result.output),
                "source_count": len(sources),
                "duration_seconds": round(elapsed, 2),
            },
        )

        logger.info(
            "internagent_run_complete: query=%s output_len=%d sources=%d elapsed=%.1fs",
            query[:80],
            len(result.output),
            len(sources),
            elapsed,
        )
        return result

    async def health(self) -> dict[str, Any]:
        """Check if InternAgent is installed and configured.

        Returns a dict with ``installed``, ``enabled``, ``available``,
        and ``base_dir`` keys.
        """
        base_exists = self.config.base_dir.exists() if self.config.base_dir else False
        return {
            "installed": INTERNAGENT_AVAILABLE,
            "enabled": self.config.enabled,
            "available": self.available,
            "base_dir": str(self.config.base_dir),
            "base_dir_exists": base_exists,
            "max_depth": self.config.max_depth,
            "timeout": self.config.timeout,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_sync(self, query: str, max_depth: int) -> tuple[str, list[Any]]:
        """Synchronous InternAgent execution (called via ``asyncio.to_thread``).

        Returns ``(output_text, sources_list)``.
        """
        assert internagent is not None  # guarded by self.available

        agent = internagent.ResearchAgent(
            work_dir=str(self.config.base_dir),
            max_depth=max_depth,
            timeout=self.config.timeout,
        )
        result = agent.run(query)

        output = (
            getattr(result, "output", "")
            or getattr(result, "text", "")
            or str(result)
        )
        sources = (
            getattr(result, "sources", [])
            or getattr(result, "references", [])
            or []
        )
        return output, sources

    @staticmethod
    async def _emit_event(
        event_type_str: str,
        *,
        request_id: str,
        agent_name: str,
        device: str,
        payload: dict[str, Any],
    ) -> None:
        """Emit a DRVP event (best-effort, never raises)."""
        try:
            from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

            et = DRVPEventType(event_type_str)
            await emit(
                DRVPEvent(
                    event_type=et,
                    request_id=request_id,
                    agent_name=agent_name,
                    device=device,
                    payload=payload,
                )
            )
        except Exception:
            pass  # DRVP is best-effort
