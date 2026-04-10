"""Plan-file orchestrator for hybrid swarm execution.

Implements the Think-Act-Observe (TAO) loop for Phase 24.  In this
initial version the Think step is deterministic (structured plan-file
parsing), Act delegates to CampaignEngine, and Observe checks campaign
results.  LLM-driven Think is a future enhancement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oas_core.plan_file import PlanFile
from oas_core.model_router import ModelRouter, RoutingContext

try:
    from oas_core.schemas.campaign import CampaignSchema
    _SCHEMAS_AVAILABLE = True
except ImportError:
    _SCHEMAS_AVAILABLE = False

from shared.models import Task, TaskResult

try:
    import structlog
except ImportError:  # pragma: no cover - exercised in minimal test envs
    class _StructlogCompatLogger:
        def __init__(self, name: str):
            self._logger = logging.getLogger(name)

        def _log(self, level: int, event: str, **kwargs: Any) -> None:
            if kwargs:
                self._logger.log(level, "%s %s", event, kwargs)
            else:
                self._logger.log(level, event)

        def info(self, event: str, **kwargs: Any) -> None:
            self._log(logging.INFO, event, **kwargs)

        def warning(self, event: str, **kwargs: Any) -> None:
            self._log(logging.WARNING, event, **kwargs)

        def error(self, event: str, **kwargs: Any) -> None:
            self._log(logging.ERROR, event, **kwargs)

        def debug(self, event: str, **kwargs: Any) -> None:
            self._log(logging.DEBUG, event, **kwargs)

    class _StructlogCompat:
        @staticmethod
        def get_logger(name: str) -> _StructlogCompatLogger:
            return _StructlogCompatLogger(name)

    structlog = _StructlogCompat()  # type: ignore[assignment]

__all__ = ["OrchestratorAgent", "OrchestratorPreparedCampaign", "is_plan_file_task", "handle"]

logger = structlog.get_logger("darklab.orchestrator")


_LOCAL_FIRST_COMMANDS = {
    "research",
    "literature",
    "doe",
    "simulate",
    "analyze",
    "synthetic",
    "report-data",
    "autoresearch",
    "deepresearch",
    "swarmresearch",
    "dft",
}
_RESEARCH_COMMANDS = {
    "research",
    "literature",
    "perplexity",
    "doe",
    "deerflow",
    "deepresearch",
    "swarmresearch",
}


def is_plan_file_task(task: Task) -> bool:
    """Whether a task should be handled via the plan-file orchestrator."""
    payload = task.payload
    source = str(payload.get("source", "")).strip().lower()
    return bool(
        payload.get("plan_path")
        or payload.get("plan_markdown")
        or source == "plan_file"
    )


@dataclass(frozen=True)
class OrchestratorPreparedCampaign:
    plan_file: PlanFile
    engine_plan: list[dict[str, Any]]
    metadata: dict[str, Any] = None  # type: ignore[assignment]


class OrchestratorAgent:
    """Converts plan files into executable campaign runs."""

    def __init__(
        self,
        *,
        campaign_engine: Any | None,
        governance: Any | None = None,
        plan_dir: str | Path | None = None,
        model_router: ModelRouter | None = None,
        routing_context_factory: Any | None = None,
    ) -> None:
        self._campaign_engine = campaign_engine
        self._governance = governance
        self._plan_dir = Path(plan_dir).expanduser().resolve() if plan_dir else None
        self._model_router = model_router or ModelRouter()
        self._routing_context_factory = routing_context_factory

    @property
    def watcher(self) -> PlanWatcher | None:
        if self._plan_dir is None:
            return None
        return PlanWatcher(self._plan_dir)

    def load_plan_file(self, task: Task) -> PlanFile:
        """Load a plan file from task payload."""
        payload = task.payload
        if payload.get("plan_markdown"):
            return PlanFile.from_markdown(
                str(payload["plan_markdown"]),
                source_path=payload.get("plan_path"),
            )

        plan_path = payload.get("plan_path")
        if not plan_path:
            raise ValueError("Plan-file task requires 'plan_path' or 'plan_markdown'")
        return PlanFile.from_path(str(plan_path))

    def plan_to_campaign(
        self,
        plan_file: PlanFile,
        *,
        request_id: str,
    ) -> OrchestratorPreparedCampaign:
        """Convert a parsed plan file into a prepared campaign via dict-based steps.

        Uses ``to_campaign_steps()`` which returns plain dicts compatible with
        CampaignEngine — no dependency on ``oas_core.schemas``.
        """
        engine_plan = plan_file.to_campaign_steps()

        # Enrich each step with orchestrator metadata
        for step in engine_plan:
            cmd = step.get("command", "")
            step["metadata"] = {
                "model_tier": self._infer_step_tier(plan_file, cmd),
                "plan_mode": plan_file.mode,
                "allow_kairos_followup": plan_file.allow_kairos_followup,
            }
            if cmd in _RESEARCH_COMMANDS:
                step["metadata"]["research_mode"] = plan_file.mode
                step["metadata"]["research_backends"] = list(plan_file.research_backends)
            if cmd == "synthesize":
                step["metadata"]["synthesis_backend"] = plan_file.synthesis

        metadata = {
            "intent": plan_file.intent,
            "mode": plan_file.mode,
            "budget_usd": plan_file.budget_usd,
            "tier": plan_file.tier,
            "tags": list(plan_file.tags),
            "plan_id": plan_file.id,
            "plan_title": plan_file.title,
            "plan_author": plan_file.author,
            "request_id": request_id,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }
        if plan_file.source_path:
            metadata["source_path"] = plan_file.source_path

        return OrchestratorPreparedCampaign(
            plan_file=plan_file,
            engine_plan=engine_plan,
            metadata=metadata,
        )

    async def handle_task(self, task: Task) -> TaskResult:
        """Execute or stage a plan-file task (TAO loop).

        **Think**: Parse plan file and convert to campaign steps.
        **Act**: Execute via CampaignEngine (or stage for approval).
        **Observe**: Inspect campaign result and build TaskResult.
        """
        # --- DRVP: orchestrator.started ---
        await _emit_drvp("ORCHESTRATOR_STARTED", task.task_id, {
            "plan_source": task.payload.get("source", "unknown"),
        })

        try:
            prepared = self.plan_to_campaign(
                self.load_plan_file(task),
                request_id=task.task_id,
            )
        except Exception as exc:
            logger.error("orchestrator_plan_parse_failed", error=str(exc), task_id=task.task_id)
            await _emit_drvp("ORCHESTRATOR_FAILED", task.task_id, {
                "error": str(exc), "phase": "think",
            })
            return TaskResult(
                task_id=task.task_id,
                agent_name="OrchestratorAgent",
                status="error",
                result={"error": str(exc), "phase": "think"},
            )

        plan_file = prepared.plan_file
        engine_plan = prepared.engine_plan
        metadata = prepared.metadata or {}

        task.payload["text"] = task.payload.get("text") or plan_file.title
        task.payload["_campaign_id"] = plan_file.id

        # --- DRVP: step_dispatched for each step ---
        for step_dict in engine_plan:
            await _emit_drvp("ORCHESTRATOR_STEP_DISPATCHED", task.task_id, {
                "step": step_dict["step"],
                "command": step_dict["command"],
                "plan_id": plan_file.id,
            })

        issue_id = task.payload.get("_issue_id")
        issue_key = task.payload.get("_issue_key")
        gov = self._governance

        if not issue_id and gov:
            issue = await gov.open_issue(
                request_id=task.task_id,
                title=plan_file.title[:120],
                agent_name="OrchestratorAgent",
                device="leader",
                description=f"Plan file campaign: {plan_file.id}",
            )
            if issue:
                issue_id = issue.get("id")
                issue_key = issue.get("key")
                task.payload["_issue_id"] = issue_id
                task.payload["_issue_key"] = issue_key

        needs_approval = plan_file.approvals_required
        approval = None
        approved = False
        if gov and needs_approval:
            approval = await gov.request_campaign_approval(
                request_id=task.task_id,
                plan=engine_plan,
                issue_id=issue_id,
            )
            approved = bool(approval.get("approved"))

        if self._campaign_engine and (approved or not needs_approval):
            try:
                campaign_result = await self._campaign_engine.execute(
                    request_id=task.task_id,
                    plan=engine_plan,
                    agent_name="OrchestratorAgent",
                    device="leader",
                )
            except Exception as exc:
                logger.error("orchestrator_campaign_failed", error=str(exc), task_id=task.task_id)
                await _emit_drvp("ORCHESTRATOR_FAILED", task.task_id, {
                    "error": str(exc), "phase": "act",
                    "plan_id": plan_file.id,
                })
                return TaskResult(
                    task_id=task.task_id,
                    agent_name="OrchestratorAgent",
                    status="error",
                    result={"error": str(exc), "phase": "act", "plan_id": plan_file.id},
                )

            logger.info(
                "orchestrator_completed",
                plan_id=plan_file.id,
                task_id=task.task_id,
                status=campaign_result.status,
            )
            await _emit_drvp("ORCHESTRATOR_COMPLETED", task.task_id, {
                "plan_id": plan_file.id,
                "campaign_status": campaign_result.status,
                "total_steps": len(engine_plan),
            })
            return TaskResult(
                task_id=task.task_id,
                agent_name="OrchestratorAgent",
                status="ok",
                result={
                    "action": "campaign_executed",
                    "campaign": campaign_result.to_dict(),
                    "campaign_metadata": metadata,
                    "plan_file": self._plan_file_summary(plan_file),
                    "issue_id": issue_id,
                    "issue_key": issue_key,
                },
            )

        await _emit_drvp("ORCHESTRATOR_COMPLETED", task.task_id, {
            "plan_id": plan_file.id,
            "action": "staged",
            "requires_approval": needs_approval and not approved,
        })
        return TaskResult(
            task_id=task.task_id,
            agent_name="OrchestratorAgent",
            status="ok",
            result={
                "action": "campaign",
                "campaign_metadata": metadata,
                "plan": engine_plan,
                "plan_file": self._plan_file_summary(plan_file),
                "requires_approval": needs_approval and not approved,
                "approval": approval,
                "issue_id": issue_id,
                "issue_key": issue_key,
                "execution_ready": self._campaign_engine is not None,
            },
        )

    def _infer_step_tier(self, plan_file: PlanFile, command: str) -> str:
        """Determine the model tier for a campaign step.

        v2: if a ``routing_context_factory`` is configured, delegates to
        ``ModelRouter.route_v2()`` for the full degradation chain.
        Legacy: static heuristic based on plan_file.tier field.
        """
        if self._routing_context_factory is not None:
            try:
                ctx = self._routing_context_factory(plan_file, command)
                decision = self._model_router.route_v2(ctx)
                return decision.tier.value
            except Exception:
                pass

        # Legacy fallback
        if plan_file.tier == "local_only" or plan_file.confidential:
            return "planning_local"
        if plan_file.tier == "boost":
            return "boost"
        if command in _LOCAL_FIRST_COMMANDS:
            return "planning_local"
        return "execution"

    @staticmethod
    def build_routing_context(
        plan_file: PlanFile,
        command: str,
        *,
        dev_reachable: bool = False,
        dev_priority_floor: int = 5,
        dev_reasoning_ready: bool = False,
        dev_worker_pool_free: int = 0,
        dev_code_ready: bool = False,
        sonnet_spent_usd: float = 0.0,
    ) -> RoutingContext:
        """Build a ``RoutingContext`` from a plan file for ``route_v2``.

        This is the canonical translation from plan-file semantics to
        routing-context semantics. Called by the ``routing_context_factory``
        in production wiring.
        """
        return RoutingContext(
            mission_id=plan_file.id,
            mission_confidential=plan_file.confidential,
            sonnet_cap_usd=plan_file.sonnet_cap_usd,
            sonnet_spent_usd=sonnet_spent_usd,
            opus_allowed=plan_file.opus_allowed,
            task_type=command.upper().replace("-", "_"),
            dev_reachable=dev_reachable,
            dev_priority_floor=dev_priority_floor,
            dev_reasoning_ready=dev_reasoning_ready,
            dev_worker_pool_free=dev_worker_pool_free,
            dev_code_ready=dev_code_ready,
        )

    @staticmethod
    def _plan_file_summary(plan_file: PlanFile) -> dict[str, Any]:
        return {
            "id": plan_file.id,
            "title": plan_file.title,
            "source_path": plan_file.source_path,
            "source_sha256": plan_file.source_sha256,
            "mode": plan_file.mode,
            "tier": plan_file.tier,
        }


# ------------------------------------------------------------------
# DRVP helper (best-effort, never raises)
# ------------------------------------------------------------------

async def _emit_drvp(event_name: str, request_id: str, payload: dict[str, Any]) -> None:
    """Emit a DRVP event. Swallows all errors."""
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        event_type = getattr(DRVPEventType, event_name, None)
        if event_type is None:
            return
        await emit(DRVPEvent(
            event_type=event_type,
            request_id=request_id,
            agent_name="OrchestratorAgent",
            device="leader",
            payload=payload,
        ))
    except Exception:
        pass


# ------------------------------------------------------------------
# Dispatch integration — handle() for _get_local_handler
# ------------------------------------------------------------------

async def handle(task: Task) -> TaskResult:
    """Dispatch entry point for ``/orchestrate`` command.

    Accepts a task with either:
    - ``plan_path``: path to a plan .md file
    - ``plan_markdown``: inline plan markdown text
    - ``args``: interpreted as a plan file path

    Lazily builds an ``OrchestratorAgent`` with the campaign engine and
    governance middleware from dispatch singletons.
    """
    text = task.payload.get("text", "").strip()
    args = task.payload.get("args", "").strip()

    # If args look like a file path, set plan_path
    if args and not task.payload.get("plan_path") and not task.payload.get("plan_markdown"):
        from pathlib import Path as _Path
        candidate = _Path(args).expanduser()
        if candidate.suffix == ".md" or candidate.exists():
            task.payload["plan_path"] = str(candidate)
            task.payload["source"] = "plan_file"

    if not task.payload.get("plan_path") and not task.payload.get("plan_markdown"):
        return TaskResult(
            task_id=task.task_id,
            agent_name="OrchestratorAgent",
            status="error",
            result={
                "error": "Missing plan_path or plan_markdown in payload. "
                         "Usage: /orchestrate <path-to-plan.md>",
            },
        )

    task.payload.setdefault("source", "plan_file")

    try:
        from leader.dispatch import _get_campaign_engine, _get_governance
        orchestrator = OrchestratorAgent(
            campaign_engine=_get_campaign_engine(),
            governance=_get_governance(),
        )
        return await orchestrator.handle_task(task)
    except Exception as exc:
        logger.error("orchestrator_handle_failed", error=str(exc), task_id=task.task_id)
        await _emit_drvp("ORCHESTRATOR_FAILED", task.task_id, {"error": str(exc)})
        return TaskResult(
            task_id=task.task_id,
            agent_name="OrchestratorAgent",
            status="error",
            result={"error": str(exc)},
        )
