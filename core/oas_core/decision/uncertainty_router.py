"""Uncertainty-aware routing — wraps dispatch with readiness checks.

Before routing a task to a module, checks readiness scores and suggests
prerequisite steps if the campaign isn't ready. Ranks viable modules by
(readiness * confidence / cost) to pick the optimal target.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from oas_core.schemas.campaign import CampaignSchema
from oas_core.schemas.intents import KnowledgeArtifact
from oas_core.decision.readiness import ReadinessScorer, ReadinessScore, ReadinessDimension
from oas_core.decision.policy_engine import DecisionAction
from oas_core.registry.capability import ModuleHealth, CostEstimate

__all__ = [
    "UncertaintyRouter",
    "RoutingDecision",
]

logger = logging.getLogger("oas.decision.uncertainty_router")


@dataclass
class ModuleCandidate:
    """A candidate module for routing with scoring."""

    name: str
    readiness: float = 0.0
    confidence: float = 0.0
    estimated_cost: float = 0.0
    composite_score: float = 0.0


@dataclass
class RoutingDecision:
    """Result of uncertainty-aware routing analysis."""

    should_proceed: bool
    target_module: str = ""
    confidence: float = 0.0
    prerequisites: list[str] = field(default_factory=list)
    reasoning: str = ""
    alternatives: list[ModuleCandidate] = field(default_factory=list)
    readiness: ReadinessScore | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "should_proceed": self.should_proceed,
            "target_module": self.target_module,
            "confidence": round(self.confidence, 3),
            "prerequisites": self.prerequisites,
            "reasoning": self.reasoning,
        }
        if self.alternatives:
            result["alternatives"] = [
                {
                    "name": a.name,
                    "readiness": round(a.readiness, 3),
                    "confidence": round(a.confidence, 3),
                    "cost": round(a.estimated_cost, 4),
                    "score": round(a.composite_score, 3),
                }
                for a in self.alternatives
            ]
        if self.readiness:
            result["readiness"] = self.readiness.to_dict()
        return result


# Command → prerequisite steps when readiness is low
_PREREQUISITE_MAP: dict[str, list[str]] = {
    "simulate": ["research", "doe"],
    "parametergolf": ["research", "doe"],
    "analyze": ["simulate"],
    "synthesize": ["research", "analyze"],
    "report": ["synthesize"],
    "paper": ["research", "synthesize"],
}

# Command → required readiness dimension
_COMMAND_READINESS: dict[str, ReadinessDimension] = {
    "research": ReadinessDimension.KNOWLEDGE,
    "literature": ReadinessDimension.KNOWLEDGE,
    "perplexity": ReadinessDimension.KNOWLEDGE,
    "deepresearch": ReadinessDimension.KNOWLEDGE,
    "deerflow": ReadinessDimension.KNOWLEDGE,
    "doe": ReadinessDimension.KNOWLEDGE,
    "simulate": ReadinessDimension.SIMULATION,
    "parametergolf": ReadinessDimension.SIMULATION,
    "analyze": ReadinessDimension.SIMULATION,
    "synthesize": ReadinessDimension.KNOWLEDGE,
    "report": ReadinessDimension.KNOWLEDGE,
    "paper": ReadinessDimension.KNOWLEDGE,
}

# Command → target module
_COMMAND_MODULE: dict[str, str] = {
    "research": "academic",
    "literature": "academic",
    "doe": "academic",
    "paper": "academic",
    "perplexity": "academic",
    "simulate": "experiment",
    "analyze": "experiment",
    "synthetic": "experiment",
    "report-data": "experiment",
    "autoresearch": "experiment",
    "parametergolf": "experiment",
    "synthesize": "leader",
    "report": "leader",
    "deerflow": "leader",
    "deepresearch": "leader",
    "swarmresearch": "leader",
    "debate": "leader",
}


class UncertaintyRouter:
    """Pre-routing check that evaluates readiness before dispatching.

    Usage::

        router = UncertaintyRouter()
        decision = router.evaluate(
            command="simulate",
            campaign=campaign,
            artifacts=artifacts,
            module_health=health_map,
        )
        if decision.should_proceed:
            await dispatch(command, args)
        else:
            for prereq in decision.prerequisites:
                await dispatch(prereq, ...)
    """

    def __init__(
        self,
        readiness_scorer: ReadinessScorer | None = None,
        readiness_threshold: float = 0.4,
    ):
        self._scorer = readiness_scorer or ReadinessScorer()
        self._threshold = readiness_threshold

    def evaluate(
        self,
        command: str,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        module_health: dict[str, ModuleHealth] | None = None,
        module_costs: dict[str, CostEstimate] | None = None,
        context: dict[str, Any] | None = None,
    ) -> RoutingDecision:
        """Evaluate whether a command should proceed given current readiness."""
        ctx = context or {}
        target_module = _COMMAND_MODULE.get(command, "leader")

        # Score readiness
        readiness = self._scorer.score(campaign, artifacts, module_health, ctx)

        # Check the relevant dimension for this command
        required_dim = _COMMAND_READINESS.get(command, ReadinessDimension.INFRASTRUCTURE)
        dim_score = readiness.get(required_dim)
        infra_score = readiness.get(ReadinessDimension.INFRASTRUCTURE)

        # Infrastructure must always be viable
        if infra_score < 0.2:
            return RoutingDecision(
                should_proceed=False,
                target_module=target_module,
                confidence=0.9,
                prerequisites=["check_infrastructure"],
                reasoning=f"Infrastructure readiness too low ({infra_score:.2f})",
                readiness=readiness,
            )

        # Check readiness for the command's dimension
        if dim_score >= self._threshold:
            # Ready to proceed — rank module candidates
            candidates = self._rank_candidates(
                command, target_module, readiness, module_costs or {}
            )

            best = candidates[0] if candidates else None
            return RoutingDecision(
                should_proceed=True,
                target_module=best.name if best else target_module,
                confidence=best.composite_score if best else dim_score,
                reasoning=f"{required_dim.value} readiness {dim_score:.2f} meets threshold",
                alternatives=candidates[1:] if len(candidates) > 1 else [],
                readiness=readiness,
            )

        # Not ready — suggest prerequisites
        prereqs = _PREREQUISITE_MAP.get(command, [])
        if not prereqs:
            # No known prerequisites; suggest generic research first
            prereqs = ["research"]

        return RoutingDecision(
            should_proceed=False,
            target_module=target_module,
            confidence=dim_score,
            prerequisites=prereqs,
            reasoning=(
                f"{required_dim.value} readiness {dim_score:.2f} "
                f"below threshold {self._threshold:.2f}; "
                f"suggest running {', '.join('/' + p for p in prereqs)} first"
            ),
            readiness=readiness,
        )

    def _rank_candidates(
        self,
        command: str,
        primary_module: str,
        readiness: ReadinessScore,
        module_costs: dict[str, CostEstimate],
    ) -> list[ModuleCandidate]:
        """Rank module candidates by composite score."""
        candidates = []

        # Primary module
        primary_cost = module_costs.get(primary_module, CostEstimate())
        primary_conf = primary_cost.confidence if primary_cost else 0.5
        cost_val = max(primary_cost.estimated_cost_usd, 0.001)

        candidates.append(ModuleCandidate(
            name=primary_module,
            readiness=readiness.overall,
            confidence=primary_conf,
            estimated_cost=cost_val,
            composite_score=readiness.overall * primary_conf / cost_val,
        ))

        # Add alternatives from cost map
        for module_name, cost_est in module_costs.items():
            if module_name == primary_module:
                continue
            cost_v = max(cost_est.estimated_cost_usd, 0.001)
            score = readiness.overall * cost_est.confidence / cost_v
            candidates.append(ModuleCandidate(
                name=module_name,
                readiness=readiness.overall,
                confidence=cost_est.confidence,
                estimated_cost=cost_v,
                composite_score=score,
            ))

        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        return candidates
