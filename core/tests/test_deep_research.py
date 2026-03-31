"""Tests for the deep research pipeline."""
import pytest

from oas_core.deep_research.evaluator import ConvergenceEvaluator, EvalScore
from oas_core.deep_research.sources import AcademicSearcher, SearchResult
from oas_core.deep_research.orchestrator import (
    ResearchOrchestrator,
    ResearchConfig,
    ResearchResult,
)


# ── Evaluator tests ─────────────────────────────────────────────

class TestConvergenceEvaluator:
    def test_scores_well_structured_text(self):
        text = """
# Research Report: Quantum Sensors

## Introduction
This report examines quantum sensor applications for environmental monitoring.

## Methodology
Systematic literature review across arXiv, Semantic Scholar, and bioRxiv.
We identified 15 relevant papers published between 2023 and 2026.

## Key Findings
Finding 1: Nitrogen-vacancy centers show 10.5% improvement in sensitivity (Smith 2025).
Finding 2: Cost reduction of $450 per unit achieved in 2024 (Jones et al., 2024).
Finding 3: Field deployment trials indicate 92% reliability over 12 months.

## Discussion
The 15 identified sources indicate active research. Citation counts suggest
growing interest, with a 45% increase year-over-year since 2023.

## Conclusion
Further research on quantum sensors is warranted. The evidence reviewed
suggests commercial viability may be achieved by 2028.

## Limitations
This review is limited to publicly available preprints and published papers.

## References
[1] Smith (2025). NV-center sensitivity improvements.
[2] Jones et al. (2024). Cost analysis of quantum sensors.
"""
        evaluator = ConvergenceEvaluator(threshold=0.75)
        score = evaluator.evaluate(text, sources_count=15, peer_reviewed_count=10, total_citations=200)
        assert score.aggregate > 0.5
        assert score.completeness > 0.5
        assert score.structure > 0.5

    def test_identifies_gaps_in_poor_text(self):
        text = "Some research was done on the topic. Results were found."
        evaluator = ConvergenceEvaluator(threshold=0.75)
        score = evaluator.evaluate(text)
        assert score.aggregate < 0.5
        assert len(score.gaps) > 0

    def test_convergence_check(self):
        evaluator = ConvergenceEvaluator(threshold=0.75)
        good = EvalScore(aggregate=0.80)
        bad = EvalScore(aggregate=0.60)
        assert evaluator.has_converged(good) is True
        assert evaluator.has_converged(bad) is False

    def test_source_quality_with_citations(self):
        text = "Research with sources [1] and [2] and (Smith, 2024) and (Jones, 2025)."
        evaluator = ConvergenceEvaluator()
        score = evaluator.evaluate(text, sources_count=10, peer_reviewed_count=8, total_citations=150)
        assert score.source_quality > 0.5

    def test_novelty_with_specific_data(self):
        text = """
The efficiency improved by 23.5% in 2024 trials. At $1200 per unit,
the technology achieved 0.95 correlation with traditional methods.
The 2025 deployment covered 47 monitoring stations.
"""
        evaluator = ConvergenceEvaluator()
        score = evaluator.evaluate(text)
        assert score.novelty > 0.3

    def test_weights_sum_to_one(self):
        total = sum(ConvergenceEvaluator.WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_feedback_populated(self):
        evaluator = ConvergenceEvaluator()
        score = evaluator.evaluate("Short text.")
        assert score.feedback != ""
        assert evaluator.last_feedback != ""


# ── SearchResult tests ───────────────────────────────────────────

class TestSearchResult:
    def test_create_search_result(self):
        r = SearchResult(
            title="Test Paper",
            authors=["Author A", "Author B"],
            source="arxiv",
            year=2025,
            citation_count=42,
        )
        assert r.title == "Test Paper"
        assert r.source == "arxiv"
        assert r.citation_count == 42


# ── Orchestrator tests ───────────────────────────────────────────

class TestResearchOrchestrator:
    @pytest.mark.asyncio
    async def test_run_with_placeholder_synthesis(self):
        """Orchestrator runs with placeholder synthesis (no LLM needed)."""
        config = ResearchConfig(max_iterations=2, threshold=0.0)  # Low threshold to converge
        orchestrator = ResearchOrchestrator(config)
        # Override searcher to avoid real network calls
        orchestrator.searcher = _MockSearcher()

        result = await orchestrator.run("quantum sensors", "req-test-001")

        assert result.request_id == "req-test-001"
        assert result.topic == "quantum sensors"
        assert len(result.output) > 0
        assert result.iterations_completed >= 1
        assert result.total_sources == 3  # From mock
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_run_respects_max_iterations(self):
        """Orchestrator stops at max_iterations even if not converged."""
        config = ResearchConfig(max_iterations=2, threshold=0.99)  # Unreachable threshold
        orchestrator = ResearchOrchestrator(config)
        orchestrator.searcher = _MockSearcher()

        result = await orchestrator.run("impossible topic", "req-test-002")

        assert result.iterations_completed == 2
        assert result.converged is False
        assert len(result.iteration_history) == 2

    @pytest.mark.asyncio
    async def test_result_to_dict(self):
        config = ResearchConfig(max_iterations=1, threshold=0.0)
        orchestrator = ResearchOrchestrator(config)
        orchestrator.searcher = _MockSearcher()

        result = await orchestrator.run("test", "req-test-003")
        d = result.to_dict()

        assert "request_id" in d
        assert "topic" in d
        assert "output" in d
        assert "final_score" in d
        assert "iterations" in d

    @pytest.mark.asyncio
    async def test_custom_synthesizer(self):
        """Orchestrator uses a custom synthesizer when provided."""
        config = ResearchConfig(max_iterations=1, threshold=0.0)
        orchestrator = ResearchOrchestrator(config)
        orchestrator.searcher = _MockSearcher()

        async def custom_synth(topic, sources, draft, feedback):
            return f"# Custom Report\n\nResearch on {topic} with {len(sources)} sources."

        result = await orchestrator.run("custom test", "req-test-004", synthesizer=custom_synth)
        assert "Custom Report" in result.output


class _MockSearcher:
    """Mock academic searcher that returns fixed results without network calls."""

    async def search_all(self, query: str) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Paper on {query} — Part 1",
                authors=["Smith, A.", "Jones, B."],
                abstract=f"This paper investigates {query} using novel methods.",
                source="arxiv",
                year=2025,
                citation_count=42,
                is_peer_reviewed=False,
            ),
            SearchResult(
                title=f"Review of {query} applications",
                authors=["Lee, C."],
                abstract=f"A comprehensive review of {query} in practical applications.",
                source="semantic_scholar",
                year=2024,
                citation_count=87,
                is_peer_reviewed=True,
                doi="10.1234/test.2024.001",
            ),
            SearchResult(
                title=f"Experimental validation of {query}",
                authors=["Wang, D.", "Chen, E."],
                abstract=f"We present experimental results validating {query} predictions.",
                source="biorxiv",
                year=2026,
                is_peer_reviewed=False,
            ),
        ]
