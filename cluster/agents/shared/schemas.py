"""EIP (Experiment Intent Package) and RR (Run Record) contract schemas.

These follow the v1.0 specification from darklab_architecture.md.
All inter-agent experimental data flows use these contracts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ExperimentParameter(BaseModel):
    name: str
    value: Any
    unit: str = ""
    range_min: Any | None = None
    range_max: Any | None = None


class SafetyCheck(BaseModel):
    check_type: str  # "pre_run" | "in_situ" | "post_run"
    description: str
    passed: bool | None = None
    timestamp: datetime | None = None


class EIP(BaseModel):
    """Experiment Intent Package v1.0 — describes what an experiment should do."""
    eip_id: str
    version: str = "1.0"
    title: str
    hypothesis: str
    method: str
    parameters: list[ExperimentParameter] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    safety_checks: list[SafetyCheck] = Field(default_factory=list)
    created_by: str = ""  # agent name
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by: str | None = None
    approved_at: datetime | None = None
    signature: str | None = None  # Ed25519 signature


class DataRef(BaseModel):
    """Reference to a data artifact (file, dataset, figure)."""
    ref_id: str
    path: str
    format: str  # "csv" | "json" | "png" | "pdf" | "parquet"
    description: str = ""
    sha256: str = ""


class RunRecord(BaseModel):
    """Run Record v1.0 — captures what actually happened during an experiment."""
    rr_id: str
    eip_id: str  # Links back to the EIP
    version: str = "1.0"
    status: str  # "completed" | "failed" | "partial"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    actual_parameters: list[ExperimentParameter] = Field(default_factory=list)
    data_refs: list[DataRef] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    executed_by: str = ""  # agent name or device
    signature: str | None = None
