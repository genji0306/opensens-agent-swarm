"""Core data models shared by all DarkLab agents."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    # Academic tasks
    RESEARCH = "research"
    LITERATURE = "literature"
    DOE = "doe"
    PAPER = "paper"
    PERPLEXITY = "perplexity"

    # Experiment tasks
    SIMULATE = "simulate"
    ANALYZE = "analyze"
    SYNTHETIC = "synthetic"
    REPORT_DATA = "report_data"
    AUTORESEARCH = "autoresearch"
    DEERFLOW = "deerflow"

    # Leader tasks
    PLAN = "plan"
    SYNTHESIZE = "synthesize"
    MEDIA_GEN = "media_gen"
    NOTEBOOKLM = "notebooklm"

    # RL + Debate
    DEBATE = "debate"
    RL_TRAIN = "rl_train"

    # Deep Research
    DEEP_RESEARCH = "deep_research"
    PARAMETER_GOLF = "parameter_golf"
    SWARM_RESEARCH = "swarm_research"
    TURBOQ_STATUS = "turboq_status"
    RESULTS = "results"
    SCHEDULE = "schedule"
    FULL_SWARM = "full_swarm"
    TURBO_SWARM = "turbo_swarm"
    PAPER_REVIEW = "paper_review"
    DFT = "dft"
    ANE_RESEARCH = "ane_research"
    GEMMA_SWARM = "gemma_swarm"
    UNIPAT_SWARM = "unipat_swarm"

    # Orchestrator (v2 Phase 24)
    ORCHESTRATE = "orchestrate"

    # KAIROS daemon (v2 Phase 24)
    KAIROS = "kairos"

    # Knowledge wiki + eval (Phase 25)
    WIKI_COMPILE = "wiki_compile"
    WIKI_LINT = "wiki_lint"
    EVAL_RUN = "eval_run"
    EVAL_REPORT = "eval_report"

    # System
    STATUS = "status"


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_type: TaskType
    user_id: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signature: str | None = None
    parent_task_id: str | None = None  # For chained workflows


class TaskResult(BaseModel):
    task_id: str
    agent_name: str
    status: str  # "ok" | "error" | "partial"
    result: dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    artifacts: list[str] = Field(default_factory=list)  # Paths to generated files
    payload_hash: str | None = None  # SHA-256 of input for provenance


class AgentInfo(BaseModel):
    name: str
    description: str
    device: str  # "leader" | "academic" | "experiment"
    task_types: list[TaskType]
    ai_services: list[str] = Field(default_factory=list)
