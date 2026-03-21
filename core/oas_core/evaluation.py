"""Self-evaluation loop for campaign quality control.

After a campaign step or full campaign completes, the evaluator assesses
the result quality and can trigger retry or refinement steps. Uses a
lightweight LLM call to score results against the original request.

The evaluation is non-blocking — it records scores and recommendations
but does not automatically retry (the caller decides).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

__all__ = [
    "EvaluationResult",
    "QualityLevel",
    "Evaluator",
    "RuleBasedEvaluator",
]

logger = logging.getLogger("oas.evaluation")


class QualityLevel(str, Enum):
    EXCELLENT = "excellent"   # Score >= 0.9
    GOOD = "good"             # Score >= 0.7
    ACCEPTABLE = "acceptable" # Score >= 0.5
    POOR = "poor"             # Score >= 0.3
    FAILED = "failed"         # Score < 0.3

    @classmethod
    def from_score(cls, score: float) -> QualityLevel:
        if score >= 0.9:
            return cls.EXCELLENT
        if score >= 0.7:
            return cls.GOOD
        if score >= 0.5:
            return cls.ACCEPTABLE
        if score >= 0.3:
            return cls.POOR
        return cls.FAILED


@dataclass
class EvaluationResult:
    """Result of evaluating a step or campaign output."""

    score: float  # 0.0 to 1.0
    quality: QualityLevel
    criteria_scores: dict[str, float] = field(default_factory=dict)
    feedback: str = ""
    should_retry: bool = False
    suggested_refinement: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "quality": self.quality.value,
            "criteria_scores": {
                k: round(v, 3) for k, v in self.criteria_scores.items()
            },
            "feedback": self.feedback,
            "should_retry": self.should_retry,
            "suggested_refinement": self.suggested_refinement,
        }


# Type for LLM-based evaluation function
LLMEvalFn = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]]


class RuleBasedEvaluator:
    """Evaluates campaign step results using configurable heuristic rules.

    Checks structural quality without an LLM call — fast and deterministic.
    Used as a first pass; an LLM evaluator can follow for deeper assessment.

    Usage::

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(
            command="research",
            request="Research quantum dot electrodes for EIT",
            output={"findings": [...], "sources": [...]},
        )
        if result.should_retry:
            # ... re-run step with refinement ...
    """

    def __init__(
        self,
        *,
        min_output_length: int = 100,
        min_sources: int = 2,
        retry_threshold: float = 0.4,
    ):
        self._min_output_length = min_output_length
        self._min_sources = min_sources
        self._retry_threshold = retry_threshold

    def evaluate(
        self,
        command: str,
        request: str,
        output: dict[str, Any],
    ) -> EvaluationResult:
        """Evaluate a step result against quality criteria."""
        scores: dict[str, float] = {}

        # 1. Completeness: does the output have substantive content?
        raw_text = _extract_text(output)
        if len(raw_text) >= self._min_output_length:
            scores["completeness"] = min(1.0, len(raw_text) / (self._min_output_length * 3))
        else:
            scores["completeness"] = len(raw_text) / self._min_output_length if self._min_output_length > 0 else 0.0

        # 2. Structure: does it have expected fields?
        expected = _expected_fields(command)
        if expected:
            present = sum(1 for f in expected if f in output)
            scores["structure"] = present / len(expected)
        else:
            scores["structure"] = 1.0 if output else 0.0

        # 3. Sources: for research commands, are sources cited?
        if command in ("research", "literature", "perplexity"):
            sources = output.get("sources", output.get("references", []))
            if isinstance(sources, list):
                scores["sources"] = min(1.0, len(sources) / self._min_sources)
            else:
                scores["sources"] = 0.5  # present but not a list
        else:
            scores["sources"] = 1.0  # not applicable

        # 4. Error-free: no error indicators
        has_error = "error" in output or output.get("status") == "error"
        scores["error_free"] = 0.0 if has_error else 1.0

        # Overall score (weighted average)
        weights = {"completeness": 0.3, "structure": 0.25, "sources": 0.25, "error_free": 0.2}
        total = sum(scores.get(k, 0) * w for k, w in weights.items())
        overall = total / sum(weights.values())

        quality = QualityLevel.from_score(overall)
        should_retry = overall < self._retry_threshold

        feedback_parts = []
        if scores.get("completeness", 1) < 0.5:
            feedback_parts.append("Output is too short or incomplete")
        if scores.get("structure", 1) < 0.5:
            feedback_parts.append(f"Missing expected fields: {expected}")
        if scores.get("sources", 1) < 0.5:
            feedback_parts.append("Insufficient source citations")
        if scores.get("error_free", 1) < 0.5:
            feedback_parts.append("Output contains error indicators")

        return EvaluationResult(
            score=overall,
            quality=quality,
            criteria_scores=scores,
            feedback="; ".join(feedback_parts) if feedback_parts else "Output meets quality criteria",
            should_retry=should_retry,
            suggested_refinement=f"Retry /{command} with more detail" if should_retry else None,
        )


class Evaluator:
    """Campaign evaluator that combines rule-based and optional LLM evaluation.

    Usage::

        evaluator = Evaluator(llm_eval_fn=my_llm_call)

        # Evaluate a single step
        result = await evaluator.evaluate_step(
            request_id="req_1",
            step_number=1,
            command="research",
            request="quantum sensors",
            output={"findings": [...]},
            agent_name="academic",
            device="academic",
        )

        # Evaluate full campaign
        results = await evaluator.evaluate_campaign(
            request_id="req_1",
            original_request="Full EIT study",
            step_results=[...],
            agent_name="leader",
            device="leader",
        )
    """

    def __init__(
        self,
        *,
        llm_eval_fn: LLMEvalFn | None = None,
        rule_evaluator: RuleBasedEvaluator | None = None,
        use_llm_for_poor: bool = True,
    ):
        self._llm_eval = llm_eval_fn
        self._rules = rule_evaluator or RuleBasedEvaluator()
        self._use_llm_for_poor = use_llm_for_poor

    async def evaluate_step(
        self,
        request_id: str,
        step_number: int,
        command: str,
        request: str,
        output: dict[str, Any],
        agent_name: str,
        device: str,
    ) -> EvaluationResult:
        """Evaluate a single campaign step result."""
        # Rule-based evaluation first (fast)
        result = self._rules.evaluate(command, request, output)

        # If poor quality and LLM available, get deeper evaluation
        if (
            self._use_llm_for_poor
            and self._llm_eval
            and result.quality in (QualityLevel.POOR, QualityLevel.FAILED)
        ):
            try:
                llm_result = await self._llm_eval(command, request, output)
                # Merge LLM feedback
                if "score" in llm_result:
                    result.score = (result.score + llm_result["score"]) / 2
                    result.quality = QualityLevel.from_score(result.score)
                if "feedback" in llm_result:
                    result.feedback = llm_result["feedback"]
                if "suggested_refinement" in llm_result:
                    result.suggested_refinement = llm_result["suggested_refinement"]
            except Exception as e:
                logger.warning("llm_eval_failed", extra={"error": str(e)})

        # Emit DRVP event
        await emit(DRVPEvent(
            event_type=DRVPEventType.TOOL_CALL_COMPLETED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "tool_name": "self_evaluation",
                "step_number": step_number,
                "score": result.score,
                "quality": result.quality.value,
                "should_retry": result.should_retry,
            },
        ))

        logger.info(
            "step_evaluated",
            extra={
                "step": step_number,
                "command": command,
                "score": round(result.score, 3),
                "quality": result.quality.value,
            },
        )

        return result

    async def evaluate_campaign(
        self,
        request_id: str,
        original_request: str,
        step_results: list[dict[str, Any]],
        agent_name: str,
        device: str,
    ) -> EvaluationResult:
        """Evaluate an entire campaign's aggregate quality."""
        if not step_results:
            return EvaluationResult(
                score=0.0,
                quality=QualityLevel.FAILED,
                feedback="No step results to evaluate",
            )

        # Average step scores
        step_scores = []
        for i, step in enumerate(step_results):
            command = step.get("command", "")
            output = step.get("result", step.get("output", {}))
            sr = self._rules.evaluate(command, original_request, output)
            step_scores.append(sr.score)

        avg_score = sum(step_scores) / len(step_scores) if step_scores else 0.0
        quality = QualityLevel.from_score(avg_score)

        result = EvaluationResult(
            score=avg_score,
            quality=quality,
            criteria_scores={"avg_step_score": avg_score, "step_count": len(step_results)},
            feedback=f"Campaign average quality: {quality.value} ({avg_score:.2f})",
            should_retry=quality in (QualityLevel.POOR, QualityLevel.FAILED),
        )

        await emit(DRVPEvent(
            event_type=DRVPEventType.CAMPAIGN_STEP_COMPLETED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "tool_name": "campaign_evaluation",
                "score": result.score,
                "quality": result.quality.value,
                "step_count": len(step_results),
            },
        ))

        return result


# --- Helpers ---

def _extract_text(output: dict[str, Any]) -> str:
    """Extract human-readable text from an output dict."""
    for key in ("text", "content", "raw", "findings", "summary", "result"):
        val = output.get(key)
        if isinstance(val, str):
            return val
        if isinstance(val, list):
            return " ".join(str(v) for v in val)
    return str(output)


def _expected_fields(command: str) -> list[str]:
    """Return expected output fields for a given command type."""
    field_map: dict[str, list[str]] = {
        "research": ["findings", "sources"],
        "literature": ["papers", "summary"],
        "doe": ["design", "factors", "levels"],
        "simulate": ["results", "parameters"],
        "analyze": ["analysis", "metrics"],
        "synthetic": ["data", "schema"],
        "synthesize": ["synthesis", "conclusions"],
        "report": ["report", "sections"],
        "perplexity": ["answer", "sources"],
    }
    return field_map.get(command, [])
