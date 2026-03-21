"""Deepagents integration — wraps the deepagents framework for DarkLab.

Provides a subprocess-based harness for running deepagents tasks with
filesystem access, sub-agent spawning, and structured output.

The wrapper can be registered as a LangGraph swarm node for complex
multi-file tasks that require autonomous agent behavior.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["DeepAgentRunner", "DeepAgentResult", "DEEP_AGENT_AVAILABLE"]

logger = logging.getLogger("oas.deep_agent")

# Lazy check for deepagents CLI availability
_deep_agent_checked = False
DEEP_AGENT_AVAILABLE = False


def _check_deep_agent_available() -> bool:
    """Lazily check if deepagents_cli is importable."""
    global _deep_agent_checked, DEEP_AGENT_AVAILABLE
    if _deep_agent_checked:
        return DEEP_AGENT_AVAILABLE
    _deep_agent_checked = True
    DEEP_AGENT_AVAILABLE = importlib.util.find_spec("deepagents_cli") is not None
    return DEEP_AGENT_AVAILABLE


@dataclass
class DeepAgentResult:
    """Result from a deepagents execution."""

    status: str  # "ok" | "error" | "timeout"
    output: str
    artifacts: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "output": self.output,
            "artifacts": self.artifacts,
            "token_usage": self.token_usage,
            "duration_seconds": self.duration_seconds,
        }


class DeepAgentRunner:
    """Runs deepagents tasks as isolated subprocesses.

    Usage::

        runner = DeepAgentRunner(work_dir="/tmp/deep-work")
        result = await runner.run(
            task="Analyze the CSV data and produce summary statistics",
            files={"data.csv": csv_content},
            max_steps=50,
            timeout=300,
        )
    """

    def __init__(
        self,
        work_dir: str | Path | None = None,
        model: str = "claude-sonnet-4-6-20260301",
        api_key: str = "",
    ):
        self.work_dir = Path(work_dir) if work_dir else None
        self.model = model
        self.api_key = api_key

    async def run(
        self,
        task: str,
        *,
        files: dict[str, str] | None = None,
        max_steps: int = 50,
        timeout: float = 300.0,
        allowed_tools: list[str] | None = None,
    ) -> DeepAgentResult:
        """Execute a deepagents task in a subprocess.

        Args:
            task: Natural language task description.
            files: Dict of filename → content to seed the workspace.
            max_steps: Maximum agent steps before termination.
            timeout: Subprocess timeout in seconds.
            allowed_tools: Restrict to specific tool names (None = all).
        """
        if not _check_deep_agent_available():
            return DeepAgentResult(
                status="error",
                output="deepagents CLI not installed",
            )

        # Create isolated workspace
        work_dir = self.work_dir or Path(tempfile.mkdtemp(prefix="deepagent-"))
        work_dir.mkdir(parents=True, exist_ok=True)

        # Seed files
        if files:
            for name, content in files.items():
                (work_dir / name).write_text(content)

        # Build the task JSON for subprocess
        task_payload = {
            "task": task,
            "model": self.model,
            "max_steps": max_steps,
            "work_dir": str(work_dir),
        }
        if allowed_tools:
            task_payload["allowed_tools"] = allowed_tools

        # Write task file
        task_file = work_dir / ".deepagent-task.json"
        task_file.write_text(json.dumps(task_payload))

        # Run as subprocess
        import time

        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "deepagents_cli", "--task-file", str(task_file),
                "--output-json",
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **dict(os.environ),
                    "ANTHROPIC_API_KEY": self.api_key,
                    "DEEPAGENT_MAX_STEPS": str(max_steps),
                },
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            elapsed = time.monotonic() - start

            if proc.returncode != 0:
                return DeepAgentResult(
                    status="error",
                    output=stderr.decode(errors="replace")[:2000],
                    duration_seconds=elapsed,
                )

            # Parse JSON output
            try:
                result_data = json.loads(stdout.decode())
                return DeepAgentResult(
                    status="ok",
                    output=result_data.get("output", stdout.decode()[:2000]),
                    artifacts=result_data.get("artifacts", []),
                    token_usage=result_data.get("token_usage", {}),
                    duration_seconds=elapsed,
                )
            except json.JSONDecodeError:
                return DeepAgentResult(
                    status="ok",
                    output=stdout.decode()[:2000],
                    duration_seconds=elapsed,
                )

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            return DeepAgentResult(
                status="timeout",
                output=f"Deepagent timed out after {timeout}s",
                duration_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return DeepAgentResult(
                status="error",
                output=str(exc),
                duration_seconds=elapsed,
            )


async def run_deep_agent_task(
    task: str,
    *,
    api_key: str = "",
    model: str = "claude-sonnet-4-6-20260301",
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Convenience function for running a single deepagent task.

    Returns a dict suitable for inclusion in a TaskResult.
    """
    runner = DeepAgentRunner(model=model, api_key=api_key)
    result = await runner.run(task, timeout=timeout)
    return result.to_dict()
