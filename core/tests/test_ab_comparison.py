"""Tests for the A/B comparison module."""
import pytest

from oas_core.rl.ab_comparison import ABComparison, ABResult


class TestABComparison:
    def test_evolved_wins(self):
        comp = ABComparison(tie_threshold=0.02)
        prompts = [
            {"prompt_id": f"p{i}", "prompt": f"Prompt {i}"}
            for i in range(10)
        ]
        result = comp.compare(
            agent_type="research",
            checkpoint_id="ckpt-001",
            baseline_version="v0",
            prompts=prompts,
            baseline_scorer=lambda p: 0.7,
            evolved_scorer=lambda p: 0.85,
        )
        assert result.evolved_avg > result.baseline_avg
        assert result.win_rate == 1.0
        assert result.loss_rate == 0.0
        assert result.delta > 0

    def test_baseline_wins(self):
        comp = ABComparison()
        prompts = [{"prompt_id": "p1", "prompt": "Test"}]
        result = comp.compare(
            agent_type="research",
            checkpoint_id="ckpt-002",
            baseline_version="v0",
            prompts=prompts,
            baseline_scorer=lambda p: 0.9,
            evolved_scorer=lambda p: 0.6,
        )
        assert result.loss_rate == 1.0
        assert result.delta < 0

    def test_ties(self):
        comp = ABComparison(tie_threshold=0.05)
        prompts = [{"prompt_id": "p1", "prompt": "Test"}]
        result = comp.compare(
            agent_type="research",
            checkpoint_id="ckpt-003",
            baseline_version="v0",
            prompts=prompts,
            baseline_scorer=lambda p: 0.80,
            evolved_scorer=lambda p: 0.81,  # Within threshold
        )
        assert result.tie_rate == 1.0

    def test_mixed_results(self):
        comp = ABComparison(tie_threshold=0.01)
        prompts = [
            {"prompt_id": "p1", "prompt": "Easy"},
            {"prompt_id": "p2", "prompt": "Hard"},
            {"prompt_id": "p3", "prompt": "Medium"},
        ]
        scores = {"Easy": (0.7, 0.9), "Hard": (0.8, 0.5), "Medium": (0.75, 0.75)}

        result = comp.compare(
            agent_type="research",
            checkpoint_id="ckpt-004",
            baseline_version="v0",
            prompts=prompts,
            baseline_scorer=lambda p: scores.get(p, (0.5, 0.5))[0],
            evolved_scorer=lambda p: scores.get(p, (0.5, 0.5))[1],
        )
        assert result.n_prompts == 3
        assert len(result.per_prompt) == 3
        # 1 win, 1 loss, 1 tie
        assert result.win_rate > 0
        assert result.loss_rate > 0

    def test_summary_string(self):
        comp = ABComparison()
        prompts = [{"prompt_id": "p1", "prompt": "Test"}]
        result = comp.compare(
            agent_type="research",
            checkpoint_id="ckpt-005",
            baseline_version="v0",
            prompts=prompts,
            baseline_scorer=lambda p: 0.7,
            evolved_scorer=lambda p: 0.85,
        )
        assert "research" in result.summary
        assert "baseline=" in result.summary
        assert "evolved=" in result.summary

    def test_empty_prompts(self):
        comp = ABComparison()
        result = comp.compare(
            agent_type="research",
            checkpoint_id="ckpt-006",
            baseline_version="v0",
            prompts=[],
            baseline_scorer=lambda p: 0.7,
            evolved_scorer=lambda p: 0.85,
        )
        assert result.n_prompts == 0
        assert result.baseline_avg == 0.0
