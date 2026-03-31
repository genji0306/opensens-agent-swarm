"""Deep Research orchestrator — coordinates the multi-phase research pipeline.

Manages the iterative loop: search → synthesize → refine → evaluate → iterate.
Emits DRVP events for real-time progress visibility in Agent Office.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oas_core.deep_research.evaluator import ConvergenceEvaluator, EvalScore
from oas_core.deep_research.sources import AcademicSearcher, SearchResult

__all__ = ["ResearchOrchestrator", "ResearchConfig", "ResearchResult"]

logger = logging.getLogger("oas.deep_research.orchestrator")


@dataclass
class ResearchConfig:
    """Configuration for a deep research run."""

    max_iterations: int = 5
    threshold: float = 0.75
    arxiv_max: int = 10
    semantic_scholar_max: int = 10
    biorxiv_enabled: bool = True
    workspace_dir: Path = field(default_factory=lambda: Path.home() / ".darklab" / "deep-research" / "workspaces")


@dataclass
class IterationResult:
    """Result of a single research iteration."""

    iteration: int
    score: EvalScore
    sources_found: int
    draft_length: int
    gaps: list[str]
    duration_seconds: float = 0.0


@dataclass
class ResearchResult:
    """Final result of a deep research run."""

    request_id: str
    topic: str
    output: str
    final_score: float
    iterations_completed: int
    total_sources: int
    sources: list[SearchResult] = field(default_factory=list)
    iteration_history: list[IterationResult] = field(default_factory=list)
    converged: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "topic": self.topic,
            "output": self.output,
            "final_score": round(self.final_score, 3),
            "iterations": self.iterations_completed,
            "total_sources": self.total_sources,
            "converged": self.converged,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at else 0
            ),
        }


class ResearchOrchestrator:
    """Orchestrates the deep research pipeline.

    Usage::

        config = ResearchConfig(max_iterations=5, threshold=0.75)
        orchestrator = ResearchOrchestrator(config)
        result = await orchestrator.run("quantum sensor applications", "req-123")
    """

    def __init__(self, config: ResearchConfig | None = None):
        self.config = config or ResearchConfig()
        self.searcher = AcademicSearcher(
            arxiv_max=self.config.arxiv_max,
            semantic_scholar_max=self.config.semantic_scholar_max,
            biorxiv_enabled=self.config.biorxiv_enabled,
        )
        self.evaluator = ConvergenceEvaluator(threshold=self.config.threshold)

    async def run(
        self,
        topic: str,
        request_id: str,
        *,
        synthesizer: Any = None,
    ) -> ResearchResult:
        """Execute the full deep research pipeline.

        Args:
            topic: The research topic or question.
            request_id: OAS request ID for DRVP events.
            synthesizer: Optional async callable(topic, sources, prior_draft, feedback) -> str.
                If None, uses a simple concatenation as placeholder.

        Returns:
            ResearchResult with the final output and metadata.
        """
        result = ResearchResult(
            request_id=request_id,
            topic=topic,
            output="",
            final_score=0.0,
            iterations_completed=0,
            total_sources=0,
        )

        await self._emit("deep_research.started", request_id, {
            "topic": topic[:200],
            "max_iterations": self.config.max_iterations,
            "threshold": self.config.threshold,
        })

        # Phase 1: Search academic sources
        await self._emit("deep_research.search", request_id, {"status": "searching"})
        sources = await self.searcher.search_all(topic)
        result.sources = sources
        result.total_sources = len(sources)

        await self._emit("deep_research.search", request_id, {
            "status": "complete",
            "sources_found": len(sources),
        })

        draft = ""
        feedback = ""

        for iteration in range(1, self.config.max_iterations + 1):
            import time
            iter_start = time.monotonic()

            await self._emit("deep_research.iteration", request_id, {
                "iteration": iteration,
                "total": self.config.max_iterations,
                "feedback": feedback[:200],
            })

            # Phase 2: Synthesize / refine
            if synthesizer:
                draft = await synthesizer(topic, sources, draft, feedback)
            else:
                draft = self._placeholder_synthesis(topic, sources, draft, feedback, iteration)

            # Phase 3: Evaluate
            peer_reviewed = sum(1 for s in sources if s.is_peer_reviewed)
            total_citations = sum(s.citation_count for s in sources)

            score = self.evaluator.evaluate(
                draft,
                sources_count=len(sources),
                peer_reviewed_count=peer_reviewed,
                total_citations=total_citations,
            )

            iter_duration = time.monotonic() - iter_start
            iter_result = IterationResult(
                iteration=iteration,
                score=score,
                sources_found=len(sources),
                draft_length=len(draft),
                gaps=score.gaps,
                duration_seconds=round(iter_duration, 1),
            )
            result.iteration_history.append(iter_result)

            await self._emit("deep_research.scored", request_id, {
                "iteration": iteration,
                "score": round(score.aggregate, 3),
                "threshold": self.config.threshold,
                "passed": self.evaluator.has_converged(score),
                "gaps": score.gaps[:3],
            })

            if self.evaluator.has_converged(score):
                result.output = draft
                result.final_score = score.aggregate
                result.iterations_completed = iteration
                result.converged = True
                break

            feedback = score.feedback
            result.iterations_completed = iteration
            result.final_score = score.aggregate

        if not result.converged:
            result.output = draft  # Deliver best effort

        result.completed_at = datetime.now(timezone.utc)

        await self._emit("deep_research.completed", request_id, {
            "converged": result.converged,
            "final_score": round(result.final_score, 3),
            "iterations": result.iterations_completed,
            "sources": result.total_sources,
        })

        return result

    def _placeholder_synthesis(
        self,
        topic: str,
        sources: list[SearchResult],
        prior_draft: str,
        feedback: str,
        iteration: int,
    ) -> str:
        """Simple placeholder synthesis (no LLM required).

        In production, this is replaced by a real LLM synthesizer passed
        via the `synthesizer` parameter.
        """
        sections = [f"# Research Report: {topic}\n"]

        if iteration > 1 and feedback:
            sections.append(f"## Iteration {iteration} — Addressing Gaps\n\n{feedback}\n")

        sections.append("## Introduction\n")
        sections.append(f"This report examines: {topic}\n")

        if sources:
            sections.append(f"\n## Sources ({len(sources)} papers found)\n")
            for i, s in enumerate(sources[:15], 1):
                authors = ", ".join(s.authors[:3])
                year = f" ({s.year})" if s.year else ""
                citations = f" — {s.citation_count} citations" if s.citation_count else ""
                sections.append(f"[{i}] {s.title}{year}. {authors}{citations}\n")
                if s.abstract:
                    sections.append(f"    {s.abstract[:200]}...\n")

        sections.append("\n## Methodology\n")
        sections.append("Systematic literature review across arXiv, Semantic Scholar, and bioRxiv.\n")

        sections.append("\n## Key Findings\n")
        for i, s in enumerate(sources[:5], 1):
            sections.append(f"- Finding {i}: {s.title} suggests further investigation may be needed.\n")

        sections.append("\n## Discussion\n")
        sections.append(f"The {len(sources)} identified sources indicate active research in this area.\n")

        sections.append("\n## Conclusion\n")
        sections.append(f"Further research on {topic} is warranted based on the evidence reviewed.\n")

        sections.append("\n## Limitations\n")
        sections.append("This review is limited to publicly available preprints and published papers.\n")

        if prior_draft:
            sections.append(f"\n## Previous Draft Sections Retained\n\n{prior_draft[:500]}\n")

        return "\n".join(sections)

    @staticmethod
    async def _emit(event_type: str, request_id: str, payload: dict[str, Any]) -> None:
        """Emit a DRVP event (best-effort)."""
        try:
            from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
            await emit(DRVPEvent(
                event_type=DRVPEventType(event_type),
                request_id=request_id,
                agent_name="deep-research",
                device="leader",
                payload=payload,
            ))
        except Exception:
            pass
