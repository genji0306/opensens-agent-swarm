"""Tests for the IdleBudgetRule in the decision policy engine."""
from __future__ import annotations

import pytest

from oas_core.decision.policy_engine import IdleBudgetRule
from oas_core.schemas.campaign import CampaignSchema
from oas_core.schemas.intents import KnowledgeArtifact, EvidenceType


def _make_campaign(**kwargs):
    return CampaignSchema(
        campaign_id="test_camp",
        title="Test Campaign",
        objective="Test quantum sensors",
        **kwargs,
    )


class TestIdleBudgetRule:
    def test_blocks_kairos_when_over_budget(self):
        """Kairos-scoped work is blocked when daily spend exceeds idle cap."""
        rule = IdleBudgetRule(max_idle_spend_ratio=0.2)
        violation = rule.evaluate(
            _make_campaign(),
            [],
            {"action_scope": "kairos", "daily_spend_ratio": 0.35},
        )
        assert violation is not None
        assert violation.severity == "block"
        assert violation.rule_name == "idle_budget"
        assert "Idle work blocked" in violation.message

    def test_allows_kairos_when_under_budget(self):
        """Kairos-scoped work is allowed when under the idle cap."""
        rule = IdleBudgetRule(max_idle_spend_ratio=0.2)
        violation = rule.evaluate(
            _make_campaign(),
            [],
            {"action_scope": "kairos", "daily_spend_ratio": 0.10},
        )
        assert violation is None

    def test_allows_non_idle_tasks_regardless_of_budget(self):
        """Non-idle action scopes are never blocked by this rule."""
        rule = IdleBudgetRule(max_idle_spend_ratio=0.2)
        # Foreground scope at 90% spend should pass
        assert rule.evaluate(
            _make_campaign(),
            [],
            {"action_scope": "foreground", "daily_spend_ratio": 0.9},
        ) is None
        # Empty scope should pass
        assert rule.evaluate(
            _make_campaign(),
            [],
            {"action_scope": "", "daily_spend_ratio": 0.9},
        ) is None
        # Missing scope should pass
        assert rule.evaluate(
            _make_campaign(),
            [],
            {"daily_spend_ratio": 0.9},
        ) is None

    def test_custom_threshold(self):
        """Custom threshold correctly gates idle work."""
        rule = IdleBudgetRule(max_idle_spend_ratio=0.5)
        # 40% spend with 50% cap -- should allow
        assert rule.evaluate(
            _make_campaign(),
            [],
            {"action_scope": "idle", "daily_spend_ratio": 0.40},
        ) is None
        # 60% spend with 50% cap -- should block
        violation = rule.evaluate(
            _make_campaign(),
            [],
            {"action_scope": "idle", "daily_spend_ratio": 0.60},
        )
        assert violation is not None
        assert "60%" in violation.message

    def test_computes_ratio_from_spend_and_budget(self):
        """Rule can compute ratio from daily_spend_usd and daily_budget_usd."""
        rule = IdleBudgetRule(max_idle_spend_ratio=0.2)
        # $15 of $50 = 30%, should block
        violation = rule.evaluate(
            _make_campaign(),
            [],
            {
                "action_scope": "background",
                "daily_spend_usd": 15.0,
                "daily_budget_usd": 50.0,
            },
        )
        assert violation is not None

        # $5 of $50 = 10%, should allow
        assert rule.evaluate(
            _make_campaign(),
            [],
            {
                "action_scope": "background",
                "daily_spend_usd": 5.0,
                "daily_budget_usd": 50.0,
            },
        ) is None
