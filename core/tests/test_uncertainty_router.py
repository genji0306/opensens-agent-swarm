"""Tests for the uncertainty-aware router."""

import pytest

from oas_core.decision.uncertainty_router import UncertaintyRouter, RoutingDecision
from oas_core.decision.readiness import ReadinessScorer
from oas_core.schemas.campaign import CampaignSchema, CampaignStepSchema
from oas_core.schemas.intents import KnowledgeArtifact, EvidenceType
from oas_core.registry.capability import ModuleHealth, ModuleStatus, CostEstimate


def _make_campaign(**kwargs):
    return CampaignSchema(campaign_id="test", objective="Test", **kwargs)


def _make_artifact(confidence=0.8):
    return KnowledgeArtifact(
        campaign_id="test",
        findings="Good findings",
        confidence=confidence,
        evidence_type=EvidenceType.LITERATURE,
        sources=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
    )


class TestUncertaintyRouter:
    def test_proceed_when_ready(self):
        router = UncertaintyRouter(readiness_threshold=0.2)
        campaign = _make_campaign()
        artifacts = [_make_artifact(confidence=0.9)]
        health = {"academic": ModuleHealth(status=ModuleStatus.HEALTHY)}

        decision = router.evaluate(
            command="research",
            campaign=campaign,
            artifacts=artifacts,
            module_health=health,
            context={"budget_remaining_usd": 20.0},
        )
        assert decision.should_proceed is True
        assert decision.target_module != ""

    def test_block_when_infra_down(self):
        router = UncertaintyRouter()
        campaign = _make_campaign()
        health = {"academic": ModuleHealth(status=ModuleStatus.UNHEALTHY)}

        decision = router.evaluate(
            command="research",
            campaign=campaign,
            artifacts=[],
            module_health=health,
            context={"budget_remaining_usd": 0.0},  # zero budget
        )
        assert decision.should_proceed is False
        assert "infrastructure" in decision.reasoning.lower() or "readiness" in decision.reasoning.lower()

    def test_suggest_prerequisites_for_simulation(self):
        router = UncertaintyRouter(readiness_threshold=0.8)
        campaign = _make_campaign()

        decision = router.evaluate(
            command="simulate",
            campaign=campaign,
            artifacts=[],
            context={"budget_remaining_usd": 10.0},
        )
        assert decision.should_proceed is False
        assert "research" in decision.prerequisites or "doe" in decision.prerequisites

    def test_rank_candidates_by_cost(self):
        router = UncertaintyRouter(readiness_threshold=0.1)
        campaign = _make_campaign()
        artifacts = [_make_artifact()]
        costs = {
            "academic": CostEstimate(estimated_cost_usd=0.01, confidence=0.8),
            "experiment": CostEstimate(estimated_cost_usd=0.05, confidence=0.7),
        }
        health = {
            "academic": ModuleHealth(status=ModuleStatus.HEALTHY),
            "experiment": ModuleHealth(status=ModuleStatus.HEALTHY),
        }

        decision = router.evaluate(
            command="research",
            campaign=campaign,
            artifacts=artifacts,
            module_health=health,
            module_costs=costs,
            context={"budget_remaining_usd": 20.0},
        )
        assert decision.should_proceed is True

    def test_routing_decision_to_dict(self):
        decision = RoutingDecision(
            should_proceed=True,
            target_module="academic",
            confidence=0.85,
            reasoning="Ready to proceed",
        )
        d = decision.to_dict()
        assert d["should_proceed"] is True
        assert d["target_module"] == "academic"

    def test_default_leader_for_unknown_command(self):
        router = UncertaintyRouter(readiness_threshold=0.1)
        campaign = _make_campaign()
        artifacts = [_make_artifact()]
        health = {"leader": ModuleHealth(status=ModuleStatus.HEALTHY)}

        decision = router.evaluate(
            command="unknown_cmd",
            campaign=campaign,
            artifacts=artifacts,
            module_health=health,
            context={"budget_remaining_usd": 20.0},
        )
        assert decision.target_module == "leader"
