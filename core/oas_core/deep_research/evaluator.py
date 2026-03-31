"""Convergence evaluator — 5-metric quality scoring for deep research.

Evaluates research output across completeness, source quality, structure,
novelty, and accuracy. The orchestrator iterates until the weighted
aggregate score crosses the configurable threshold.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["ConvergenceEvaluator", "EvalScore"]

logger = logging.getLogger("oas.deep_research.evaluator")


@dataclass
class EvalScore:
    """Quality scores for a research output."""

    completeness: float = 0.0  # 0-1: sub-topics covered
    source_quality: float = 0.0  # 0-1: peer-reviewed ratio + citations
    structure: float = 0.0  # 0-1: sections, flow, logic
    novelty: float = 0.0  # 0-1: non-trivial insights
    accuracy: float = 0.0  # 0-1: claims verified against sources
    aggregate: float = 0.0  # Weighted average

    gaps: list[str] = field(default_factory=list)
    feedback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "completeness": round(self.completeness, 3),
            "source_quality": round(self.source_quality, 3),
            "structure": round(self.structure, 3),
            "novelty": round(self.novelty, 3),
            "accuracy": round(self.accuracy, 3),
            "aggregate": round(self.aggregate, 3),
            "gaps": self.gaps,
        }


class ConvergenceEvaluator:
    """Evaluates research quality using 5 weighted metrics.

    Weights:
      - completeness: 0.25
      - source_quality: 0.25
      - structure: 0.20
      - novelty: 0.15
      - accuracy: 0.15
    """

    WEIGHTS = {
        "completeness": 0.25,
        "source_quality": 0.25,
        "structure": 0.20,
        "novelty": 0.15,
        "accuracy": 0.15,
    }

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold
        self.last_feedback: str = ""

    def evaluate(
        self,
        text: str,
        sources_count: int = 0,
        peer_reviewed_count: int = 0,
        total_citations: int = 0,
    ) -> EvalScore:
        """Evaluate a research text using rule-based heuristics.

        For production use, this should be augmented with an LLM scorer.
        The rule-based version provides a fast, deterministic baseline.
        """
        score = EvalScore()

        # 1. Completeness — check for expected research sections
        expected_sections = [
            "introduction", "background", "methodology", "methods",
            "results", "findings", "discussion", "conclusion",
            "references", "future work", "limitations",
        ]
        text_lower = text.lower()
        found_sections = sum(1 for s in expected_sections if s in text_lower)
        score.completeness = min(1.0, found_sections / 5.0)

        # Check for sub-topic coverage (presence of multiple distinct themes)
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
        score.completeness = min(1.0, score.completeness * 0.6 + min(1.0, len(paragraphs) / 8) * 0.4)

        # 2. Source quality — peer-reviewed ratio + citation density
        if sources_count > 0:
            pr_ratio = peer_reviewed_count / sources_count
            citation_density = min(1.0, total_citations / (sources_count * 10))
            score.source_quality = pr_ratio * 0.6 + citation_density * 0.2 + min(1.0, sources_count / 15) * 0.2
        else:
            # Check for inline citation patterns
            cite_patterns = len(re.findall(r'\[\d+\]|\(\w+,?\s*\d{4}\)', text))
            score.source_quality = min(1.0, cite_patterns / 10)

        # 3. Structure — heading hierarchy, logical flow
        headings = re.findall(r'^#{1,4}\s+.+', text, re.MULTILINE)
        has_intro = any("intro" in h.lower() for h in headings)
        has_conclusion = any("conclu" in h.lower() for h in headings)

        heading_score = min(1.0, len(headings) / 6)
        flow_score = 0.5 + (0.25 if has_intro else 0) + (0.25 if has_conclusion else 0)
        word_count = len(text.split())
        length_score = min(1.0, word_count / 1500)
        score.structure = heading_score * 0.4 + flow_score * 0.3 + length_score * 0.3

        # 4. Novelty — non-generic statements, specific data points
        specific_patterns = [
            r'\d+\.?\d*%',  # Percentages
            r'\d{4}',  # Years
            r'\$\d+',  # Dollar amounts
            r'\d+\.\d+',  # Decimal numbers
        ]
        specifics = sum(len(re.findall(p, text)) for p in specific_patterns)
        score.novelty = min(1.0, specifics / 15)

        # 5. Accuracy — proxy: citation presence, hedging language, no obvious errors
        hedging = len(re.findall(r'\b(may|might|could|suggests|indicates|appears)\b', text, re.IGNORECASE))
        appropriate_hedging = min(1.0, hedging / 5)  # Some hedging is good
        score.accuracy = score.source_quality * 0.5 + appropriate_hedging * 0.3 + 0.2

        # Aggregate
        score.aggregate = sum(
            getattr(score, metric) * weight
            for metric, weight in self.WEIGHTS.items()
        )

        # Identify gaps
        if score.completeness < 0.7:
            score.gaps.append("Missing key research sections (introduction, methodology, conclusion)")
        if score.source_quality < 0.6:
            score.gaps.append("Insufficient peer-reviewed sources")
        if score.structure < 0.7:
            score.gaps.append("Weak document structure — needs better headings and flow")
        if score.novelty < 0.5:
            score.gaps.append("Lacks specific data points and non-trivial insights")
        if score.accuracy < 0.6:
            score.gaps.append("Claims need better source attribution")

        score.feedback = "; ".join(score.gaps) if score.gaps else "Quality threshold met"
        self.last_feedback = score.feedback

        logger.info(
            "research_evaluated",
            aggregate=round(score.aggregate, 3),
            threshold=self.threshold,
            passed=score.aggregate >= self.threshold,
            gaps=len(score.gaps),
        )

        return score

    def has_converged(self, score: EvalScore) -> bool:
        """Check if the score meets the convergence threshold."""
        return score.aggregate >= self.threshold
