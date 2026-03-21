"""Campaign execution engine.

Executes multi-step research campaigns planned by the Leader's
``plan_campaign()`` function. Manages step dependencies, parallel
execution of independent steps, and Paperclip issue tracking for
each step.

A campaign is a DAG of steps where each step has:
- A command (maps to a routing table entry)
- Arguments
- Dependencies on prior steps (by step number)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

__all__ = ["CampaignEngine", "CampaignStep", "StepStatus", "CampaignResult"]

logger = logging.getLogger("oas.campaign")


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CampaignStep:
    """A single step in a campaign plan."""

    step: int
    command: str
    args: str
    depends_on: list[int] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    issue_id: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CampaignStep:
        return cls(
            step=d["step"],
            command=d["command"],
            args=d.get("args", ""),
            depends_on=d.get("depends_on", []),
        )

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class CampaignResult:
    """Result of a completed campaign execution."""

    request_id: str
    steps: list[CampaignStep]
    status: str  # "completed" | "partial" | "failed"
    total_duration_seconds: float | None = None

    @property
    def completed_steps(self) -> list[CampaignStep]:
        return [s for s in self.steps if s.status == StepStatus.COMPLETED]

    @property
    def failed_steps(self) -> list[CampaignStep]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "total_steps": len(self.steps),
            "completed": len(self.completed_steps),
            "failed": len(self.failed_steps),
            "total_duration_seconds": self.total_duration_seconds,
            "steps": [
                {
                    "step": s.step,
                    "command": s.command,
                    "args": s.args,
                    "status": s.status.value,
                    "error": s.error,
                    "duration_seconds": s.duration_seconds,
                    "issue_id": s.issue_id,
                }
                for s in self.steps
            ],
        }


# Type for the step executor callback
StepExecutor = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]]


class CampaignEngine:
    """Executes campaign plans with dependency resolution and parallelism.

    Usage::

        engine = CampaignEngine(
            step_executor=my_dispatch_fn,
            governance=governance_middleware,  # optional
        )

        result = await engine.execute(
            request_id="req_123",
            plan=[
                {"step": 1, "command": "research", "args": "quantum dots", "depends_on": []},
                {"step": 2, "command": "simulate", "args": "QD model", "depends_on": [1]},
                {"step": 3, "command": "analyze", "args": "sim results", "depends_on": [2]},
            ],
            agent_name="leader",
            device="leader",
        )
    """

    def __init__(
        self,
        step_executor: StepExecutor,
        *,
        governance: Any | None = None,
        max_parallel: int = 3,
        step_timeout: float = 300.0,
    ):
        self._execute_step = step_executor
        self._governance = governance
        self._max_parallel = max_parallel
        self._step_timeout = step_timeout

    @staticmethod
    def _check_for_cycles(steps: list[CampaignStep]) -> None:
        """Verify the dependency graph has no cycles (Kahn's algorithm)."""
        step_ids = {s.step for s in steps}
        in_degree: dict[int, int] = {s.step: 0 for s in steps}
        adj: dict[int, list[int]] = {s.step: [] for s in steps}

        for s in steps:
            for dep in s.depends_on:
                if dep in step_ids:
                    adj[dep].append(s.step)
                    in_degree[s.step] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(steps):
            raise ValueError(
                f"Campaign plan contains a dependency cycle "
                f"({visited}/{len(steps)} steps reachable)"
            )

    async def execute(
        self,
        request_id: str,
        plan: list[dict[str, Any]],
        agent_name: str,
        device: str,
    ) -> CampaignResult:
        """Execute a campaign plan respecting step dependencies.

        Steps with no unfinished dependencies run in parallel (up to
        ``max_parallel``). Failed steps cause dependent steps to be skipped.
        """
        steps = [CampaignStep.from_dict(d) for d in plan]
        step_map = {s.step: s for s in steps}

        # Cycle detection — verify the dependency graph is a DAG
        self._check_for_cycles(steps)

        campaign_start = datetime.now(timezone.utc)

        await emit(DRVPEvent(
            event_type=DRVPEventType.CAMPAIGN_STEP_STARTED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"total_steps": len(steps), "step_number": 0},
        ))

        completed_steps: set[int] = set()
        failed_steps: set[int] = set()

        while True:
            # Find ready steps: all dependencies completed, not yet started
            ready = [
                s for s in steps
                if s.status == StepStatus.PENDING
                and all(d in completed_steps for d in s.depends_on)
                and not any(d in failed_steps for d in s.depends_on)
            ]

            # Skip steps whose dependencies failed
            for s in steps:
                if s.status == StepStatus.PENDING and any(d in failed_steps for d in s.depends_on):
                    s.status = StepStatus.SKIPPED
                    s.error = f"Dependency step(s) failed: {[d for d in s.depends_on if d in failed_steps]}"
                    logger.info("step_skipped", extra={"step": s.step, "reason": s.error})

            if not ready:
                # No more steps to run
                break

            # Execute ready steps in parallel (limited concurrency)
            sem = asyncio.Semaphore(self._max_parallel)

            async def _run(step: CampaignStep) -> None:
                async with sem:
                    await self._run_step(
                        step, request_id, agent_name, device, step_map, len(steps)
                    )
                    if step.status == StepStatus.COMPLETED:
                        completed_steps.add(step.step)
                    elif step.status == StepStatus.FAILED:
                        failed_steps.add(step.step)

            await asyncio.gather(*[_run(s) for s in ready])

        campaign_end = datetime.now(timezone.utc)
        duration = (campaign_end - campaign_start).total_seconds()

        # Determine overall status
        if all(s.status == StepStatus.COMPLETED for s in steps):
            status = "completed"
        elif any(s.status == StepStatus.COMPLETED for s in steps):
            status = "partial"
        else:
            status = "failed"

        result = CampaignResult(
            request_id=request_id,
            steps=steps,
            status=status,
            total_duration_seconds=duration,
        )

        await emit(DRVPEvent(
            event_type=DRVPEventType.CAMPAIGN_STEP_COMPLETED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "total_steps": len(steps),
                "step_number": len(steps),
                "status": status,
                "completed": len(result.completed_steps),
                "failed": len(result.failed_steps),
                "duration_seconds": duration,
            },
        ))

        logger.info(
            "campaign_completed",
            extra={
                "request_id": request_id,
                "status": status,
                "steps": len(steps),
                "completed": len(completed_steps),
                "failed": len(failed_steps),
                "duration": round(duration, 1),
            },
        )

        return result

    async def _run_step(
        self,
        step: CampaignStep,
        request_id: str,
        agent_name: str,
        device: str,
        step_map: dict[int, CampaignStep],
        total_steps: int,
    ) -> None:
        """Execute a single campaign step."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc)

        await emit(DRVPEvent(
            event_type=DRVPEventType.CAMPAIGN_STEP_STARTED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "step_number": step.step,
                "total_steps": total_steps,
                "command": step.command,
            },
        ))

        # Create governance issue for this step
        if self._governance:
            try:
                issue = await self._governance.open_issue(
                    request_id=request_id,
                    title=f"Step {step.step}: /{step.command} {step.args[:80]}",
                    agent_name=agent_name,
                    device=device,
                    description=f"Campaign step {step.step}/{total_steps}",
                )
                step.issue_id = issue.get("id") if issue else None
            except Exception as e:
                logger.warning("step_issue_create_failed", extra={"error": str(e)})

        # Gather dependency results for context
        dep_results = {}
        for dep_num in step.depends_on:
            dep_step = step_map.get(dep_num)
            if dep_step and dep_step.result:
                dep_results[f"step_{dep_num}"] = dep_step.result

        payload = {
            "text": f"/{step.command} {step.args}",
            "command": step.command,
            "args": step.args,
            "campaign_request_id": request_id,
            "step_number": step.step,
            "dependency_results": dep_results,
        }

        try:
            result = await asyncio.wait_for(
                self._execute_step(step.command, step.args, payload),
                timeout=self._step_timeout,
            )
            step.status = StepStatus.COMPLETED
            step.result = result
            step.completed_at = datetime.now(timezone.utc)

            await emit(DRVPEvent(
                event_type=DRVPEventType.CAMPAIGN_STEP_COMPLETED,
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={
                    "step_number": step.step,
                    "total_steps": total_steps,
                    "command": step.command,
                    "status": "completed",
                    "duration_seconds": step.duration_seconds,
                },
            ))

        except asyncio.TimeoutError:
            step.status = StepStatus.FAILED
            step.error = f"Step timed out after {self._step_timeout}s"
            step.completed_at = datetime.now(timezone.utc)
            logger.warning("step_timeout", extra={"step": step.step, "command": step.command})

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.now(timezone.utc)
            logger.warning(
                "step_failed",
                extra={"step": step.step, "command": step.command, "error": str(e)},
            )
