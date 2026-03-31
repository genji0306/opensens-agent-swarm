"""Tests for multi-layer readiness scoring."""

import pytest

from oas_core.decision.readiness import (
    ReadinessDimension,
    ReadinessScore,
    ReadinessScorer,
)
from oas_core.schemas.campaign import CampaignSchema, CampaignStepSchema
from oas_core.schemas.intents import KnowledgeArtifact, EvidenceType
from oas_core.registry.capability import ModuleHealth, ModuleStatus


def _make_campaign(**kwargs):
    return CampaignSchema(campaign_id="test", objective="Test", **kwargs)


def _make_artifact(confidence=0.7, evidence_type=EvidenceType.LITERATURE, n_sources=3):
    return KnowledgeArtifact(
        campaign_id="test",
        findings="findings",
        confidence=confidence,
        evidence_type=evidence_type,
        sources=[{"title": f"Source {i}"} for i in range(n_sources)],
    )


class TestReadinessScorer:
    def test_score_returns_all_dimensions(self):
        scorer = ReadinessScorer()
        campaign = _make_campaign()
        result = scorer.score(campaign, [])
        assert len(result.dimensions) == 4
        dims = {d.dimension for d in result.dimensions}
        assert dims == {
            ReadinessDimension.KNOWLEDGE,
            ReadinessDimension.SIMULATION,
            ReadinessDimension.EXPERIMENT,
            ReadinessDimension.INFRASTRUCTURE,
        }

    def test_high_readiness_with_good_artifacts(self):
        scorer = ReadinessScorer(threshold=0.3)
        campaign = _make_campaign()
        artifacts = [
            _make_artifact(confidence=0.9, evidence_type=EvidenceType.LITERATURE),
            _make_artifact(confidence=0.8, evidence_type=EvidenceType.ANALYSIS),
        ]
        health = {"academic": ModuleHealth(status=ModuleStatus.HEALTHY)}
        result = scorer.score(campaign, artifacts, health, {"budget_remaining_usd": 20.0})
        assert result.ready is True
        assert result.overall > 0.3

    def test_low_readiness_no_artifacts(self):
        scorer = ReadinessScorer(threshold=0.7)
        campaign = _make_campaign()
        result = scorer.score(campaign, [])
        assert result.ready is False
        assert result.recommended_action == "gather_more_evidence"

    def test_infrastructure_readiness_with_health(self):
        scorer = ReadinessScorer()
        campaign = _make_campaign()
        health = {
            "academic": ModuleHealth(status=ModuleStatus.HEALTHY),
            "experiment": ModuleHealth(status=ModuleStatus.UNHEALTHY),
        }
        result = scorer.score(campaign, [], health)
        infra = result.get(ReadinessDimension.INFRASTRUCTURE)
        assert 0 < infra < 1  # one healthy, one unhealthy

    def test_simulation_readiness_with_steps(self):
        scorer = ReadinessScorer()
        campaign = _make_campaign(steps=[
            CampaignStepSchema(step=1, command="simulate", args="test"),
        ])
        result = scorer.score(campaign, [])
        sim = result.get(ReadinessDimension.SIMULATION)
        assert sim > 0  # has simulation plan

    def test_experiment_readiness_with_context(self):
        scorer = ReadinessScorer()
        campaign = _make_campaign(approval_id="appr_123")
        result = scorer.score(campaign, [], context={
            "protocol": "EIT protocol v2",
            "materials": ["quantum dots", "buffer"],
            "safety_reviewed": True,
        })
        exp = result.get(ReadinessDimension.EXPERIMENT)
        assert exp > 0.8

    def test_to_dict(self):
        scorer = ReadinessScorer()
        result = scorer.score(_make_campaign(), [])
        d = result.to_dict()
        assert "overall" in d
        assert "dimensions" in d
        assert "knowledge" in d["dimensions"]

    def test_get_missing_dimension(self):
        result = ReadinessScore()
        assert result.get(ReadinessDimension.KNOWLEDGE) == 0.0
