"""Tests for the decision policy engine."""

import pytest

from oas_core.decision.policy_engine import (
    DecisionAction,
    DecisionPolicyEngine,
    DecisionRecommendation,
    PolicyRule,
    CostCeilingRule,
    ConfidenceFloorRule,
    MaxRetriesRule,
    HumanEscalationRule,
    IdleBudgetRule,
)
from oas_core.schemas.campaign import (
    CampaignSchema,
    CampaignStepSchema,
    CampaignStatus,
    CostAttribution,
)
from oas_core.schemas.intents import KnowledgeArtifact, EvidenceType


def _make_campaign(**kwargs):
    return CampaignSchema(
        campaign_id="test_camp",
        title="Test Campaign",
        objective="Test quantum sensors",
        **kwargs,
    )


def _make_artifact(confidence=0.7, evidence_type=EvidenceType.LITERATURE):
    return KnowledgeArtifact(
        campaign_id="test_camp",
        findings="Some findings",
        confidence=confidence,
        evidence_type=evidence_type,
        sources=[{"title": "Paper A"}],
    )


class TestCostCeilingRule:
    def test_passes_under_ceiling(self):
        rule = CostCeilingRule(max_cost_usd=10.0)
        campaign = _make_campaign()
        assert rule.evaluate(campaign, [], {}) is None

    def test_blocks_over_ceiling(self):
        rule = CostCeilingRule(max_cost_usd=5.0)
        steps = [
            CampaignStepSchema(step=1, command="research", cost=CostAttribution(
                campaign_id="test", model="claude", cost_usd=3.0
            )),
            CampaignStepSchema(step=2, command="simulate", cost=CostAttribution(
                campaign_id="test", model="claude", cost_usd=3.0
            )),
        ]
        campaign = _make_campaign(steps=steps)
        v = rule.evaluate(campaign, [], {})
        assert v is not None
        assert v.severity == "block"
        assert "$6.00" in v.message


class TestConfidenceFloorRule:
    def test_passes_with_good_confidence(self):
        rule = ConfidenceFloorRule(min_confidence=0.4)
        artifacts = [_make_artifact(confidence=0.8)]
        assert rule.evaluate(_make_campaign(), artifacts, {}) is None

    def test_warns_low_confidence(self):
        rule = ConfidenceFloorRule(min_confidence=0.5)
        artifacts = [_make_artifact(confidence=0.2), _make_artifact(confidence=0.3)]
        v = rule.evaluate(_make_campaign(), artifacts, {})
        assert v is not None
        assert v.severity == "warn"

    def test_no_artifacts_passes(self):
        rule = ConfidenceFloorRule()
        assert rule.evaluate(_make_campaign(), [], {}) is None


class TestMaxRetriesRule:
    def test_passes_under_limit(self):
        rule = MaxRetriesRule(max_retries=3)
        assert rule.evaluate(_make_campaign(), [], {"retry_count": 1}) is None

    def test_blocks_at_limit(self):
        rule = MaxRetriesRule(max_retries=3)
        v = rule.evaluate(_make_campaign(), [], {"retry_count": 3})
        assert v is not None
        assert v.severity == "block"


class TestHumanEscalationRule:
    def test_passes_low_failure_rate(self):
        rule = HumanEscalationRule()
        steps = [
            CampaignStepSchema(step=1, command="research", status="completed"),
            CampaignStepSchema(step=2, command="simulate", status="completed"),
        ]
        campaign = _make_campaign(steps=steps)
        assert rule.evaluate(campaign, [], {}) is None

    def test_warns_high_failure_rate(self):
        rule = HumanEscalationRule(failure_rate_threshold=0.5)
        steps = [
            CampaignStepSchema(step=1, command="research", status="completed"),
            CampaignStepSchema(step=2, command="simulate", status="failed"),
        ]
        campaign = _make_campaign(steps=steps)
        v = rule.evaluate(campaign, [], {})
        assert v is not None
        assert "50%" in v.message


