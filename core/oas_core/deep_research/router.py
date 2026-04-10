"""Research backend router -- parallel / sequential / hybrid execution.

Routes research queries to configured backends (DeerFlow, LabClaw, InternAgent,
UniScientist) based on the plan file's mode setting.

Modes (from OAS-V2-HYBRID-SWARM-PLAN.md section 6):

- **sequential**: Discovery -> Lab-loop -> Synthesis.
  ``internagent -> labclaw -> uniscientist``, each step receives prior output.
- **parallel**: Cross-validation, triangulation.
  ``deerflow || labclaw || internagent``, then ``uniscientist`` merges.
- **hybrid**: Phased deepening.
  ``{deerflow || internagent} -> labclaw -> uniscientist``.

DRVP events emitted:
- ``research.router.mode_chosen`` -- when mode is selected
- ``research.backend.started`` / ``research.backend.completed`` -- per backend
- ``research.synthesis.started`` / ``research.synthesis.completed`` -- for final merge
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from oas_core.adapters.research_result import ResearchResult

__all__ = [
    "ResearchRouter",
    "ResearchRouterConfig",
    "ResearchRouterResult",
    "ResearchMode",
]

logger = logging.getLogger("oas.deep_research.router")


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class ResearchBackend(Protocol):
    """Any object whose ``run()`` returns a ``ResearchResult``."""

    async def run(
        self,
        query: str,
        *,
        context: str,
    ) -> ResearchResult: ...


class SynthesisBackend(Protocol):
    """Any object that can synthesize multiple research findings."""

    async def run(
        self,
        query: str,
        *,
        context: str,
    ) -> ResearchResult: ...


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class ResearchMode:
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HYBRID = "hybrid"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ResearchRouterConfig(BaseModel):
    """Configuration for the research router."""

    default_mode: Literal["parallel", "sequential", "hybrid"] = "hybrid"
    default_backends: list[str] = ["deerflow"]
    synthesis_backend: Literal["default", "uniscientist", "none"] = "default"
    timeout_per_backend: float = 300.0


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ResearchRouterResult:
    """Aggregated result from a routed research pipeline."""

    query: str
    mode: str
    backend_results: list[ResearchResult] = field(default_factory=list)
    synthesis: str = ""
    total_sources: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return bool(self.synthesis) and not self.errors


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class ResearchRouter:
    """Routes research to backends in parallel, sequential, or hybrid mode.

    Auto-discovers available backends at construction time.  Backends
    that are not installed or not enabled are silently skipped.

    Usage::

        router = ResearchRouter()
        result = await router.run(
            "Graphene bilayer DFT parameters",
            mode="parallel",
            backends=["deerflow", "labclaw"],
        )
    """

    def __init__(
        self,
        config: ResearchRouterConfig | None = None,
        *,
        backends: dict[str, Any] | None = None,
        synthesis: Any | None = None,
    ) -> None:
        self.config = config or ResearchRouterConfig()
        self._backends: dict[str, Any] = dict(backends) if backends else {}
        self._synthesis = synthesis

        if not self._backends:
            self._register_available_backends()

    # ------------------------------------------------------------------
    # Auto-discovery
    # ------------------------------------------------------------------

    def _register_available_backends(self) -> None:
        """Auto-discover which backends are available and register them."""
        # DeerFlow -- always register a stub entry; real adapter injected at runtime
        self._backends["deerflow"] = _DeerFlowStub()

        # LabClaw
        try:
            from oas_core.adapters.labclaw import LabClawAdapter

            self._backends["labclaw"] = LabClawAdapter()
        except Exception:
            logger.debug("labclaw_backend_not_registered")

        # InternAgent
        try:
            from oas_core.adapters.internagent import InternAgentAdapter

            self._backends["internagent"] = InternAgentAdapter()
        except Exception:
            logger.debug("internagent_backend_not_registered")

    @property
    def available_backends(self) -> list[str]:
        """Return sorted list of registered backend names."""
        return sorted(self._backends.keys())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        query: str,
        *,
        mode: str | None = None,
        backends: list[str] | None = None,
        synthesis: str | None = None,
        context: str = "",
        request_id: str = "",
    ) -> ResearchRouterResult:
        """Execute research across backends according to mode.

        Modes:
        - parallel: run all backends concurrently, merge results
        - sequential: chain backends, each receives prior output as context
        - hybrid: parallel discovery phase, then sequential deepening

        Parameters
        ----------
        query:
            The research question.
        mode:
            Execution mode.  Defaults to ``config.default_mode``.
        backends:
            Backend names to use.  Defaults to ``config.default_backends``.
        synthesis:
            Synthesis strategy override.
        context:
            Optional prior context to seed the first backend.
        request_id:
            OAS request identifier for DRVP event grouping.
        """
        effective_mode = mode or self.config.default_mode
        selected = backends or list(self.config.default_backends)
        active = {k: self._backends[k] for k in selected if k in self._backends}

        # Emit mode-chosen event
        await self._emit_event(
            "research.router.mode_chosen",
            request_id=request_id,
            payload={
                "mode": effective_mode,
                "backends": list(active.keys()),
                "query": query[:200],
            },
        )

        if not active:
            return ResearchRouterResult(
                query=query,
                mode=effective_mode,
                errors=["No active research backends available"],
            )

        t0 = time.monotonic()

        if effective_mode == ResearchMode.PARALLEL:
            backend_results, errors = await self._run_parallel(
                query, active, context, request_id
            )
        elif effective_mode == ResearchMode.HYBRID:
            backend_results, errors = await self._run_hybrid(
                query, active, context, request_id
            )
        else:
            backend_results, errors = await self._run_sequential(
                query, active, context, request_id
            )

        # Synthesis
        synthesized = await self._synthesize(
            query, backend_results, synthesis, request_id
        )

        elapsed = time.monotonic() - t0

        total_sources = sum(len(r.sources) for r in backend_results)

        return ResearchRouterResult(
            query=query,
            mode=effective_mode,
            backend_results=backend_results,
            synthesis=synthesized,
            total_sources=total_sources,
            duration_seconds=round(elapsed, 2),
            errors=errors,
        )

    async def health(self) -> dict[str, Any]:
        """Report which backends are available and configured."""
        backend_health: dict[str, Any] = {}
        for name, backend in self._backends.items():
            if hasattr(backend, "health"):
                try:
                    backend_health[name] = await backend.health()
                except Exception as exc:
                    backend_health[name] = {"error": str(exc)}
            else:
                backend_health[name] = {"registered": True}

        return {
            "default_mode": self.config.default_mode,
            "default_backends": self.config.default_backends,
            "registered_backends": self.available_backends,
            "backend_health": backend_health,
        }

    # ------------------------------------------------------------------
    # Mode implementations
    # ------------------------------------------------------------------

    async def _run_sequential(
        self,
        query: str,
        active: dict[str, Any],
        initial_context: str,
        request_id: str,
    ) -> tuple[list[ResearchResult], list[str]]:
        """Sequential: each step receives prior output as context."""
        results: list[ResearchResult] = []
        errors: list[str] = []
        ctx = initial_context

        for name, backend in active.items():
            try:
                r = await self._call_backend(name, backend, query, ctx, request_id)
                results.append(r)
                if r.available and r.output:
                    ctx = r.output
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                logger.warning(
                    "research_backend_failed: backend=%s error=%s", name, exc
                )

        return results, errors

    async def _run_parallel(
        self,
        query: str,
        active: dict[str, Any],
        context: str,
        request_id: str,
    ) -> tuple[list[ResearchResult], list[str]]:
        """Parallel: all backends run concurrently."""
        tasks = {
            name: asyncio.create_task(
                self._call_backend(name, backend, query, context, request_id)
            )
            for name, backend in active.items()
        }

        results: list[ResearchResult] = []
        errors: list[str] = []

        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for name, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                errors.append(f"{name}: {result}")
                logger.warning(
                    "research_backend_failed: backend=%s error=%s", name, result
                )
            else:
                results.append(result)

        return results, errors

    async def _run_hybrid(
        self,
        query: str,
        active: dict[str, Any],
        initial_context: str,
        request_id: str,
    ) -> tuple[list[ResearchResult], list[str]]:
        """Hybrid: parallel discovery phase, then sequential deepening.

        Phase 1: Run deerflow and internagent in parallel (discovery).
        Phase 2: Feed combined discovery into labclaw and others (deepening).
        """
        discovery_names = [n for n in ("deerflow", "internagent") if n in active]
        deepening_names = [n for n in active if n not in discovery_names]
        results: list[ResearchResult] = []
        errors: list[str] = []

        # Phase 1: parallel discovery
        if discovery_names:
            disc_tasks = {
                name: asyncio.create_task(
                    self._call_backend(
                        name, active[name], query, initial_context, request_id
                    )
                )
                for name in discovery_names
            }
            disc_gathered = await asyncio.gather(
                *disc_tasks.values(), return_exceptions=True
            )
            for name, result in zip(disc_tasks.keys(), disc_gathered):
                if isinstance(result, Exception):
                    errors.append(f"{name}: {result}")
                else:
                    results.append(result)

        # Phase 2: sequential deepening with discovery context
        discovery_context = "\n\n".join(
            r.output for r in results if r.available and r.output
        )
        combined_context = (
            f"{initial_context}\n\n{discovery_context}".strip()
            if initial_context
            else discovery_context
        )

        for name in deepening_names:
            try:
                r = await self._call_backend(
                    name, active[name], query, combined_context, request_id
                )
                results.append(r)
                if r.available and r.output:
                    combined_context += "\n\n" + r.output
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        return results, errors

    # ------------------------------------------------------------------
    # Backend invocation
    # ------------------------------------------------------------------

    async def _call_backend(
        self,
        name: str,
        backend: Any,
        query: str,
        context: str,
        request_id: str,
    ) -> ResearchResult:
        """Call a single backend, returning a ``ResearchResult``."""
        if hasattr(backend, "run"):
            result = await backend.run(query, context=context)
        elif callable(backend):
            raw = await backend(request_id, query, context=context)
            result = ResearchResult(
                query=query,
                output=raw.get("output", str(raw)),
                sources=raw.get("sources", []),
                available=True,
                backend=name,
                metadata=raw,
            )
        else:
            result = ResearchResult(
                query=query,
                output="",
                available=False,
                backend=name,
                metadata={"error": "backend is not callable"},
            )

        return result

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def _synthesize(
        self,
        query: str,
        results: list[ResearchResult],
        synthesis_override: str | None,
        request_id: str,
    ) -> str:
        """Merge all backend results into a single synthesis string."""
        strategy = synthesis_override or self.config.synthesis_backend

        if strategy == "none" or not results:
            return ""

        await self._emit_event(
            "research.synthesis.started",
            request_id=request_id,
            payload={
                "strategy": strategy,
                "result_count": len(results),
            },
        )

        # Try UniScientist synthesis if requested
        if strategy == "uniscientist" and self._synthesis is not None:
            try:
                synth_result = await self._synthesis.run(
                    query, context=self._merge_outputs(results)
                )
                output = synth_result.output if hasattr(synth_result, "output") else str(synth_result)
                await self._emit_event(
                    "research.synthesis.completed",
                    request_id=request_id,
                    payload={
                        "strategy": "uniscientist",
                        "output_length": len(output),
                    },
                )
                return output
            except Exception as exc:
                logger.warning("synthesis_failed: strategy=%s error=%s", strategy, exc)

        # Default: concatenate outputs
        merged = self._merge_outputs(results)
        await self._emit_event(
            "research.synthesis.completed",
            request_id=request_id,
            payload={
                "strategy": "default",
                "output_length": len(merged),
            },
        )
        return merged

    @staticmethod
    def _merge_outputs(results: list[ResearchResult]) -> str:
        """Concatenate available backend outputs with separators."""
        parts: list[str] = []
        for r in results:
            if r.available and r.output:
                header = f"[{r.backend}]" if r.backend else ""
                parts.append(f"{header}\n{r.output}" if header else r.output)
        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # DRVP helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _emit_event(
        event_type_str: str,
        *,
        request_id: str = "",
        agent_name: str = "research_router",
        device: str = "leader",
        payload: dict[str, Any] | None = None,
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
                    payload=payload or {},
                )
            )
        except Exception:
            pass  # DRVP is best-effort


# ---------------------------------------------------------------------------
# Internal stubs
# ---------------------------------------------------------------------------

class _DeerFlowStub:
    """Placeholder for DeerFlow when the real adapter is not injected."""

    available = False

    async def run(
        self,
        query: str,
        *,
        context: str = "",
    ) -> ResearchResult:
        return ResearchResult(
            query=query,
            output="",
            available=False,
            backend="deerflow",
            metadata={"reason": "DeerFlow adapter not injected"},
        )

    async def health(self) -> dict[str, Any]:
        return {"installed": False, "available": False, "stub": True}
