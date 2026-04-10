"""Campaign execution engine.

Executes multi-step research campaigns planned by the Leader's
``plan_campaign()`` function. Manages step dependencies, parallel
execution of independent steps, and Paperclip issue tracking for
each step.

A campaign is a DAG of steps where each step has:
- A command (maps to a routing table entry)
- Arguments
- Dependencies on prior steps (by step number)

Orchestration patterns inspired by open-multi-agent:
- **SharedMemory**: namespaced context visible to all steps
- **Retry with backoff**: per-step exponential retry (capped at 30s)
- **Cascade failure**: transitive failure propagation with reason chain
- **Capability matching**: auto-assign unrouted steps by keyword overlap
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

from oas_core.capability_matcher import (
    CapabilitySource,
    MatchResult,
    score_candidates,
)
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
from oas_core.shared_memory import SharedMemory

try:
    from oas_core.eval.scorer import EvalScorer as _EvalScorer
    _EVAL_AVAILABLE = True
except ImportError:
    _EvalScorer = None  # type: ignore[assignment,misc]
    _EVAL_AVAILABLE = False

_EVAL_PASS_THRESHOLD = 3.5
_EVAL_MAX_RETRIES = 3

__all__ = ["CampaignEngine", "CampaignStep", "StepStatus", "CampaignResult"]

logger = logging.getLogger("oas.campaign")

_MAX_RETRY_DELAY = 30.0  # Cap for exponential backoff


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

    # Retry configuration (open-multi-agent pattern)
    max_retries: int = 0
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    retry_count: int = 0

    # Cascade failure tracking
    failure_reason_chain: list[str] = field(default_factory=list)

    # Capability matching
    assigned_via: str | None = None  # None = hardcoded, "capability_match" = auto

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CampaignStep:
        return cls(
            step=d["step"],
            command=d["command"],
            args=d.get("args", ""),
            depends_on=d.get("depends_on", []),
            max_retries=d.get("max_retries", 0),
            retry_delay=d.get("retry_delay", 1.0),
            retry_backoff=d.get("retry_backoff", 2.0),
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
    shared_memory: dict[str, dict[str, Any]] = field(default_factory=dict)

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
                    "retry_count": s.retry_count,
                    "max_retries": s.max_retries,
                    "assigned_via": s.assigned_via,
                    "failure_reason_chain": s.failure_reason_chain,
                }
                for s in self.steps
            ],
            "shared_memory_keys": {
                ns: list(entries.keys())
                for ns, entries in self.shared_memory.items()
            },
        }


# Type for the step executor callback
StepExecutor = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]]


class CampaignEngine:
    """Executes campaign plans with dependency resolution and parallelism.

    Improvements over basic DAG execution (inspired by open-multi-agent):
    - SharedMemory: all steps see all prior results via prompt injection
    - Per-step retry: exponential backoff with configurable max_retries
    - Cascade failure: transitive propagation with reason chains
    - Capability matching: auto-assign unrouted steps by keyword overlap

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
        capability_index: list[CapabilitySource] | None = None,
        eval_golden_dir: Any | None = None,
    ):
        self._execute_step = step_executor
        self._governance = governance
        self._max_parallel = max_parallel
        self._step_timeout = step_timeout
        self._capability_index = capability_index
        self._memory = SharedMemory()
        # Generator-Evaluator: optional scorer backed by golden fixtures
        self._eval_scorer = _EvalScorer() if (_EVAL_AVAILABLE and eval_golden_dir) else None
        self._eval_golden_dir = eval_golden_dir

    # ------------------------------------------------------------------
    # DAG validation
    # ------------------------------------------------------------------

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

    @staticmethod
    def _build_adjacency(steps: list[CampaignStep]) -> dict[int, list[int]]:
        """Build forward adjacency map (step → list of dependents)."""
        step_ids = {s.step for s in steps}
        adj: dict[int, list[int]] = {s.step: [] for s in steps}
        for s in steps:
            for dep in s.depends_on:
                if dep in step_ids:
                    adj[dep].append(s.step)
        return adj

    # ------------------------------------------------------------------
    # Cascade failure
    # ------------------------------------------------------------------

    def _cascade_failure(
        self,
        failed_step: CampaignStep,
        step_map: dict[int, CampaignStep],
        adj: dict[int, list[int]],
        failed_steps: set[int],
        request_id: str,
        agent_name: str,
        device: str,
    ) -> list[CampaignStep]:
        """Transitively fail all dependents of a failed step.

        Returns the list of newly cascade-failed steps for DRVP emission.
        """
        cascade_root = (
            f"Step {failed_step.step} '{failed_step.command}': "
            f"{failed_step.error or 'unknown error'}"
        )

        # BFS through adjacency graph
        queue = list(adj.get(failed_step.step, []))
        visited: set[int] = set()
        cascaded: list[CampaignStep] = []

        while queue:
            sid = queue.pop(0)
            if sid in visited or sid in failed_steps:
                continue
            visited.add(sid)

            dep_step = step_map.get(sid)
            if dep_step is None or dep_step.status in (
                StepStatus.COMPLETED,
                StepStatus.RUNNING,
            ):
                continue

            # Build reason chain
            dep_step.status = StepStatus.FAILED
            dep_step.failure_reason_chain = (
                failed_step.failure_reason_chain
                + [f"Cascaded from {cascade_root}"]
            )
            dep_step.error = dep_step.failure_reason_chain[-1]
            dep_step.completed_at = datetime.now(timezone.utc)
            failed_steps.add(sid)
            cascaded.append(dep_step)

            # Continue BFS to transitive dependents
            queue.extend(adj.get(sid, []))

        return cascaded

    # ------------------------------------------------------------------
    # Capability matching
    # ------------------------------------------------------------------

    def _try_capability_match(self, step: CampaignStep) -> MatchResult | None:
        """Try to match an unknown command to a capability source."""
        if not self._capability_index:
            return None

        results = score_candidates(
            f"{step.command} {step.args}",
            self._capability_index,
            top_k=1,
            min_score=0.1,
        )
        return results[0] if results else None

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        request_id: str,
        plan: list[dict[str, Any]],
        agent_name: str,
        device: str,
    ) -> CampaignResult:
        """Execute a campaign plan respecting step dependencies.

        Steps with no unfinished dependencies run in parallel (up to
        ``max_parallel``). Failed steps cause dependent steps to be
        cascade-failed with reason chains.
        """
        steps = [CampaignStep.from_dict(d) for d in plan]
        step_map = {s.step: s for s in steps}

        # Cycle detection — verify the dependency graph is a DAG
        self._check_for_cycles(steps)

        # Build adjacency for cascade failure
        adj = self._build_adjacency(steps)

        # Fresh shared memory per campaign run
        self._memory.clear()

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

            # Cascade-fail steps whose dependencies failed (transitive)
            for s in steps:
                if (
                    s.status == StepStatus.PENDING
                    and any(d in failed_steps for d in s.depends_on)
                    and s.step not in failed_steps
                ):
                    # Find the first failed dependency for the reason chain
                    for d in s.depends_on:
                        if d in failed_steps:
                            failed_dep = step_map[d]
                            cascaded = self._cascade_failure(
                                failed_dep, step_map, adj, failed_steps,
                                request_id, agent_name, device,
                            )
                            # Also fail this step directly if not caught by cascade
                            if s.step not in failed_steps:
                                s.status = StepStatus.FAILED
                                root_error = failed_dep.error or "unknown"
                                s.failure_reason_chain = [
                                    f"Cascaded from Step {d} "
                                    f"'{failed_dep.command}': {root_error}"
                                ]
                                s.error = s.failure_reason_chain[-1]
                                s.completed_at = datetime.now(timezone.utc)
                                failed_steps.add(s.step)

                            # Emit DRVP events for cascade failures
                            for cs in cascaded:
                                await emit(DRVPEvent(
                                    event_type=DRVPEventType.CAMPAIGN_STEP_CASCADE_FAILED,
                                    request_id=request_id,
                                    agent_name=agent_name,
                                    device=device,
                                    payload={
                                        "step_number": cs.step,
                                        "command": cs.command,
                                        "reason_chain": cs.failure_reason_chain,
                                        "source_step": d,
                                    },
                                ))
                            break

            if not ready:
                break

            # Execute ready steps in parallel (limited concurrency)
            sem = asyncio.Semaphore(self._max_parallel)

            async def _run(step: CampaignStep) -> None:
                async with sem:
                    await self._run_step(
                        step, request_id, agent_name, device,
                        step_map, len(steps), adj, failed_steps,
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
            shared_memory=self._memory.snapshot(),
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
                "shared_memory_entries": len(self._memory),
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
                "shared_memory_entries": len(self._memory),
            },
        )

        return result

    # ------------------------------------------------------------------
    # Single step execution with retry
    # ------------------------------------------------------------------

    async def _run_step(
        self,
        step: CampaignStep,
        request_id: str,
        agent_name: str,
        device: str,
        step_map: dict[int, CampaignStep],
        total_steps: int,
        adj: dict[int, list[int]],
        failed_steps: set[int],
    ) -> None:
        """Execute a single campaign step with retry and shared memory."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc)

        # Capability matching for unknown commands
        if self._capability_index:
            match = self._try_capability_match(step)
            if match and match.command != step.command:
                original = step.command
                step.command = match.command
                step.assigned_via = "capability_match"
                logger.info(
                    "step_capability_matched",
                    extra={
                        "step": step.step,
                        "original": original,
                        "matched": match.command,
                        "score": match.score,
                    },
                )
                await emit(DRVPEvent(
                    event_type=DRVPEventType.CAMPAIGN_STEP_ROUTED,
                    request_id=request_id,
                    agent_name=agent_name,
                    device=device,
                    payload={
                        "step_number": step.step,
                        "original_command": original,
                        "matched_command": match.command,
                        "score": match.score,
                    },
                ))

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

        # Create governance issue
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

        # Gather dependency results
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
            "shared_memory": self._memory.snapshot(),
            "shared_memory_summary": self._memory.summary(),
        }

        # Retry loop (open-multi-agent pattern)
        last_error: str | None = None
        for attempt in range(step.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._execute_step(step.command, step.args, payload),
                    timeout=self._step_timeout,
                )

                # Generator-Evaluator: score output against golden fixture (best-effort)
                eval_passed = True
                if self._eval_scorer:
                    output_text = (
                        result.get("output") or result.get("result") or ""
                    )
                    if output_text and attempt < _EVAL_MAX_RETRIES:
                        try:
                            scoring = self._eval_scorer.score(
                                task_id=f"{step.command}_{step.step}",
                                task_type=step.command.upper(),
                                output={"output": output_text},
                                ground_truth={},
                                cost_usd=result.get("cost_usd", 0.0),
                            )
                            eval_passed = scoring.passed
                            if not eval_passed:
                                logger.info(
                                    "step_eval_failed_retrying",
                                    extra={
                                        "step": step.step,
                                        "score": scoring.weighted_average,
                                        "attempt": attempt,
                                    },
                                )
                                # Inject feedback into next attempt payload
                                payload["eval_feedback"] = scoring.feedback
                                raise RuntimeError(
                                    f"Eval score {scoring.weighted_average:.2f} < "
                                    f"{_EVAL_PASS_THRESHOLD} — retrying"
                                )
                        except RuntimeError:
                            raise
                        except Exception as eval_exc:
                            logger.debug("eval_score_error", exc_info=eval_exc)

                # Success — write to shared memory and complete
                step.status = StepStatus.COMPLETED
                step.result = result
                step.completed_at = datetime.now(timezone.utc)
                step.retry_count = attempt

                # Write result to shared memory for subsequent steps
                namespace = f"step_{step.step}_{step.command}"
                await self._memory.write(namespace, "result", result)
                await self._memory.write(namespace, "status", "completed")

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
                        "retry_count": attempt,
                    },
                ))
                return  # Success — exit retry loop

            except asyncio.TimeoutError:
                last_error = f"Step timed out after {self._step_timeout}s"
            except Exception as e:
                last_error = str(e)

            # Check if we should retry
            if attempt < step.max_retries:
                delay = min(
                    step.retry_delay * (step.retry_backoff ** attempt),
                    _MAX_RETRY_DELAY,
                )
                logger.info(
                    "step_retrying",
                    extra={
                        "step": step.step,
                        "attempt": attempt + 1,
                        "max_retries": step.max_retries,
                        "delay": delay,
                        "error": last_error,
                    },
                )
                await emit(DRVPEvent(
                    event_type=DRVPEventType.CAMPAIGN_STEP_RETRYING,
                    request_id=request_id,
                    agent_name=agent_name,
                    device=device,
                    payload={
                        "step_number": step.step,
                        "attempt": attempt + 1,
                        "max_retries": step.max_retries,
                        "delay_seconds": delay,
                        "error": last_error,
                    },
                ))
                await asyncio.sleep(delay)

        # All retries exhausted — mark as failed
        step.status = StepStatus.FAILED
        step.error = last_error
        step.completed_at = datetime.now(timezone.utc)
        step.retry_count = step.max_retries

        logger.warning(
            "step_failed",
            extra={
                "step": step.step,
                "command": step.command,
                "error": last_error,
                "retries_exhausted": step.max_retries,
            },
        )
