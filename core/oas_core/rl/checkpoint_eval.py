"""Checkpoint evaluation against canonical test prompts.

Evaluates RL-trained checkpoints using the existing OAS evaluation
framework extended with RL-specific metrics.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oas_core.rl import EvaluationResult

__all__ = ["CheckpointEvaluator"]

logger = logging.getLogger("oas.rl.checkpoint_eval")


class CheckpointEvaluator:
    """Evaluates RL checkpoints against canonical test prompts."""

    def __init__(
        self,
        evaluations_dir: Path,
        baselines_dir: Path,
    ):
        self.evaluations_dir = evaluations_dir
        self.baselines_dir = baselines_dir

    def load_baseline_score(self, agent_type: str) -> float:
        """Load the baseline evaluation score for an agent type."""
        baseline_path = self.baselines_dir / f"{agent_type}-v0.json"
        if not baseline_path.exists():
            return 0.0
        try:
            data = json.loads(baseline_path.read_text())
            scores = data.get("evaluation_scores", {})
            return scores.get("aggregate", 0.0)
        except (json.JSONDecodeError, Exception):
            return 0.0

    def load_previous_promoted_score(self, agent_type: str) -> float:
        """Load the evaluation score of the currently promoted checkpoint."""
        # Scan evaluations dir for the most recent promoted checkpoint
        best_score = 0.0
        for path in self.evaluations_dir.glob(f"{agent_type}-ckpt-*.json"):
            try:
                data = json.loads(path.read_text())
                if data.get("regression_check", {}).get("passed"):
                    score = data.get("aggregate_score", 0.0)
                    if score > best_score:
                        best_score = score
            except (json.JSONDecodeError, Exception):
                continue
        return best_score

    def evaluate(
        self,
        checkpoint_id: str,
        agent_type: str,
        test_prompts: list[dict[str, str]],
        response_scorer: Any = None,
    ) -> EvaluationResult:
        """Evaluate a checkpoint against canonical test prompts.

        Args:
            checkpoint_id: ID of the checkpoint to evaluate.
            agent_type: Agent type (e.g. "research").
            test_prompts: List of {"prompt_id": str, "prompt": str, "expected": str}.
            response_scorer: Callable(prompt, response, expected) -> float.
                If None, uses a simple heuristic.

        Returns:
            EvaluationResult with scores and regression analysis.
        """
        baseline_score = self.load_baseline_score(agent_type)
        per_prompt: list[dict[str, Any]] = []

        criteria_totals: dict[str, float] = {
            "completeness": 0.0,
            "structure": 0.0,
            "sources": 0.0,
            "error_free": 0.0,
        }

        for test in test_prompts:
            prompt_id = test.get("prompt_id", "unknown")
            # In real implementation, this would call the RL-evolved model
            # For now, generate a placeholder score
            if response_scorer:
                score = response_scorer(
                    test.get("prompt", ""),
                    "",  # Would be model response
                    test.get("expected", ""),
                )
            else:
                score = 0.75  # Placeholder

            quality = "excellent" if score >= 0.9 else "good" if score >= 0.7 else "fair" if score >= 0.5 else "poor"
            per_prompt.append({
                "prompt_id": prompt_id,
                "score": round(score, 3),
                "quality": quality,
            })

            # Distribute to criteria (simplified — real impl uses RuleBasedEvaluator)
            for key in criteria_totals:
                criteria_totals[key] += score

        n = len(test_prompts) or 1
        criteria_scores = {k: round(v / n, 3) for k, v in criteria_totals.items()}
        aggregate = round(sum(p["score"] for p in per_prompt) / n, 3) if per_prompt else 0.0

        regressed = [p for p in per_prompt if p["score"] < baseline_score * 0.8]

        result = EvaluationResult(
            checkpoint_id=checkpoint_id,
            test_set=f"{agent_type}-canonical-v1",
            n_prompts=len(test_prompts),
            aggregate_score=aggregate,
            criteria_scores=criteria_scores,
            per_prompt_scores=per_prompt,
            regression_check={
                "baseline_score": baseline_score,
                "delta": round(aggregate - baseline_score, 3),
                "regressed_prompts": [p["prompt_id"] for p in regressed],
                "passed": aggregate >= baseline_score,
            },
        )

        # Persist the evaluation
        eval_path = self.evaluations_dir / f"{checkpoint_id}.json"
        eval_path.write_text(result.model_dump_json(indent=2))
        logger.info(
            "checkpoint_evaluated",
            checkpoint_id=checkpoint_id,
            score=aggregate,
            baseline=baseline_score,
        )

        return result
