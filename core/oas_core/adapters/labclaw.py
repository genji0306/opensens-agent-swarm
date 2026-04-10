"""LabClaw adapter -- lab-loop iterative research automation.

Wraps the LabClaw research framework for use in OAS research campaigns.
When LabClaw is not installed, all methods return stub ``ResearchResult``
objects with ``available=False`` so the research router can skip gracefully.

Upstream: https://github.com/wu-yc/LabClaw
Guard: ``LABCLAW_AVAILABLE`` (``try: import labclaw``)
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
    "LabClawAdapter",
    "LabClawConfig",
    "LABCLAW_AVAILABLE",
]

logger = logging.getLogger("oas.adapters.labclaw")

# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------
try:
    import labclaw  # type: ignore[import-untyped]

    LABCLAW_AVAILABLE = True
except ImportError:
    labclaw = None  # type: ignore[assignment]
    LABCLAW_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class LabClawConfig(BaseModel):
    """Runtime configuration for the LabClaw adapter."""

    enabled: bool = False
    base_dir: Path = Path.home() / ".darklab" / "labclaw"
    max_iterations: int = 5
    timeout: float = 300.0


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class LabClawAdapter:
    """Wraps LabClaw for OAS research pipeline integration.

    When ``LABCLAW_AVAILABLE`` is ``False`` or ``config.enabled`` is ``False``,
    all methods return stub results with ``available=False`` so the research
    router can skip gracefully.

    In production, the adapter can be wired with an ``inference_fn`` that
    delegates LLM calls to DEV compute via ``BorrowedInferenceClient``.

    Parameters
    ----------
    config:
        Optional configuration.  Defaults are conservative (5 iterations,
        300 s timeout).
    inference_fn:
        Optional callback for LLM calls inside the lab loop.  Wired to
        ``BorrowedInferenceClient.borrow()`` in production.
    """

    def __init__(
        self,
        config: LabClawConfig | None = None,
        *,
        inference_fn: Any | None = None,
    ) -> None:
        self.config = config or LabClawConfig()
        self.available = LABCLAW_AVAILABLE and self.config.enabled
        self._inference_fn = inference_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        query: str,
        *,
        context: str = "",
        max_iterations: int | None = None,
        request_id: str = "",
        agent_name: str = "labclaw",
        device: str = "leader",
    ) -> ResearchResult:
        """Run a LabClaw research loop on the given query.

        When unavailable, returns a stub ``ResearchResult`` with
        ``available=False``.  When available, delegates to LabClaw in
        ``asyncio.to_thread()``.

        Parameters
        ----------
        query:
            The research question.
        context:
            Optional prior context to augment the query.
        max_iterations:
            Override the default max-iteration count from config.
        request_id:
            OAS request identifier for DRVP event grouping.
        agent_name:
            Agent name for DRVP events.
        device:
            Device name for DRVP events.
        """
        iterations = max_iterations or self.config.max_iterations
        effective_query = f"{context}\n\n{query}".strip() if context else query

        # Emit start event
        await self._emit_event(
            "research.backend.started",
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "backend": "labclaw",
                "query": query[:200],
                "max_iterations": iterations,
            },
        )

        if not self.available:
            logger.debug("labclaw_unavailable: returning stub result")
            result = ResearchResult(
                query=query,
                output="",
                sources=[],
                available=False,
                backend="labclaw",
                duration_seconds=0.0,
                metadata={"reason": "labclaw not available or not enabled"},
            )
            await self._emit_event(
                "research.backend.completed",
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={
                    "backend": "labclaw",
                    "available": False,
                    "output_length": 0,
                },
            )
            return result

        t0 = time.monotonic()

        try:
            output, sources_raw = await asyncio.to_thread(
                self._run_sync, effective_query, iterations
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.warning("labclaw_run_failed: %s", exc)
            await self._emit_event(
                "research.backend.failed",
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={
                    "backend": "labclaw",
                    "error": str(exc)[:300],
                    "duration_seconds": round(elapsed, 2),
                },
            )
            return ResearchResult(
                query=query,
                output=f"LabClaw error: {exc}",
                sources=[],
                available=True,
                backend="labclaw",
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
            backend="labclaw",
            duration_seconds=round(elapsed, 2),
            metadata={"iterations": iterations},
        )

        await self._emit_event(
            "research.backend.completed",
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "backend": "labclaw",
                "available": True,
                "output_length": len(result.output),
                "source_count": len(sources),
                "duration_seconds": round(elapsed, 2),
            },
        )

        logger.info(
            "labclaw_run_complete: query=%s output_len=%d sources=%d elapsed=%.1fs",
            query[:80],
            len(result.output),
            len(sources),
            elapsed,
        )
        return result

    async def health(self) -> dict[str, Any]:
        """Check if LabClaw is installed and configured.

        Returns a dict with ``installed``, ``enabled``, ``available``,
        and ``base_dir`` keys.
        """
        base_exists = self.config.base_dir.exists() if self.config.base_dir else False
        return {
            "installed": LABCLAW_AVAILABLE,
            "enabled": self.config.enabled,
            "available": self.available,
            "base_dir": str(self.config.base_dir),
            "base_dir_exists": base_exists,
            "max_iterations": self.config.max_iterations,
            "timeout": self.config.timeout,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_sync(self, query: str, max_iterations: int) -> tuple[str, list[Any]]:
        """Synchronous LabClaw execution (called via ``asyncio.to_thread``).

        Returns ``(output_text, sources_list)``.
        """
        assert labclaw is not None  # guarded by self.available

        runner = labclaw.LabClawRunner(
            work_dir=str(self.config.base_dir),
            max_iterations=max_iterations,
            timeout=self.config.timeout,
        )
        result = runner.run(query)

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
