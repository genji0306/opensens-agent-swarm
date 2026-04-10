"""Five-dimension eval scoring rubric.

Dimensions (from LLM-WIKI-HARNESS-ENGINEERING-PLAN):
  Completeness (25%)  -- covers all aspects of the question
  Accuracy (25%)      -- verifiably correct, well-sourced
  Source Quality (20%) -- primary literature, recent, high-impact
  Synthesis (20%)     -- novel connections, actionable insights
  Cost Efficiency (10%) -- optimal tier selection per task
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("oas.eval.scorer")

__all__ = ["EvalScorer", "ScoringResult", "DimensionScore"]


@dataclass(frozen=True)
class DimensionScore:
    """Score for a single evaluation dimension."""

    name: str
    score: float  # 1.0 to 5.0
    weight: float
    feedback: str = ""


@dataclass(frozen=True)
class ScoringResult:
    """Aggregate scoring result for a single task evaluation."""

    task_id: str
    task_type: str
    dimension_scores: tuple[DimensionScore, ...]
    weighted_average: float
    passed: bool  # >= threshold
    feedback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "dimensions": {
                d.name: {
                    "score": round(d.score, 2),
                    "weight": d.weight,
                    "feedback": d.feedback,
                }
                for d in self.dimension_scores
            },
            "weighted_average": round(self.weighted_average, 2),
            "passed": self.passed,
            "feedback": self.feedback,
        }


DIMENSION_WEIGHTS: dict[str, float] = {
    "completeness": 0.25,
    "accuracy": 0.25,
    "source_quality": 0.20,
    "synthesis": 0.20,
    "cost_efficiency": 0.10,
}


class EvalScorer:
    """Scores agent outputs against golden set ground truth on 5 dimensions."""

    def __init__(self, *, threshold: float = 3.5) -> None:
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def score(
        self,
        *,
        task_id: str,
        task_type: str,
        output: dict[str, Any],
        ground_truth: dict[str, Any],
        cost_usd: float = 0.0,
    ) -> ScoringResult:
        """Score an output against ground truth on all 5 dimensions."""
        output_text = _extract_text(output)
        dimensions: list[DimensionScore] = []

        # --- 1. Completeness ---
        gt_points = ground_truth.get("key_points", [])
        if gt_points:
            covered = sum(
                1 for p in gt_points if p.lower() in output_text.lower()
            )
            completeness = 1.0 + 4.0 * (covered / len(gt_points))
            completeness_fb = f"Covered {covered}/{len(gt_points)} key points"
        else:
            gt_text = _extract_text(ground_truth)
            if gt_text:
                ratio = min(1.0, len(output_text) / max(1, len(gt_text)))
                completeness = 1.0 + 4.0 * ratio
            else:
                completeness = 3.0 if len(output_text) > 200 else 1.5
            covered = 0
            completeness_fb = f"Text length ratio scored {completeness:.1f}"

        dimensions.append(
            DimensionScore(
                name="completeness",
                score=min(5.0, completeness),
                weight=DIMENSION_WEIGHTS["completeness"],
                feedback=completeness_fb,
            )
        )

        # --- 2. Accuracy ---
        gt_facts = ground_truth.get("verified_facts", [])
        if gt_facts:
            correct = sum(
                1 for f in gt_facts if f.lower() in output_text.lower()
            )
            accuracy = 1.0 + 4.0 * (correct / len(gt_facts))
            accuracy_fb = f"Matched {correct}/{len(gt_facts)} facts"
        else:
            has_errors = any(
                kw in output_text.lower()
                for kw in ["error", "failed", "incorrect"]
            )
            accuracy = 2.0 if has_errors else 3.5
            correct = 0
            accuracy_fb = "No verified facts to check"

        dimensions.append(
            DimensionScore(
                name="accuracy",
                score=min(5.0, accuracy),
                weight=DIMENSION_WEIGHTS["accuracy"],
                feedback=accuracy_fb,
            )
        )

        # --- 3. Source Quality ---
        sources = output.get("sources", output.get("references", []))
        gt_sources = ground_truth.get("expected_sources", [])
        if isinstance(sources, list):
            source_count = len(sources)
            if gt_sources:
                matched = sum(
                    1
                    for s in gt_sources
                    if any(s.lower() in str(src).lower() for src in sources)
                )
                source_quality = 1.0 + 4.0 * (matched / len(gt_sources))
                source_fb = f"Matched {matched}/{len(gt_sources)} expected sources ({source_count} total)"
            else:
                source_quality = min(5.0, 1.0 + source_count * 0.5)
                source_fb = f"{source_count} sources cited"
        else:
            source_quality = 1.0
            source_count = 0
            source_fb = "No sources list found"

        dimensions.append(
            DimensionScore(
                name="source_quality",
                score=min(5.0, source_quality),
                weight=DIMENSION_WEIGHTS["source_quality"],
                feedback=source_fb,
            )
        )

        # --- 4. Synthesis ---
        synthesis_indicators = [
            "therefore",
            "consequently",
            "this suggests",
            "combined with",
            "in contrast",
            "building on",
            "novel",
            "implication",
        ]
        synthesis_count = sum(
            1 for ind in synthesis_indicators if ind in output_text.lower()
        )
        synthesis_score = min(5.0, 1.0 + synthesis_count * 0.5)
        has_conclusions = bool(
            output.get("conclusions")
            or output.get("synthesis")
            or output.get("insights")
        )
        if has_conclusions:
            synthesis_score = min(5.0, synthesis_score + 1.0)

        dimensions.append(
            DimensionScore(
                name="synthesis",
                score=synthesis_score,
                weight=DIMENSION_WEIGHTS["synthesis"],
                feedback=f"{synthesis_count} synthesis indicators found"
                + (", has conclusions section" if has_conclusions else ""),
            )
        )

        # --- 5. Cost Efficiency ---
        expected_cost = ground_truth.get("expected_cost_usd", 0.05)
        if cost_usd <= 0:
            cost_score = 5.0  # Local-only = perfect efficiency
        elif cost_usd <= expected_cost:
            cost_score = 5.0
        elif cost_usd <= expected_cost * 2:
            cost_score = 3.5
        elif cost_usd <= expected_cost * 5:
            cost_score = 2.0
        else:
            cost_score = 1.0

        dimensions.append(
            DimensionScore(
                name="cost_efficiency",
                score=cost_score,
                weight=DIMENSION_WEIGHTS["cost_efficiency"],
                feedback=f"${cost_usd:.4f} vs expected ${expected_cost:.4f}",
            )
        )

        # --- Weighted average ---
        weighted = sum(d.score * d.weight for d in dimensions)
        passed = weighted >= self._threshold

        feedback_parts = [f"{d.name}: {d.score:.1f}/5.0" for d in dimensions]
        overall_fb = (
            f"Overall: {weighted:.2f}/5.0 ({'PASS' if passed else 'FAIL'}). "
            + ", ".join(feedback_parts)
        )

        result = ScoringResult(
            task_id=task_id,
            task_type=task_type,
            dimension_scores=tuple(dimensions),
            weighted_average=weighted,
            passed=passed,
            feedback=overall_fb,
        )
        logger.info(
            "task_scored",
            extra={
                "task_id": task_id,
                "weighted_average": round(weighted, 2),
                "passed": passed,
            },
        )
        return result


def _extract_text(data: dict[str, Any]) -> str:
    """Extract human-readable text from an output dict."""
    for key in (
        "text",
        "content",
        "raw",
        "findings",
        "summary",
        "result",
        "synthesis",
    ):
        val = data.get(key)
        if isinstance(val, str):
            return val
        if isinstance(val, list):
            return " ".join(str(v) for v in val)
    return str(data)
