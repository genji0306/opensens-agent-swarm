"""DarkLab AutoResearch Agent: autonomous ML experimentation on Apple Silicon.

Wraps Karpathy's autoresearch-macos to run autonomous ML experiment loops.
The loop: read state → propose experiment → modify train.py → commit → train → evaluate → keep/revert.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import structlog

from shared.models import Task, TaskResult
from shared.config import settings
from shared.audit import log_event
from shared.node_bridge import run_agent

logger = structlog.get_logger("darklab.autoresearch")

AUTORESEARCH_DIR = Path.home() / ".darklab" / "tools" / "autoresearch"
WORKSPACES_DIR = Path.home() / ".darklab" / "autoresearch-workspaces"
LOCK_FILE = Path.home() / ".darklab" / "autoresearch.lock"


class AutoResearchRunner:
    def __init__(self, workspace_name: str):
        self.workspace = WORKSPACES_DIR / workspace_name
        self.workspace.mkdir(parents=True, exist_ok=True)

    def setup(self, program_md: str, train_py: str) -> None:
        """Initialize experiment workspace with git tracking."""
        (self.workspace / "program.md").write_text(program_md)
        (self.workspace / "train.py").write_text(train_py)

        # Initialize git repo for experiment tracking
        subprocess.run(["git", "init"], cwd=self.workspace, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=self.workspace, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial experiment setup"],
            cwd=self.workspace, check=True, capture_output=True,
        )

    def run(self, max_iterations: int = 20, time_limit_min: int = 5) -> dict:
        """Execute the AutoResearch loop."""
        # Single-instance lock to prevent MPS memory contention
        if LOCK_FILE.exists():
            return {
                "status": "blocked",
                "error": "Another AutoResearch instance is running. Only one can run at a time on MPS.",
            }

        try:
            LOCK_FILE.write_text(str(time.time()))
            log_event("autoresearch_start", workspace=str(self.workspace),
                      max_iterations=max_iterations)

            total_timeout = max_iterations * (time_limit_min + 2) * 60

            result = subprocess.run(
                [
                    "python3", str(AUTORESEARCH_DIR / "train.py"),
                ],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=total_timeout,
            )

            # Parse results.tsv if it exists
            results_tsv = self.workspace / "results.tsv"
            experiments = self._parse_results(results_tsv)

            # Get git log for experiment history
            git_log = subprocess.run(
                ["git", "log", "--oneline", "-20"],
                cwd=self.workspace, capture_output=True, text=True,
            ).stdout.strip()

            log_event("autoresearch_complete",
                      workspace=str(self.workspace),
                      n_experiments=len(experiments))

            return {
                "status": "completed",
                "experiments": experiments,
                "git_log": git_log,
                "stdout_tail": result.stdout[-2000:] if result.stdout else "",
                "best_metric": self._get_best_metric(experiments),
            }

        except subprocess.TimeoutExpired:
            return {"status": "timeout", "error": f"Exceeded {total_timeout}s timeout"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
        finally:
            LOCK_FILE.unlink(missing_ok=True)

    def _parse_results(self, results_path: Path) -> list[dict]:
        """Parse results.tsv into structured records."""
        if not results_path.exists():
            return []

        experiments = []
        lines = results_path.read_text().strip().split("\n")
        if not lines:
            return []

        # First line is header
        headers = lines[0].split("\t")
        for line in lines[1:]:
            fields = line.split("\t")
            record = {}
            for i, header in enumerate(headers):
                record[header] = fields[i] if i < len(fields) else ""
            experiments.append(record)

        return experiments

    def _get_best_metric(self, experiments: list[dict]) -> float | None:
        """Extract the best val_bpb from experiments."""
        best = None
        for exp in experiments:
            if exp.get("status") == "keep":
                try:
                    val = float(exp.get("val_bpb", exp.get("metric", "inf")))
                    if best is None or val < best:
                        best = val
                except (ValueError, TypeError):
                    pass
        return best


async def handle(task: Task) -> TaskResult:
    program_md = task.payload.get("program_md", "")
    train_py = task.payload.get("train_py", "")
    max_iterations = task.payload.get("max_iterations", 20)
    time_limit_min = task.payload.get("time_limit_min", 5)
    workspace_name = task.payload.get("workspace", f"exp_{task.task_id}")

    if not program_md:
        return TaskResult(
            task_id=task.task_id,
            agent_name="AutoResearchAgent",
            status="error",
            result={"error": "No program.md provided. This is the research protocol that guides the agent."},
        )

    runner = AutoResearchRunner(workspace_name)

    if train_py:
        runner.setup(program_md, train_py)

    result_data = runner.run(
        max_iterations=max_iterations,
        time_limit_min=time_limit_min,
    )

    artifacts = []
    results_path = runner.workspace / "results.tsv"
    if results_path.exists():
        artifacts.append(str(results_path))

    return TaskResult(
        task_id=task.task_id,
        agent_name="AutoResearchAgent",
        status=result_data.get("status", "error"),
        result=result_data,
        artifacts=artifacts,
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="AutoResearchAgent")
