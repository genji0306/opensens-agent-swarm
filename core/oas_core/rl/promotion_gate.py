"""Checkpoint promotion gate — decides whether a trained checkpoint goes live.

A checkpoint is promoted only when:
1. Evaluation score >= baseline score (no regression)
2. Evaluation score >= previous promoted checkpoint score
3. No single test prompt scores below the catastrophic threshold (0.3)
4. Optionally requires human approval via Paperclip
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

__all__ = ["PromotionGate", "PromotionDecision"]

logger = logging.getLogger("oas.rl.promotion_gate")


@dataclass
class PromotionDecision:
    """Result of the promotion gate check."""

    promoted: bool
    reason: str
    checkpoint_id: str
    score: float
    baseline_score: float
    previous_promoted_score: float


class PromotionGate:
    """Gate that controls when RL checkpoints are promoted to production."""

    def __init__(
        self,
        *,
        min_score: float = 0.7,
        catastrophic_threshold: float = 0.3,
        require_approval: bool = False,
    ):
        self.min_score = min_score
        self.catastrophic_threshold = catastrophic_threshold
        self.require_approval = require_approval

    def evaluate(
        self,
        checkpoint_id: str,
        eval_score: float,
        baseline_score: float,
        previous_promoted_score: float = 0.0,
        per_prompt_scores: list[dict[str, Any]] | None = None,
    ) -> PromotionDecision:
        """Decide whether a checkpoint should be promoted.

        Args:
            checkpoint_id: ID of the checkpoint being evaluated.
            eval_score: Aggregate evaluation score of the checkpoint.
            baseline_score: Score of the frozen baseline.
            previous_promoted_score: Score of the currently promoted checkpoint.
            per_prompt_scores: Per-prompt scores for catastrophic failure check.

        Returns:
            PromotionDecision with the verdict and reasoning.
        """
        # Check minimum absolute score
        if eval_score < self.min_score:
            return PromotionDecision(
                promoted=False,
                reason=f"Score {eval_score:.3f} below minimum threshold {self.min_score}",
                checkpoint_id=checkpoint_id,
                score=eval_score,
                baseline_score=baseline_score,
                previous_promoted_score=previous_promoted_score,
            )

        # Check regression vs baseline
        if eval_score < baseline_score:
            return PromotionDecision(
                promoted=False,
                reason=f"Score {eval_score:.3f} regressed vs baseline {baseline_score:.3f}",
                checkpoint_id=checkpoint_id,
                score=eval_score,
                baseline_score=baseline_score,
                previous_promoted_score=previous_promoted_score,
            )

        # Check regression vs previous promoted
        if previous_promoted_score > 0 and eval_score < previous_promoted_score:
            return PromotionDecision(
                promoted=False,
                reason=(
                    f"Score {eval_score:.3f} below previous promoted "
                    f"{previous_promoted_score:.3f}"
                ),
                checkpoint_id=checkpoint_id,
                score=eval_score,
                baseline_score=baseline_score,
                previous_promoted_score=previous_promoted_score,
            )

        # Check for catastrophic failures on individual prompts
        if per_prompt_scores:
            for entry in per_prompt_scores:
                prompt_score = entry.get("score", 1.0)
                if prompt_score < self.catastrophic_threshold:
                    prompt_id = entry.get("prompt_id", "unknown")
                    return PromotionDecision(
                        promoted=False,
                        reason=(
                            f"Catastrophic failure on prompt {prompt_id}: "
                            f"{prompt_score:.3f} < {self.catastrophic_threshold}"
                        ),
                        checkpoint_id=checkpoint_id,
                        score=eval_score,
                        baseline_score=baseline_score,
                        previous_promoted_score=previous_promoted_score,
                    )

        delta = eval_score - baseline_score
        logger.info(
            "checkpoint_promoted",
            checkpoint_id=checkpoint_id,
            score=eval_score,
            baseline=baseline_score,
            delta=f"+{delta:.3f}",
        )

        return PromotionDecision(
            promoted=True,
            reason=f"Passed all gates: {eval_score:.3f} (baseline {baseline_score:.3f}, +{delta:.3f})",
            checkpoint_id=checkpoint_id,
            score=eval_score,
            baseline_score=baseline_score,
            previous_promoted_score=previous_promoted_score,
        )
