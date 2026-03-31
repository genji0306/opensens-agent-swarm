"""Multi-layer readiness scoring for campaign decision-making.

Scores four dimensions (knowledge, simulation, experiment, infrastructure)
from 0.0 to 1.0 to determine whether a campaign is ready to advance to
the next stage. The decision engine uses these scores to avoid premature
handoffs and unnecessary module invocations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from oas_core.schemas.campaign import CampaignSchema
from oas_core.schemas.intents import (
    KnowledgeArtifact,
    EvidenceType,
    ResearchIntentPackage,
)
from oas_core.registry.capability import ModuleHealth, ModuleStatus

__all__ = [
    "ReadinessDimension",
    "ReadinessScore",
    "ReadinessScorer",
]

logger = logging.getLogger("oas.decision.readiness")


class ReadinessDimension(str, Enum):
    KNOWLEDGE = "knowledge"
    SIMULATION = "simulation"
    EXPERIMENT = "experiment"
    INFRASTRUCTURE = "infrastructure"


@dataclass
class DimensionScore:
    """Score for a single readiness dimension."""

    dimension: ReadinessDimension
    score: float  # 0.0 to 1.0
    breakdown: dict[str, float] = field(default_factory=dict)
    notes: str = ""


@dataclass
class ReadinessScore:
    """Aggregate readiness across all dimensions."""

    dimensions: list[DimensionScore] = field(default_factory=list)
    overall: float = 0.0
    ready: bool = False
    recommended_action: str = ""

    def get(self, dim: ReadinessDimension) -> float:
        for d in self.dimensions:
            if d.dimension == dim:
                return d.score
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 3),
            "ready": self.ready,
            "recommended_action": self.recommended_action,
            "dimensions": {
                d.dimension.value: {
                    "score": round(d.score, 3),
                    "breakdown": {k: round(v, 3) for k, v in d.breakdown.items()},
                    "notes": d.notes,
                }
                for d in self.dimensions
            },
        }


class ReadinessScorer:
    """Scores campaign readiness across four dimensions.

    Usage::

        scorer = ReadinessScorer(threshold=0.6)
        score = scorer.score(campaign, artifacts, module_health, context)
        if score.ready:
            proceed()
        else:
            print(score.recommended_action)
    """

    def __init__(self, threshold: float = 0.6):
        self._threshold = threshold

    def score(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        module_health: dict[str, ModuleHealth] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ReadinessScore:
        """Score readiness across all dimensions."""
        ctx = context or {}
        health = module_health or {}

        dims = [
            self._score_knowledge(campaign, artifacts, ctx),
            self._score_simulation(campaign, artifacts, ctx),
            self._score_experiment(campaign, artifacts, ctx),
            self._score_infrastructure(campaign, health, ctx),
        ]

        # Weighted overall: knowledge matters most early, infrastructure always matters
        weights = {
            ReadinessDimension.KNOWLEDGE: 0.35,
            ReadinessDimension.SIMULATION: 0.2,
            ReadinessDimension.EXPERIMENT: 0.15,
            ReadinessDimension.INFRASTRUCTURE: 0.3,
        }
        total = sum(d.score * weights[d.dimension] for d in dims)
        ready = total >= self._threshold

        # Recommend action based on weakest dimension
        weakest = min(dims, key=lambda d: d.score)
        if ready:
            action = "proceed"
        elif weakest.dimension == ReadinessDimension.KNOWLEDGE:
            action = "gather_more_evidence"
        elif weakest.dimension == ReadinessDimension.SIMULATION:
            action = "define_simulation_parameters"
        elif weakest.dimension == ReadinessDimension.EXPERIMENT:
            action = "prepare_experiment_protocol"
        else:
            action = "check_infrastructure"

        result = ReadinessScore(
            dimensions=dims,
            overall=total,
            ready=ready,
            recommended_action=action,
        )

        logger.info(
            "readiness_scored",
            extra={
                "campaign_id": campaign.campaign_id,
                "overall": round(total, 3),
                "ready": ready,
                "action": action,
            },
        )

        return result

    def _score_knowledge(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> DimensionScore:
        """Score knowledge readiness: source count, confidence, coverage."""
        breakdown: dict[str, float] = {}

        # Source count
        total_sources = sum(len(a.sources) for a in artifacts)
        min_sources = context.get("min_sources", 3)
        breakdown["source_count"] = min(1.0, total_sources / max(min_sources, 1))

        # Confidence of findings
        if artifacts:
            avg_conf = sum(a.confidence for a in artifacts) / len(artifacts)
            breakdown["confidence"] = avg_conf
        else:
            breakdown["confidence"] = 0.0

        # Evidence diversity: how many evidence types are covered
        evidence_types = {a.evidence_type for a in artifacts}
        breakdown["diversity"] = min(1.0, len(evidence_types) / 3)

        # Coverage: do we have research artifacts at all?
        has_research = any(
            a.evidence_type in (EvidenceType.LITERATURE, EvidenceType.ANALYSIS)
            for a in artifacts
        )
        breakdown["coverage"] = 1.0 if has_research else 0.0

        weights = {"source_count": 0.3, "confidence": 0.35, "diversity": 0.15, "coverage": 0.2}
        score = sum(breakdown.get(k, 0) * w for k, w in weights.items())

        return DimensionScore(
            dimension=ReadinessDimension.KNOWLEDGE,
            score=score,
            breakdown=breakdown,
            notes=f"{len(artifacts)} artifacts, {total_sources} sources",
        )

    def _score_simulation(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> DimensionScore:
        """Score simulation readiness: parameter completeness, model spec."""
        breakdown: dict[str, float] = {}

        # Check if simulation steps exist in campaign
        sim_steps = [s for s in campaign.steps if s.command in ("simulate", "parametergolf")]
        has_sim = len(sim_steps) > 0
        breakdown["has_plan"] = 1.0 if has_sim else 0.0

        # Check simulation artifacts from prior work
        sim_artifacts = [a for a in artifacts if a.evidence_type == EvidenceType.SIMULATION]
        breakdown["prior_results"] = min(1.0, len(sim_artifacts) / 2)

        # Parameter quality from context
        params = context.get("simulation_parameters", {})
        if params:
            defined = sum(1 for v in params.values() if v is not None)
            breakdown["parameter_completeness"] = defined / max(len(params), 1)
        else:
            breakdown["parameter_completeness"] = 0.5 if has_sim else 0.0

        weights = {"has_plan": 0.3, "prior_results": 0.3, "parameter_completeness": 0.4}
        score = sum(breakdown.get(k, 0) * w for k, w in weights.items())

        return DimensionScore(
            dimension=ReadinessDimension.SIMULATION,
            score=score,
            breakdown=breakdown,
            notes=f"{len(sim_steps)} simulation steps planned",
        )

    def _score_experiment(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> DimensionScore:
        """Score experiment readiness: protocol, materials, safety, approval."""
        breakdown: dict[str, float] = {}

        # Protocol defined
        has_protocol = bool(context.get("protocol"))
        breakdown["protocol_defined"] = 1.0 if has_protocol else 0.0

        # Materials listed
        materials = context.get("materials", [])
        breakdown["materials_listed"] = 1.0 if materials else 0.0

        # Safety review
        safety_reviewed = context.get("safety_reviewed", False)
        breakdown["safety_reviewed"] = 1.0 if safety_reviewed else 0.0

        # Approval obtained (from campaign metadata)
        has_approval = campaign.approval_id is not None
        breakdown["approval_obtained"] = 1.0 if has_approval else 0.0

        weights = {"protocol_defined": 0.35, "materials_listed": 0.2, "safety_reviewed": 0.25, "approval_obtained": 0.2}
        score = sum(breakdown.get(k, 0) * w for k, w in weights.items())

        return DimensionScore(
            dimension=ReadinessDimension.EXPERIMENT,
            score=score,
            breakdown=breakdown,
            notes="experiment prerequisites check",
        )

    def _score_infrastructure(
        self,
        campaign: CampaignSchema,
        module_health: dict[str, ModuleHealth],
        context: dict[str, Any],
    ) -> DimensionScore:
        """Score infrastructure readiness: module health, budget, queue depth."""
        breakdown: dict[str, float] = {}

        # Module health: fraction of healthy modules
        if module_health:
            healthy = sum(
                1 for h in module_health.values()
                if h.status in (ModuleStatus.HEALTHY, ModuleStatus.DEGRADED)
            )
            breakdown["module_health"] = healthy / len(module_health)
        else:
            breakdown["module_health"] = 0.5  # unknown

        # Budget remaining
        budget_remaining = context.get("budget_remaining_usd")
        if budget_remaining is not None:
            breakdown["budget_available"] = min(1.0, budget_remaining / 5.0)
        else:
            breakdown["budget_available"] = 0.5  # unknown

        # Queue depth (lower is better)
        queue_depth = context.get("queue_depth", 0)
        breakdown["queue_capacity"] = max(0.0, 1.0 - queue_depth / 20.0)

        weights = {"module_health": 0.4, "budget_available": 0.35, "queue_capacity": 0.25}
        score = sum(breakdown.get(k, 0) * w for k, w in weights.items())

        return DimensionScore(
            dimension=ReadinessDimension.INFRASTRUCTURE,
            score=score,
            breakdown=breakdown,
            notes=f"{len(module_health)} modules tracked",
        )
