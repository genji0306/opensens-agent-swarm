"""Campaign schema — canonical, versioned campaign object.

Replaces ad-hoc dicts with typed Pydantic models. All campaign data
flowing through OAS should use these schemas for creation, persistence,
and cross-module communication.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "CampaignSchema",
    "CampaignStepSchema",
    "CampaignStatus",
    "CostAttribution",
]

SCHEMA_VERSION = "1.0.0"


class CampaignStatus(str, Enum):
    """Campaign lifecycle states."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def can_transition_to(self, target: CampaignStatus) -> bool:
        """Check if a transition from this state to target is valid."""
        return target in _VALID_TRANSITIONS.get(self, set())


# Valid state machine transitions
_VALID_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {
        CampaignStatus.PENDING_APPROVAL,
        CampaignStatus.APPROVED,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.PENDING_APPROVAL: {
        CampaignStatus.APPROVED,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.APPROVED: {
        CampaignStatus.RUNNING,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.RUNNING: {
        CampaignStatus.PAUSED,
        CampaignStatus.COMPLETED,
        CampaignStatus.FAILED,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.PAUSED: {
        CampaignStatus.RUNNING,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.COMPLETED: set(),
    CampaignStatus.FAILED: {
        CampaignStatus.RUNNING,  # retry
    },
    CampaignStatus.CANCELLED: set(),
}


class CostAttribution(BaseModel):
    """Token and compute cost for a single LLM call within a campaign."""

    campaign_id: str
    step_id: int | None = None
    model: str
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_name: str = ""
    request_id: str = ""


class CampaignStepSchema(BaseModel):
    """A single step in a campaign plan — typed version of CampaignStep."""

    step: int
    command: str
    args: str = ""
    depends_on: list[int] = Field(default_factory=list)
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    issue_id: str | None = None
    cost: CostAttribution | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class CampaignSchema(BaseModel):
    """Canonical campaign object — the single source of truth for a campaign.

    Every campaign created in OAS gets one of these. It tracks the full
    lifecycle from draft through completion, with provenance, cost
    attribution, and state machine enforcement.
    """

    schema_version: str = SCHEMA_VERSION
    campaign_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    request_id: str = ""
    title: str = ""
    objective: str = ""
    status: CampaignStatus = CampaignStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    agent_name: str = ""
    device: str = ""
    steps: list[CampaignStepSchema] = Field(default_factory=list)
    total_cost: CostAttribution | None = None
    provenance_ids: list[str] = Field(default_factory=list)
    parent_campaign_id: str | None = None
    issue_id: str | None = None
    issue_key: str | None = None
    approval_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    checkpoint: dict[str, Any] | None = None

    def transition_to(self, target: CampaignStatus) -> None:
        """Transition to a new status, raising ValueError if invalid."""
        if not self.status.can_transition_to(target):
            raise ValueError(
                f"Invalid transition: {self.status.value} -> {target.value}"
            )
        self.status = target
        self.updated_at = datetime.now(timezone.utc)
        if target == CampaignStatus.RUNNING and self.started_at is None:
            self.started_at = self.updated_at
        if target in (CampaignStatus.COMPLETED, CampaignStatus.FAILED, CampaignStatus.CANCELLED):
            self.completed_at = self.updated_at

    @property
    def completed_steps(self) -> list[CampaignStepSchema]:
        return [s for s in self.steps if s.status == "completed"]

    @property
    def failed_steps(self) -> list[CampaignStepSchema]:
        return [s for s in self.steps if s.status == "failed"]

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_checkpoint(self) -> dict[str, Any]:
        """Serialize campaign state for persistence/resume."""
        return self.model_dump(mode="json")

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any]) -> CampaignSchema:
        """Restore campaign from persisted checkpoint."""
        return cls.model_validate(data)

    @classmethod
    def from_plan_file(cls, path: str | Path) -> CampaignSchema:
        """Create a campaign schema from a markdown plan file."""
        from oas_core.plan_file import PlanFile

        return PlanFile.from_path(path).to_campaign()
