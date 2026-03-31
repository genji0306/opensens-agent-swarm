"""A/B comparison between RL-evolved and baseline checkpoints.

Runs the same set of prompts through both the RL-evolved model and
the baseline, then compares scores side-by-side to detect regressions
and quantify improvements.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

__all__ = ["ABComparison", "ABResult"]

logger = logging.getLogger("oas.rl.ab_comparison")


@dataclass
class ABPromptResult:
    """Score comparison for a single prompt."""

    prompt_id: str
    prompt: str
    baseline_score: float
    evolved_score: float
    delta: float
    winner: str  # "baseline" | "evolved" | "tie"


@dataclass
class ABResult:
    """Aggregate A/B comparison result."""

    comparison_id: str
    agent_type: str
    checkpoint_id: str
    baseline_version: str
    n_prompts: int
    baseline_avg: float
    evolved_avg: float
    delta: float
    win_rate: float  # Fraction of prompts where evolved > baseline
    loss_rate: float  # Fraction where evolved < baseline
    tie_rate: float
    per_prompt: list[ABPromptResult] = field(default_factory=list)
    ran_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def summary(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return (
            f"A/B {self.agent_type}: baseline={self.baseline_avg:.3f}, "
            f"evolved={self.evolved_avg:.3f} ({sign}{self.delta:.3f}), "
            f"W/L/T={self.win_rate:.0%}/{self.loss_rate:.0%}/{self.tie_rate:.0%}"
        )


class ABComparison:
    """Runs A/B comparisons between RL checkpoints and baselines."""

    def __init__(self, *, tie_threshold: float = 0.02):
        self.tie_threshold = tie_threshold

    def compare(
        self,
        agent_type: str,
        checkpoint_id: str,
        baseline_version: str,
        prompts: list[dict[str, str]],
        baseline_scorer: Callable[[str], float],
        evolved_scorer: Callable[[str], float],
    ) -> ABResult:
        """Run A/B comparison on a set of prompts.

        Args:
            agent_type: Agent type being compared.
            checkpoint_id: ID of the RL-evolved checkpoint.
            baseline_version: Version string of the baseline.
            prompts: List of {"prompt_id": str, "prompt": str}.
            baseline_scorer: Callable that scores a prompt using the baseline model.
            evolved_scorer: Callable that scores a prompt using the evolved model.

        Returns:
            ABResult with aggregate and per-prompt scores.
        """
        per_prompt: list[ABPromptResult] = []
        wins = 0
        losses = 0
        ties = 0

        for p in prompts:
            prompt_id = p.get("prompt_id", "unknown")
            prompt_text = p.get("prompt", "")

            b_score = baseline_scorer(prompt_text)
            e_score = evolved_scorer(prompt_text)
            delta = e_score - b_score

            if abs(delta) <= self.tie_threshold:
                winner = "tie"
                ties += 1
            elif delta > 0:
                winner = "evolved"
                wins += 1
            else:
                winner = "baseline"
                losses += 1

            per_prompt.append(ABPromptResult(
                prompt_id=prompt_id,
                prompt=prompt_text[:100],
                baseline_score=round(b_score, 3),
                evolved_score=round(e_score, 3),
                delta=round(delta, 3),
                winner=winner,
            ))

        n = len(prompts) or 1
        baseline_avg = sum(r.baseline_score for r in per_prompt) / n
        evolved_avg = sum(r.evolved_score for r in per_prompt) / n

        result = ABResult(
            comparison_id=f"ab-{agent_type}-{checkpoint_id}",
            agent_type=agent_type,
            checkpoint_id=checkpoint_id,
            baseline_version=baseline_version,
            n_prompts=len(prompts),
            baseline_avg=round(baseline_avg, 3),
            evolved_avg=round(evolved_avg, 3),
            delta=round(evolved_avg - baseline_avg, 3),
            win_rate=round(wins / n, 3),
            loss_rate=round(losses / n, 3),
            tie_rate=round(ties / n, 3),
            per_prompt=per_prompt,
        )

        logger.info("ab_comparison_complete", summary=result.summary)
        return result
