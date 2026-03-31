"""Data retention and cleanup for RL training data.

Manages rollout files, checkpoints, and evaluations with configurable
retention policies to prevent unbounded storage growth.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

__all__ = ["DataManager"]

logger = logging.getLogger("oas.rl.data_manager")


class DataManager:
    """Manages RL data retention and cleanup."""

    def __init__(
        self,
        rl_dir: Path,
        *,
        max_checkpoints: int = 10,
        rollout_retention_days: int = 30,
        max_rollout_files: int = 500,
    ):
        self.rl_dir = rl_dir
        self.max_checkpoints = max_checkpoints
        self.rollout_retention_days = rollout_retention_days
        self.max_rollout_files = max_rollout_files

    @property
    def rollouts_dir(self) -> Path:
        return self.rl_dir / "rollouts"

    @property
    def checkpoints_dir(self) -> Path:
        return self.rl_dir / "checkpoints"

    @property
    def evaluations_dir(self) -> Path:
        return self.rl_dir / "evaluations"

    def cleanup_old_rollouts(self) -> int:
        """Remove rollout files older than the retention period.

        Returns the number of files removed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.rollout_retention_days)
        removed = 0

        for source_dir in ("live", "synthetic"):
            dir_path = self.rollouts_dir / source_dir
            if not dir_path.exists():
                continue

            files = sorted(dir_path.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
            for path in files:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    path.unlink()
                    removed += 1

        if removed:
            logger.info("cleaned_old_rollouts", removed=removed)
        return removed

    def cleanup_excess_rollouts(self) -> int:
        """Remove oldest rollout files when total exceeds max_rollout_files.

        Returns the number of files removed.
        """
        all_files: list[Path] = []
        for source_dir in ("live", "synthetic"):
            dir_path = self.rollouts_dir / source_dir
            if dir_path.exists():
                all_files.extend(dir_path.glob("*.jsonl"))

        if len(all_files) <= self.max_rollout_files:
            return 0

        # Sort by modification time, remove oldest
        all_files.sort(key=lambda p: p.stat().st_mtime)
        to_remove = len(all_files) - self.max_rollout_files
        removed = 0

        for path in all_files[:to_remove]:
            path.unlink()
            removed += 1

        if removed:
            logger.info("cleaned_excess_rollouts", removed=removed, remaining=self.max_rollout_files)
        return removed

    def cleanup_old_checkpoints(self, agent_type: str) -> int:
        """Keep only the most recent N checkpoints for an agent type.

        Never removes the baseline. Returns the number removed.
        """
        if not self.checkpoints_dir.exists():
            return 0

        ckpt_dirs = sorted(
            [d for d in self.checkpoints_dir.iterdir()
             if d.is_dir() and d.name.startswith(f"{agent_type}-ckpt-")],
            key=lambda d: d.stat().st_mtime,
        )

        if len(ckpt_dirs) <= self.max_checkpoints:
            return 0

        to_remove = len(ckpt_dirs) - self.max_checkpoints
        removed = 0

        for ckpt_dir in ckpt_dirs[:to_remove]:
            shutil.rmtree(ckpt_dir)
            removed += 1

        if removed:
            logger.info(
                "cleaned_old_checkpoints",
                agent_type=agent_type,
                removed=removed,
                remaining=self.max_checkpoints,
            )
        return removed

    def get_storage_stats(self) -> dict[str, Any]:
        """Return storage usage statistics."""
        stats: dict[str, Any] = {}

        for name, path in [
            ("rollouts_live", self.rollouts_dir / "live"),
            ("rollouts_synthetic", self.rollouts_dir / "synthetic"),
            ("checkpoints", self.checkpoints_dir),
            ("evaluations", self.evaluations_dir),
        ]:
            if path.exists():
                files = list(path.rglob("*"))
                file_count = sum(1 for f in files if f.is_file())
                total_bytes = sum(f.stat().st_size for f in files if f.is_file())
                stats[name] = {
                    "files": file_count,
                    "size_mb": round(total_bytes / (1024 * 1024), 2),
                }
            else:
                stats[name] = {"files": 0, "size_mb": 0.0}

        return stats

    def run_cleanup(self, agent_types: list[str] | None = None) -> dict[str, int]:
        """Run all cleanup operations.

        Returns a summary of items removed by category.
        """
        results: dict[str, int] = {}
        results["old_rollouts"] = self.cleanup_old_rollouts()
        results["excess_rollouts"] = self.cleanup_excess_rollouts()

        if agent_types:
            ckpt_total = 0
            for agent_type in agent_types:
                ckpt_total += self.cleanup_old_checkpoints(agent_type)
            results["old_checkpoints"] = ckpt_total

        return results
