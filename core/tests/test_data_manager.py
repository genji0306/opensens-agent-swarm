"""Tests for RL data manager (retention and cleanup)."""
import json
import time
from pathlib import Path

import pytest

from oas_core.rl.data_manager import DataManager


class TestDataManager:
    def _populate_rollouts(self, rl_dir: Path, n_live: int = 5, n_synthetic: int = 3):
        for source, count in [("live", n_live), ("synthetic", n_synthetic)]:
            d = rl_dir / "rollouts" / source
            d.mkdir(parents=True, exist_ok=True)
            for i in range(count):
                (d / f"file-{i:03d}.jsonl").write_text(f'{{"session_id": "{i}"}}\n')

    def _populate_checkpoints(self, rl_dir: Path, agent: str = "research", n: int = 5):
        for i in range(n):
            d = rl_dir / "checkpoints" / f"{agent}-ckpt-{i:03d}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "adapter.bin").write_text("fake")

    def test_cleanup_excess_rollouts(self, tmp_path):
        self._populate_rollouts(tmp_path, n_live=10, n_synthetic=5)
        dm = DataManager(rl_dir=tmp_path, max_rollout_files=8)
        removed = dm.cleanup_excess_rollouts()
        assert removed == 7  # 15 - 8

    def test_no_cleanup_under_limit(self, tmp_path):
        self._populate_rollouts(tmp_path, n_live=3, n_synthetic=2)
        dm = DataManager(rl_dir=tmp_path, max_rollout_files=10)
        removed = dm.cleanup_excess_rollouts()
        assert removed == 0

    def test_cleanup_old_checkpoints(self, tmp_path):
        self._populate_checkpoints(tmp_path, n=8)
        dm = DataManager(rl_dir=tmp_path, max_checkpoints=3)
        removed = dm.cleanup_old_checkpoints("research")
        assert removed == 5

    def test_get_storage_stats(self, tmp_path):
        self._populate_rollouts(tmp_path, n_live=3, n_synthetic=2)
        dm = DataManager(rl_dir=tmp_path)
        stats = dm.get_storage_stats()
        assert stats["rollouts_live"]["files"] == 3
        assert stats["rollouts_synthetic"]["files"] == 2

    def test_run_cleanup(self, tmp_path):
        self._populate_rollouts(tmp_path, n_live=10, n_synthetic=5)
        self._populate_checkpoints(tmp_path, n=8)
        dm = DataManager(rl_dir=tmp_path, max_rollout_files=5, max_checkpoints=3)
        results = dm.run_cleanup(agent_types=["research"])
        assert results["excess_rollouts"] > 0
        assert results["old_checkpoints"] > 0
