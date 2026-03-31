"""Intent and artifact schemas — typed packages for cross-module communication.

These schemas define the vocabulary OAS uses to express what it wants
a downstream module to do (intents) and what that module produces
(artifacts). Using typed schemas instead of ad-hoc dicts ensures
contract compliance across the Darklab stack.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ResearchIntentPackage",
    "KnowledgeArtifact",
    "SimulationIntentPackage",
    "ExperimentIntentPackage",
    "RunRecord",
    "ComputeRequest",
    "ComputeReceipt",
    "EvidenceType",
    "IntentPriority",
]

SCHEMA_VERSION = "1.0.0"


class IntentPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceType(str, Enum):
    LITERATURE = "literature"
    SIMULATION = "simulation"
    EXPERIMENT = "experiment"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    DEBATE = "debate"


# --- Intent Packages (inputs to modules) ---


class ResearchIntentPackage(BaseModel):
    """Describes a research objective to be fulfilled by Parallax or Academic agents."""

    schema_version: str = SCHEMA_VERSION
    intent_id: str = Field(default_factory=lambda: f"rip-{uuid.uuid4().hex[:12]}")
    campaign_id: str = ""
    objective: str
    constraints: list[str] = Field(default_factory=list)
    budget_limit_usd: float | None = None
    deadline: datetime | None = None
    evidence_requirements: list[str] = Field(default_factory=list)
    priority: IntentPriority = IntentPriority.NORMAL
    source_requirements: int = 3
    max_iterations: int = 5
    convergence_threshold: float = 0.75
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulationIntentPackage(BaseModel):
    """Describes a simulation task for OAE or Experiment agents."""

    schema_version: str = SCHEMA_VERSION
    intent_id: str = Field(default_factory=lambda: f"sip-{uuid.uuid4().hex[:12]}")
    campaign_id: str = ""
    model_spec: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    validation_criteria: list[str] = Field(default_factory=list)
    compute_budget_usd: float | None = None
    priority: IntentPriority = IntentPriority.NORMAL
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentIntentPackage(BaseModel):
    """Describes a physical experiment for OPAD or lab nodes."""

    schema_version: str = SCHEMA_VERSION
    intent_id: str = Field(default_factory=lambda: f"eip-{uuid.uuid4().hex[:12]}")
    campaign_id: str = ""
    protocol: str = ""
    materials: list[str] = Field(default_factory=list)
    safety_requirements: list[str] = Field(default_factory=list)
    approval_required: bool = True
    priority: IntentPriority = IntentPriority.NORMAL
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Artifacts (outputs from modules) ---


class KnowledgeArtifact(BaseModel):
    """Output of research or analysis — a knowledge unit with provenance."""

    schema_version: str = SCHEMA_VERSION
    artifact_id: str = Field(default_factory=lambda: f"ka-{uuid.uuid4().hex[:12]}")
    campaign_id: str = ""
    step_id: int | None = None
    findings: str = ""
    summary: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    evidence_type: EvidenceType = EvidenceType.LITERATURE
    provenance_id: str = ""
    agent_name: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    """Output of a simulation or experiment execution."""

    schema_version: str = SCHEMA_VERSION
    record_id: str = Field(default_factory=lambda: f"rr-{uuid.uuid4().hex[:12]}")
    campaign_id: str = ""
    step_id: int | None = None
    results: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    compute_used: dict[str, Any] = Field(default_factory=dict)
    agent_name: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Compute Contracts ---


class ComputeRequest(BaseModel):
    """Resource allocation request from OAS to a compute provider."""

    schema_version: str = SCHEMA_VERSION
    request_id: str = Field(default_factory=lambda: f"cr-{uuid.uuid4().hex[:12]}")
    campaign_id: str = ""
    requested_resources: dict[str, Any] = Field(default_factory=dict)
    max_cost_usd: float | None = None
    max_duration_seconds: float | None = None
    priority: IntentPriority = IntentPriority.NORMAL


class ComputeReceipt(BaseModel):
    """Acknowledgement of allocated compute resources."""

    schema_version: str = SCHEMA_VERSION
    receipt_id: str = Field(default_factory=lambda: f"cx-{uuid.uuid4().hex[:12]}")
    request_id: str = ""
    campaign_id: str = ""
    allocated_resources: dict[str, Any] = Field(default_factory=dict)
    start_time: datetime | None = None
    end_time: datetime | None = None
    cost_usd: float = 0.0
