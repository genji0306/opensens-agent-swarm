"""Training pipeline — orchestrates rollout scoring and batch assembly.

Reads rollout JSONL files from the rollouts directory, scores them using
the PRM (via Tinker or local evaluation), and assembles training batches
for the OpenClaw-RL trainer.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from oas_core.rl import RolloutSession

__all__ = ["TrainingPipeline", "TrainingBatch"]

logger = logging.getLogger("oas.rl.training_pipeline")


class ScoredRollout(BaseModel):
    """A rollout session with PRM scores attached."""

    session: RolloutSession
    turn_scores: list[float] = Field(default_factory=list)
    aggregate_score: float = 0.0


class TrainingBatch(BaseModel):
    """A batch of scored rollouts ready for training."""

    batch_id: str
    agent_type: str
    rollouts: list[ScoredRollout] = Field(default_factory=list)
    live_count: int = 0
    synthetic_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total(self) -> int:
        return len(self.rollouts)


class TrainingPipeline:
    """Orchestrates the rollout → scoring → batch assembly pipeline."""

    def __init__(
        self,
        rollouts_dir: Path,
        *,
        batch_size: int = 16,
        min_session_score: float = 0.3,
        synthetic_weight: float = 0.3,
    ):
        self.rollouts_dir = rollouts_dir
        self.batch_size = batch_size
        self.min_session_score = min_session_score
        self.synthetic_weight = synthetic_weight

    def load_rollouts(self, agent_type: str, source: str = "live") -> list[RolloutSession]:
        """Load rollout sessions from JSONL files for a given agent type and source."""
        source_dir = self.rollouts_dir / source
        if not source_dir.exists():
            return []

        sessions: list[RolloutSession] = []
        for path in sorted(source_dir.glob("*.jsonl")):
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        if data.get("agent_type") == agent_type:
                            sessions.append(RolloutSession.model_validate(data))
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning("rollout_load_error", path=str(path), error=str(exc))

        return sessions

    def score_rollouts(
        self,
        sessions: list[RolloutSession],
        scorer: Any = None,
    ) -> list[ScoredRollout]:
        """Score rollout sessions using the PRM.

        If no scorer is provided, uses a simple heuristic based on
        response length and turn count (placeholder for real PRM).
        """
        scored: list[ScoredRollout] = []

        for session in sessions:
            if scorer is not None:
                turn_scores = scorer(session)
                agg = sum(turn_scores) / len(turn_scores) if turn_scores else 0.0
            else:
                # Heuristic placeholder: score based on assistant response quality
                turn_scores = []
                for turn in session.turns:
                    if turn.role == "assistant":
                        # Simple heuristic: longer, substantive responses score higher
                        length = len(turn.content)
                        score = min(1.0, length / 500.0) * 0.7 + 0.3
                        turn_scores.append(round(score, 3))
                agg = sum(turn_scores) / len(turn_scores) if turn_scores else 0.0

            if agg >= self.min_session_score:
                scored.append(ScoredRollout(
                    session=session,
                    turn_scores=turn_scores,
                    aggregate_score=round(agg, 3),
                ))

        return scored

    def assemble_batch(
        self,
        agent_type: str,
        live_rollouts: list[ScoredRollout],
        synthetic_rollouts: list[ScoredRollout] | None = None,
    ) -> TrainingBatch | None:
        """Assemble a training batch with a mix of live and synthetic data.

        Returns None if there aren't enough rollouts to fill a batch.
        """
        synthetic_rollouts = synthetic_rollouts or []

        # Calculate target counts for the mix
        target_synthetic = int(self.batch_size * self.synthetic_weight)
        target_live = self.batch_size - target_synthetic

        # Take what we can, fill remainder from the other source
        actual_live = live_rollouts[:target_live]
        actual_synthetic = synthetic_rollouts[:target_synthetic]

        # Fill shortfall from the other source
        if len(actual_live) < target_live:
            extra_needed = target_live - len(actual_live)
            actual_synthetic.extend(synthetic_rollouts[target_synthetic:target_synthetic + extra_needed])
        elif len(actual_synthetic) < target_synthetic:
            extra_needed = target_synthetic - len(actual_synthetic)
            actual_live.extend(live_rollouts[target_live:target_live + extra_needed])

        combined = actual_live + actual_synthetic
        if len(combined) < self.batch_size:
            logger.info(
                "insufficient_rollouts_for_batch",
                agent_type=agent_type,
                available=len(combined),
                required=self.batch_size,
            )
            return None

        batch = TrainingBatch(
            batch_id=f"{agent_type}-batch-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            agent_type=agent_type,
            rollouts=combined[:self.batch_size],
            live_count=len([r for r in combined[:self.batch_size] if r.session.source == "live"]),
            synthetic_count=len([r for r in combined[:self.batch_size] if r.session.source == "synthetic"]),
        )

        logger.info(
            "training_batch_assembled",
            batch_id=batch.batch_id,
            live=batch.live_count,
            synthetic=batch.synthetic_count,
        )

        return batch
