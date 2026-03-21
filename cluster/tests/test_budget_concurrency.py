"""Stress tests for budget enforcement under concurrent access.

Validates that the file-lock approach in llm_client.py correctly handles
multiple simultaneous callers without data corruption or budget over-runs.
"""
import json
import multiprocessing
import time
from unittest.mock import patch

import pytest

from shared.llm_client import (
    _check_and_record_spend,
    _budget_file,
    DAILY_BUDGETS,
)


def _worker_record_spend(args):
    """Worker function for multiprocessing: records a small spend."""
    tmp_dir, cost, worker_id = args
    with patch("shared.llm_client.settings") as mock_settings:
        mock_settings.darklab_home = tmp_dir
        mock_settings.darklab_role = "leader"
        try:
            _check_and_record_spend(cost, "anthropic", f"test-model-{worker_id}")
            return ("ok", worker_id)
        except RuntimeError:
            return ("budget_exceeded", worker_id)
        except Exception as e:
            return ("error", str(e))


def _worker_check_and_record(args):
    """Worker function for multiprocessing: atomic check-and-record."""
    tmp_dir, cost, worker_id = args
    with patch("shared.llm_client.settings") as mock_settings:
        mock_settings.darklab_home = tmp_dir
        mock_settings.darklab_role = "experiment"
        try:
            _check_and_record_spend(cost, "anthropic", f"test-model-{worker_id}")
            return ("ok", worker_id)
        except RuntimeError as e:
            if "budget exceeded" in str(e).lower():
                return ("budget_exceeded", worker_id)
            return ("error", str(e))
        except Exception as e:
            return ("error", str(e))


class TestConcurrentRecordSpend:
    """Test that _record_spend handles concurrent writes without data loss."""

    def test_concurrent_writes_no_data_loss(self, tmp_path):
        """Spawn N workers all writing small costs; total must match sum."""
        n_workers = 20
        cost_per_call = 0.05
        expected_total = n_workers * cost_per_call

        args = [(str(tmp_path), cost_per_call, i) for i in range(n_workers)]

        with multiprocessing.Pool(processes=min(n_workers, 8)) as pool:
            results = pool.map(_worker_record_spend, args)

        # All should succeed
        assert all(r[0] == "ok" for r in results), f"Some workers failed: {results}"

        # Read back and verify total
        with patch("shared.llm_client.settings") as mock_settings:
            mock_settings.darklab_home = tmp_path
            bf = _budget_file()
            total = json.loads(bf.read_text()).get("total_usd", 0.0)

        assert abs(total - expected_total) < 1e-6, (
            f"Expected ${expected_total:.2f}, got ${total:.2f} — data loss detected"
        )

    def test_concurrent_writes_correct_call_count(self, tmp_path):
        """Verify all individual call records are preserved."""
        n_workers = 15
        args = [(str(tmp_path), 0.01, i) for i in range(n_workers)]

        with multiprocessing.Pool(processes=min(n_workers, 8)) as pool:
            pool.map(_worker_record_spend, args)

        with patch("shared.llm_client.settings") as mock_settings:
            mock_settings.darklab_home = tmp_path
            bf = _budget_file()
            data = json.loads(bf.read_text())

        assert len(data["calls"]) == n_workers, (
            f"Expected {n_workers} call records, got {len(data['calls'])}"
        )


class TestConcurrentCheckAndRecord:
    """Test that _check_and_record_spend enforces budget atomically."""

    def test_budget_not_exceeded_under_concurrency(self, tmp_path):
        """Experiment budget is $20. Spawn 25 workers each spending $1.
        At most 20 should succeed; the rest should get budget_exceeded.
        """
        n_workers = 25
        cost_per_call = 1.0
        budget_limit = DAILY_BUDGETS["experiment"]  # $20

        args = [(str(tmp_path), cost_per_call, i) for i in range(n_workers)]

        with multiprocessing.Pool(processes=min(n_workers, 8)) as pool:
            results = pool.map(_worker_check_and_record, args)

        ok_count = sum(1 for r in results if r[0] == "ok")
        exceeded_count = sum(1 for r in results if r[0] == "budget_exceeded")
        error_count = sum(1 for r in results if r[0] == "error")

        assert error_count == 0, f"Unexpected errors: {[r for r in results if r[0] == 'error']}"
        assert ok_count <= int(budget_limit / cost_per_call), (
            f"Too many succeeded: {ok_count} (budget allows {int(budget_limit / cost_per_call)})"
        )
        assert ok_count + exceeded_count == n_workers

        # Verify final spend does not exceed budget
        with patch("shared.llm_client.settings") as mock_settings:
            mock_settings.darklab_home = tmp_path
            bf = _budget_file()
            final_spend = json.loads(bf.read_text()).get("total_usd", 0.0)

        assert final_spend <= budget_limit, (
            f"Budget exceeded: ${final_spend:.2f} > ${budget_limit:.2f}"
        )

    def test_all_succeed_within_budget(self, tmp_path):
        """Spawn 10 workers each spending $1 against $20 budget — all should succeed."""
        n_workers = 10
        cost_per_call = 1.0

        args = [(str(tmp_path), cost_per_call, i) for i in range(n_workers)]

        with multiprocessing.Pool(processes=min(n_workers, 8)) as pool:
            results = pool.map(_worker_check_and_record, args)

        assert all(r[0] == "ok" for r in results), f"Some workers failed: {results}"

        with patch("shared.llm_client.settings") as mock_settings:
            mock_settings.darklab_home = tmp_path
            bf = _budget_file()
            total = json.loads(bf.read_text()).get("total_usd", 0.0)

        expected = n_workers * cost_per_call
        assert abs(total - expected) < 1e-6


class TestFileIntegrity:
    """Test that the spend file remains valid JSON under concurrent access."""

    def test_file_is_valid_json_after_concurrent_writes(self, tmp_path):
        """Ensure the file isn't corrupted by overlapping writes."""
        n_workers = 30
        args = [(str(tmp_path), 0.001, i) for i in range(n_workers)]

        with multiprocessing.Pool(processes=min(n_workers, 8)) as pool:
            pool.map(_worker_record_spend, args)

        with patch("shared.llm_client.settings") as mock_settings:
            mock_settings.darklab_home = tmp_path
            bf = _budget_file()

        # File must be valid JSON
        data = json.loads(bf.read_text())
        assert "total_usd" in data
        assert "calls" in data
        assert isinstance(data["calls"], list)
        assert len(data["calls"]) == n_workers