class TestIdleBudgetRule:
    def test_blocks_background_work_over_idle_cap(self):
        rule = IdleBudgetRule(max_idle_spend_ratio=0.2)
        violation = rule.evaluate(
            _make_campaign(),
            [],
            {"action_scope": "kairos", "daily_spend_ratio": 0.35},
        )
        assert violation is not None
        assert violation.severity == "block"
        assert "Idle work blocked" in violation.message

    def test_ignores_non_idle_scope(self):
        rule = IdleBudgetRule(max_idle_spend_ratio=0.2)
        assert rule.evaluate(
            _make_campaign(),
            [],
            {"action_scope": "foreground", "daily_spend_ratio": 0.9},
        ) is None


class TestDecisionPolicyEngine:
    def test_recommend_proceed_no_violations(self):
        engine = DecisionPolicyEngine()
        steps = [
            CampaignStepSchema(step=1, command="research", status="completed"),
            CampaignStepSchema(step=2, command="simulate", status="pending"),
        ]
        campaign = _make_campaign(steps=steps)
        artifacts = [_make_artifact(confidence=0.8)]
        rec = engine.recommend(campaign, artifacts, {"current_module": "leader"})
        assert rec.action in (
            DecisionAction.HANDOFF_TO,
            DecisionAction.PROCEED_TO_NEXT_STEP,
        )
        assert rec.confidence > 0

    def test_recommend_escalate_on_cost_block(self):
        engine = DecisionPolicyEngine(rules=[CostCeilingRule(max_cost_usd=1.0)])
        steps = [
            CampaignStepSchema(step=1, command="research", cost=CostAttribution(
                campaign_id="test", model="claude", cost_usd=2.0
            )),
        ]
        campaign = _make_campaign(steps=steps)
        rec = engine.recommend(campaign, [])
        assert rec.action == DecisionAction.ESCALATE_TO_HUMAN

    def test_recommend_stop_on_max_retries(self):
        engine = DecisionPolicyEngine(rules=[MaxRetriesRule(max_retries=2)])
        campaign = _make_campaign()
        rec = engine.recommend(campaign, [], {"retry_count": 5})
        assert rec.action == DecisionAction.STOP_INSUFFICIENT_EVIDENCE

    def test_recommend_retry_on_low_confidence(self):
        engine = DecisionPolicyEngine(rules=[ConfidenceFloorRule(min_confidence=0.6)])
        campaign = _make_campaign(steps=[
            CampaignStepSchema(step=1, command="research", status="pending"),
        ])
        artifacts = [_make_artifact(confidence=0.2)]
        rec = engine.recommend(campaign, artifacts)
        assert rec.action == DecisionAction.RETRY_WITH_REFINEMENT

    def test_recommend_handoff_different_module(self):
        engine = DecisionPolicyEngine(rules=[])
        steps = [
            CampaignStepSchema(step=1, command="research", status="completed"),
            CampaignStepSchema(step=2, command="simulate", status="pending"),
        ]
        campaign = _make_campaign(steps=steps)
        artifacts = [_make_artifact(confidence=0.9)]
        rec = engine.recommend(campaign, artifacts, {"current_module": "academic"})
        assert rec.action == DecisionAction.HANDOFF_TO
        assert rec.target_module == "experiment"

    def test_add_rule(self):
        engine = DecisionPolicyEngine(rules=[])
        assert len(engine.rules) == 0
        engine.add_rule(CostCeilingRule())
        assert len(engine.rules) == 1

    def test_recommendation_to_dict(self):
        rec = DecisionRecommendation(
            action=DecisionAction.PROCEED_TO_NEXT_STEP,
            confidence=0.85,
            reasoning="All good",
        )
        d = rec.to_dict()
        assert d["action"] == "proceed_to_next_step"
        assert d["confidence"] == 0.85

    def test_all_steps_completed(self):
        engine = DecisionPolicyEngine(rules=[])
        steps = [
            CampaignStepSchema(step=1, command="research", status="completed"),
        ]
        campaign = _make_campaign(steps=steps)
        rec = engine.recommend(campaign, [])
        assert rec.action == DecisionAction.PROCEED_TO_NEXT_STEP
        assert "completed" in rec.reasoning.lower()
