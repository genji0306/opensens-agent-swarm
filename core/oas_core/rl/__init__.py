"""OAS reinforcement learning subpackage.

Provides rollout collection, training pipeline management, checkpoint
evaluation, and MiroShark transcript conversion for the OpenClaw-RL
integration.
"""
from __future__ import annotations

__all__ = [
    "RolloutSession",
    "RolloutTurn",
    "CheckpointMeta",
    "BaselineMeta",
    "EvaluationResult",
]

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class RolloutTurn(BaseModel):
    """A single turn in a conversation rollout."""

    role: str  # "system" | "user" | "assistant"
    content: str
    turn_type: str = "main"  # "main" (trainable) | "side" (not trainable)
    token_logprobs: list[float] | None = None
    response_tokens: int | None = None


class RolloutSession(BaseModel):
    """A complete conversation session formatted for OpenClaw-RL training."""

    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_type: str
    source: str = "live"  # "live" | "synthetic"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    turns: list[RolloutTurn] = Field(default_factory=list)

    def add_turn(
        self, role: str, content: str, *, turn_type: str = "main", **kwargs: Any
    ) -> None:
        self.turns.append(RolloutTurn(role=role, content=content, turn_type=turn_type, **kwargs))

    def finalize(self) -> None:
        self.completed_at = datetime.now(timezone.utc)


class CheckpointMeta(BaseModel):
    """Metadata for an RL training checkpoint."""

    checkpoint_id: str
    parent_checkpoint: str | None = None
    base_model: str = "Qwen/Qwen3-4B-Instruct-2507"
    baseline_version: str = ""
    training_method: str = "combine"
    training_steps: int = 0
    rollout_sources: dict[str, int] = Field(default_factory=dict)
    evaluation_score: float = 0.0
    baseline_score: float = 0.0
    delta: float = 0.0
    promoted: bool = False
    promoted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BaselineMeta(BaseModel):
    """Metadata for a frozen pre-RL baseline snapshot."""

    agent_type: str
    version: str  # e.g. "research-v0"
    base_model: str
    model_hash: str = ""
    evaluation_scores: dict[str, float] = Field(default_factory=dict)
    frozen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvaluationResult(BaseModel):
    """Result of evaluating a checkpoint against canonical test prompts."""

    checkpoint_id: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    test_set: str = ""
    n_prompts: int = 0
    aggregate_score: float = 0.0
    criteria_scores: dict[str, float] = Field(default_factory=dict)
    per_prompt_scores: list[dict[str, Any]] = Field(default_factory=list)
    regression_check: dict[str, Any] = Field(default_factory=dict)
