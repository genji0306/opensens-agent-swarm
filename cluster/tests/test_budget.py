"""Tests for LLM client budget enforcement."""
import json
import time
from pathlib import Path
from unittest.mock import patch

from shared.llm_client import _estimate_cost, _budget_file, _check_and_record_spend


class TestEstimateCost:
    def test_known_model(self):
        # claude-opus: $0.015/1K input, $0.075/1K output
        cost = _estimate_cost("claude-opus-4-6-20260301", 1000, 1000)
        assert abs(cost - 0.090) < 1e-6

    def test_free_tier(self):
        cost = _estimate_cost("gemini-2.0-flash", 5000, 2000)
        assert cost == 0.0

    def test_unknown_model_uses_default(self):
        # Default: $0.003/1K input, $0.015/1K output
        cost = _estimate_cost("unknown-model", 1000, 1000)
        assert abs(cost - 0.018) < 1e-6

    def test_zero_tokens(self):
        cost = _estimate_cost("gpt-4o", 0, 0)
        assert cost == 0.0


class TestBudgetFile:
    def test_path_contains_date(self):
        today = time.strftime("%Y-%m-%d")
        bf = _budget_file()
        assert today in str(bf)
        assert str(bf).endswith(".json")


class TestCheckAndRecordSpend:
    def test_record_and_read(self, tmp_path):
        with patch("shared.llm_client.settings") as mock_settings:
            mock_settings.darklab_home = tmp_path
            mock_settings.darklab_role = "academic"

            # Record a spend
            _check_and_record_spend(0.05, "anthropic", "claude-sonnet-4-6-20260301")

            # Record another
            _check_and_record_spend(0.03, "openai", "gpt-4o")

            # Verify file content
            bf = _budget_file()
            data = json.loads(bf.read_text())
            assert abs(data["total_usd"] - 0.08) < 1e-6
            assert len(data["calls"]) == 2
            assert data["calls"][0]["provider"] == "anthropic"
            assert data["calls"][1]["provider"] == "openai"

    def test_under_budget(self, tmp_path):
        with patch("shared.llm_client.settings") as mock_settings:
            mock_settings.darklab_home = tmp_path
            mock_settings.darklab_role = "academic"
            # Academic budget is $30 — should not raise
            _check_and_record_spend(1.0, "anthropic", "test-model")

    def test_over_budget(self, tmp_path):
        with patch("shared.llm_client.settings") as mock_settings:
            mock_settings.darklab_home = tmp_path
            mock_settings.darklab_role = "experiment"

            # Write a spend file that exceeds experiment budget ($20)
            bf = _budget_file()
            bf.parent.mkdir(parents=True, exist_ok=True)
            bf.write_text(json.dumps({"total_usd": 25.0, "calls": []}))

            try:
                _check_and_record_spend(1.0, "anthropic", "test-model")
                assert False, "Should have raised RuntimeError"
            except RuntimeError as e:
                assert "budget exceeded" in str(e).lower()
