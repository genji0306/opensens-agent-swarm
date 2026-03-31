"""Tests for the RL promotion gate."""
import pytest

from oas_core.rl.promotion_gate import PromotionGate, PromotionDecision


class TestPromotionGate:
    def setup_method(self):
        self.gate = PromotionGate(min_score=0.7, catastrophic_threshold=0.3)

    def test_promotes_when_all_gates_pass(self):
        result = self.gate.evaluate(
            checkpoint_id="research-ckpt-001",
            eval_score=0.85,
            baseline_score=0.72,
            previous_promoted_score=0.80,
        )
        assert result.promoted is True
        assert "+0.130" in result.reason

    def test_rejects_below_min_score(self):
        result = self.gate.evaluate(
            checkpoint_id="research-ckpt-002",
            eval_score=0.65,
            baseline_score=0.72,
        )
        assert result.promoted is False
        assert "below minimum" in result.reason

    def test_rejects_regression_vs_baseline(self):
        result = self.gate.evaluate(
            checkpoint_id="research-ckpt-003",
            eval_score=0.71,
            baseline_score=0.75,
        )
        assert result.promoted is False
        assert "regressed vs baseline" in result.reason

    def test_rejects_regression_vs_previous_promoted(self):
        result = self.gate.evaluate(
            checkpoint_id="research-ckpt-004",
            eval_score=0.80,
            baseline_score=0.72,
            previous_promoted_score=0.82,
        )
        assert result.promoted is False
        assert "below previous promoted" in result.reason

    def test_rejects_catastrophic_failure(self):
        result = self.gate.evaluate(
            checkpoint_id="research-ckpt-005",
            eval_score=0.85,
            baseline_score=0.72,
            per_prompt_scores=[
                {"prompt_id": "p001", "score": 0.92},
                {"prompt_id": "p002", "score": 0.15},  # Catastrophic
            ],
        )
        assert result.promoted is False
        assert "Catastrophic failure" in result.reason
        assert "p002" in result.reason

    def test_skips_previous_check_when_zero(self):
        """If no previous promoted checkpoint, skip that check."""
        result = self.gate.evaluate(
            checkpoint_id="research-ckpt-006",
            eval_score=0.75,
            baseline_score=0.72,
            previous_promoted_score=0.0,
        )
        assert result.promoted is True

    def test_decision_fields(self):
        result = self.gate.evaluate(
            checkpoint_id="test-ckpt",
            eval_score=0.85,
            baseline_score=0.70,
            previous_promoted_score=0.80,
        )
        assert result.checkpoint_id == "test-ckpt"
        assert result.score == 0.85
        assert result.baseline_score == 0.70
        assert result.previous_promoted_score == 0.80
