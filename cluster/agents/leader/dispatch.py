"""DarkLab Leader Dispatch: routes commands to the correct agent and device.

The Leader runs inside the OpenClaw gateway (Node.js). This module provides
programmatic routing logic that can be invoked by the gateway's LLM agent
via system.run, or used for multi-step campaign orchestration.

Routing table (from SKILL.md):
  /research     -> Academic   -> darklab-research
  /literature   -> Academic   -> darklab-literature
  /doe          -> Academic   -> darklab-doe
  /paper        -> Academic   -> darklab-paper
  /perplexity   -> Academic   -> darklab-perplexity
  /simulate     -> Experiment -> darklab-simulation
  /analyze      -> Experiment -> darklab-analysis
  /synthetic    -> Experiment -> darklab-synthetic
  /report-data  -> Experiment -> darklab-report-data
  /autoresearch -> Experiment -> darklab-autoresearch
  /deerflow     -> Leader     -> darklab-deerflow (local)
  /prorl-status -> Leader     -> darklab-rl-train (local)
  /prorl-run    -> Leader     -> darklab-rl-train (local)
  /synthesize   -> Leader     -> darklab-synthesis (local)
  /report       -> Leader     -> darklab-media-gen (local)
  /notebooklm   -> Leader     -> darklab-notebooklm (local)
  /status       -> All        -> health check
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

        def debug(self, event: str, **kwargs: Any) -> None:
            self._log(logging.DEBUG, event, **kwargs)

        def info(self, event: str, **kwargs: Any) -> None:
            self._log(logging.INFO, event, **kwargs)

        def warning(self, event: str, **kwargs: Any) -> None:
            self._log(logging.WARNING, event, **kwargs)

        def error(self, event: str, **kwargs: Any) -> None:
            self._log(logging.ERROR, event, **kwargs)

    class _StructlogCompat:
        @staticmethod
        def get_logger(name: str) -> _StructlogCompatLogger:
            return _StructlogCompatLogger(name)

    structlog = _StructlogCompat()  # type: ignore[assignment]

__all__ = [
    "handle",
    "parse_command",
    "resolve_route",
    "build_node_invoke",
    "ROUTING_TABLE",
    "Route",
    "pre_dispatch_hook",
    "plan_campaign",
]

from shared.models import Task, TaskType, TaskResult
from shared.config import settings
from shared.llm_client import call_anthropic, call_routed, get_model_router
from shared.audit import log_event
from shared.node_bridge import run_agent

logger = structlog.get_logger("darklab.dispatch")

# --- Swarm singleton (lazy init) ---

_UNINITIALIZED = object()  # sentinel to distinguish "not yet init" from "init returned None"

_swarm_app: Any | None = None
_swarm_lock: asyncio.Lock | None = None
_swarm_init_failed: bool = False
_governance: Any = _UNINITIALIZED
_memory_mw: Any = _UNINITIALIZED
_audit_mw: Any = _UNINITIALIZED
_campaign_engine: Any = _UNINITIALIZED
_budget_mw: Any = _UNINITIALIZED
_team_state_store: Any = _UNINITIALIZED
_team_worktree_manager: Any = _UNINITIALIZED
_team_journal_bridge: Any = _UNINITIALIZED


def _get_lock() -> asyncio.Lock:
    """Get or create the swarm init lock (must be called inside a running loop)."""
    global _swarm_lock
    if _swarm_lock is None:
        _swarm_lock = asyncio.Lock()
    return _swarm_lock


def _get_governance():
    """Get or lazily init the GovernanceMiddleware singleton."""
    global _governance
    if _governance is not _UNINITIALIZED:
        return _governance

    try:
        from oas_core.middleware.governance import GovernanceMiddleware
        from oas_core.adapters.paperclip import PaperclipClient

        if settings.paperclip_url and settings.paperclip_api_key:
            client = PaperclipClient(
                base_url=settings.paperclip_url,
                api_key=settings.paperclip_api_key,
                company_id=settings.paperclip_company_id,
            )
            _governance = GovernanceMiddleware(
                paperclip=client,
                agent_id=settings.paperclip_agent_id,
            )
        else:
            _governance = GovernanceMiddleware(paperclip=None, agent_id="")
    except Exception as exc:
        logger.warning("governance_init_error", error=str(exc))
        _governance = None
    return _governance


def _get_memory_mw():
    """Get or lazily init the MemoryMiddleware singleton."""
    global _memory_mw
    if _memory_mw is not _UNINITIALIZED:
        return _memory_mw

    try:
        from oas_core.middleware.memory import MemoryMiddleware
        from oas_core.memory import MemoryClient

        if settings.openviking_url:
            client = MemoryClient(
                base_url=settings.openviking_url,
                api_key=settings.openviking_api_key or None,
            )
            _memory_mw = MemoryMiddleware(client)
        else:
            _memory_mw = MemoryMiddleware(None)
    except Exception as exc:
        logger.warning("memory_mw_init_error", error=str(exc))
        _memory_mw = None
    return _memory_mw


def _get_audit_mw():
    """Get or lazily init the AuditMiddleware singleton."""
    global _audit_mw
    if _audit_mw is not _UNINITIALIZED:
        return _audit_mw

    try:
        from oas_core.middleware.audit import AuditMiddleware
        log_dir = settings.logs_dir
        key_path = settings.signing_key_path if settings.signing_key_path.exists() else None
        _audit_mw = AuditMiddleware(
            log_dir=log_dir,
            signing_key_path=key_path,
        )
    except Exception as exc:
        logger.warning("audit_mw_init_error", error=str(exc))
        _audit_mw = None
    return _audit_mw


def _get_campaign_engine():
    """Get or lazily init the CampaignEngine singleton."""
    global _campaign_engine
    if _campaign_engine is not _UNINITIALIZED:
        return _campaign_engine

    try:
        from oas_core.campaign import CampaignEngine

        async def step_executor(command, args, payload):
            """Execute a single campaign step by re-routing through dispatch."""
            route = resolve_route(command)
            if not route:
                return {"error": f"Unknown command: {command}"}
            node_url = _node_url(route.node)
            if node_url:
                import httpx
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(node_url, json={
                        "text": f"/{command} {args}",
                        "task_type": route.task_type.value,
                        "payload": payload,
                    })
                    resp.raise_for_status()
                    return resp.json()
            return {"action": "dispatch", "route": {"node": route.node, "skill": route.skill}}

        _campaign_engine = CampaignEngine(
            step_executor=step_executor,
            governance=_get_governance(),
        )
    except Exception as exc:
        logger.warning("campaign_engine_init_error", error=str(exc))
        _campaign_engine = None
    return _campaign_engine


def _get_budget_mw():
    """Get or lazily init the BudgetMiddleware singleton."""
    global _budget_mw
    if _budget_mw is not _UNINITIALIZED:
        return _budget_mw

    try:
        from oas_core.middleware.budget import BudgetMiddleware
        from oas_core.adapters.paperclip import PaperclipClient

        if settings.paperclip_url and settings.paperclip_api_key:
            client = PaperclipClient(
                base_url=settings.paperclip_url,
                api_key=settings.paperclip_api_key,
                company_id=settings.paperclip_company_id,
            )
            _budget_mw = BudgetMiddleware(
                paperclip=client,
                agent_id=settings.paperclip_agent_id,
            )
        else:
            _budget_mw = None
    except Exception as exc:
        logger.warning("budget_mw_init_error", error=str(exc))
        _budget_mw = None
    return _budget_mw


def _get_team_state_store():
    """Get or lazily init the TeamStateStore singleton.

    Best-effort: if the team runtime package is unavailable, dispatch continues
    normally with no runtime state tracking.
    """
    global _team_state_store
    if _team_state_store is not _UNINITIALIZED:
        return _team_state_store

    try:
        from oas_core.team_runtime import TeamStateStore

        state_dir = settings.darklab_home / "state" / "team"
        _team_state_store = TeamStateStore(state_dir)
    except Exception as exc:
        logger.debug("team_state_store_init_skip", error=str(exc))
        _team_state_store = None
    return _team_state_store


def _detect_repo_root() -> Path:
    """Best-effort repo root for worktree provisioning."""
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / ".git").exists():
        return candidate
    return Path.cwd()


def _get_team_worktree_manager():
    """Get or lazily init TeamWorktreeManager.

    Best-effort: if unavailable, guarded mutating tasks are blocked with
    an explicit error and non-mutating tasks continue normally.
    """
    global _team_worktree_manager
    if _team_worktree_manager is not _UNINITIALIZED:
        return _team_worktree_manager

    try:
        from oas_core.team_runtime import TeamWorktreeManager

        _team_worktree_manager = TeamWorktreeManager(repo_root=_detect_repo_root())
    except Exception as exc:
        logger.debug("team_worktree_manager_init_skip", error=str(exc))
        _team_worktree_manager = None
    return _team_worktree_manager


def _get_team_journal_bridge():
    """Get or lazily init TeamJournalBridge for campaign replay integration."""
    global _team_journal_bridge
    if _team_journal_bridge is not _UNINITIALIZED:
        return _team_journal_bridge

    store = _get_team_state_store()
    if store is None:
        _team_journal_bridge = None
        return None

    try:
        from oas_core.team_runtime import TeamJournalBridge

        journal_dir = settings.darklab_home / "journals" / "team_runtime"
        _team_journal_bridge = TeamJournalBridge(store, journal_dir)
    except Exception as exc:
        logger.debug("team_journal_bridge_init_skip", error=str(exc))
        _team_journal_bridge = None
    return _team_journal_bridge


def _team_campaign_id_from_task(task: Task) -> str:
    raw = (
        task.payload.get("campaign_id")
        or task.payload.get("_campaign_id")
        or task.payload.get("run_id")
        or task.task_id
    )
    return str(raw)


async def _sync_team_journal(task: Task, team_name: str) -> None:
    """Best-effort sync from team event log into campaign journal."""
    bridge = _get_team_journal_bridge()
    if bridge is None:
        return

    try:
        result = bridge.sync(
            team_name=team_name,
            campaign_id=_team_campaign_id_from_task(task),
        )
        task.payload["_team_journal_sync"] = {
            "synced_events": result.synced_events,
            "last_event_id": result.last_event_id,
        }
    except Exception as exc:
        logger.debug("team_journal_sync_skip", error=str(exc), team_name=team_name)


def _team_runtime_status_summary() -> dict[str, Any]:
    """Summarize current team runtime state for /status visibility."""
    store = _get_team_state_store()
    if store is None:
        return {"enabled": False, "reason": "team_state_store_unavailable"}

    try:
        teams = store.list_teams()
        total_tasks = 0
        total_events = 0
        aggregate_task_counts: dict[str, int] = {}
        team_summaries: list[dict[str, Any]] = []

        for team_name in teams:
            tasks = store.list_tasks(team_name)
            task_counts: dict[str, int] = {}
            for task in tasks:
                key = task.status.value
                task_counts[key] = task_counts.get(key, 0) + 1
                aggregate_task_counts[key] = aggregate_task_counts.get(key, 0) + 1

            event_count = store.count_events(team_name)
            total_tasks += len(tasks)
            total_events += event_count
            team_summaries.append(
                {
                    "team_name": team_name,
                    "task_count": len(tasks),
                    "event_count": event_count,
                    "task_counts": task_counts,
                }
            )

        return {
            "enabled": True,
            "team_count": len(teams),
            "total_tasks": total_tasks,
            "total_events": total_events,
            "task_counts": aggregate_task_counts,
            "teams": team_summaries[:10],
        }
    except Exception as exc:
        logger.debug("team_runtime_status_summary_skip", error=str(exc))
        return {"enabled": False, "reason": "summary_error", "error": str(exc)}


def _task_requires_worktree(task: Task) -> bool:
    """Whether this task must allocate a worktree before execution."""
    for key in ("requires_worktree", "mutating"):
        value = task.payload.get(key)
        if isinstance(value, bool):
            if value:
                return True
        elif isinstance(value, str):
            if value.strip().lower() in {"1", "true", "yes", "on"}:
                return True
    return False


async def _ensure_worktree_allocation(task: Task, command: str, route: Route) -> dict | None:
    """Allocate worktree for mutating tasks or return a blocking error payload."""
    if not _task_requires_worktree(task):
        return None

    if route.node != "leader":
        error = "worktree-guarded task must run on leader node"
        await _team_runtime_mark_failed(task, command, route, error)
        return {
            "blocked": True,
            "reason": "worktree_requires_leader_route",
            "detail": error,
        }

    manager = _get_team_worktree_manager()
    if manager is None:
        error = "worktree manager unavailable"
        await _team_runtime_mark_failed(task, command, route, error)
        return {
            "blocked": True,
            "reason": "worktree_manager_unavailable",
            "detail": error,
        }

    try:
        team_name = _team_name_from_task(task)
        worker_name = _team_worker_name(command, route)
        info = manager.create(team_name, worker_name)
        task.payload["_worktree"] = {
            "path": str(info.path),
            "branch": info.branch,
            "team_name": info.team_name,
            "worker_name": info.worker_name,
        }
        return None
    except Exception as exc:
        error = f"worktree allocation failed: {exc}"
        await _team_runtime_mark_failed(task, command, route, error)
        return {
            "blocked": True,
            "reason": "worktree_allocation_failed",
            "detail": str(exc),
        }


def _team_name_from_task(task: Task) -> str:
    raw = (
        task.payload.get("team_name")
        or task.payload.get("team")
        or task.payload.get("swarm_team")
        or "default"
    )
    return str(raw)


def _team_worker_name(command: str, route: Route) -> str:
    if route.node == "leader":
        return f"leader.{command}"
    return route.skill


def _safe_preview(value: Any, *, max_chars: int = 400) -> str:
    text = str(value)
    return text[:max_chars]


def _build_task_metadata(task: Task, command: str, route: Route, args: str) -> dict[str, Any]:
    return {
        "command": command,
        "node": route.node,
        "skill": route.skill,
        "task_type": route.task_type.value,
        "raw_text": task.payload.get("raw_text", task.payload.get("text", "")),
        "args_preview": _safe_preview(args, max_chars=240),
    }


def _ensure_team_runtime_task(
    task: Task,
    command: str,
    route: Route,
    args: str,
):
    """Create/refresh the team manifest + task record and return state tuple."""
    store = _get_team_state_store()
    if store is None:
        return None, None

    try:
        from oas_core.schemas.team import (
            TeamManifestSchema,
            TeamTaskSchema,
            TeamTaskStatus,
            TeamWorkerSchema,
            WorkerBackend,
        )

        team_name = _team_name_from_task(task)
        worker_name = _team_worker_name(command, route)

        manifest = store.load_manifest(team_name)
        if manifest is None:
            manifest = TeamManifestSchema(
                team_name=team_name,
                metadata={"created_by": "leader.dispatch"},
            )

        if not any(w.name == worker_name for w in manifest.workers):
            backend = WorkerBackend.CLAUDE_LOCAL if route.node == "leader" else WorkerBackend.REMOTE
            manifest.workers.append(
                TeamWorkerSchema(
                    name=worker_name,
                    backend=backend,
                    metadata={"route_node": route.node, "route_skill": route.skill},
                )
            )

        manifest.touch()
        store.save_manifest(manifest)

        team_task = store.get_task(team_name, task.task_id)
        if team_task is None:
            team_task = TeamTaskSchema(
                task_id=task.task_id,
                subject=f"/{command}",
                description=args,
                status=TeamTaskStatus.PENDING,
                owner=worker_name,
                metadata=_build_task_metadata(task, command, route, args),
            )
        else:
            team_task.owner = team_task.owner or worker_name
            team_task.metadata.update(_build_task_metadata(task, command, route, args))
            if args and not team_task.description:
                team_task.description = args

        store.upsert_task(team_name, team_task)
        return team_name, team_task
    except Exception as exc:
        logger.debug("team_runtime_task_setup_skip", error=str(exc), command=command)
        return None, None


async def _team_runtime_record_pending(task: Task, command: str, route: Route, args: str) -> None:
    store = _get_team_state_store()
    if store is None:
        return

    try:
        from oas_core.schemas.team import TeamEventSchema, TeamEventType

        team_name, team_task = _ensure_team_runtime_task(task, command, route, args)
        if team_name is None or team_task is None:
            return

        store.append_event(
            team_name,
            TeamEventSchema(
                team_name=team_name,
                event_type=TeamEventType.TASK_CREATED,
                task_id=team_task.task_id,
                worker_name=_team_worker_name(command, route),
                payload={
                    "command": command,
                    "skill": route.skill,
                    "task_type": route.task_type.value,
                },
            ),
        )
        await _sync_team_journal(task, team_name)
    except Exception as exc:
        logger.debug("team_runtime_pending_skip", error=str(exc), command=command)


async def _team_runtime_mark_started(task: Task, command: str, route: Route, args: str) -> None:
    store = _get_team_state_store()
    if store is None:
        return

    try:
        from oas_core.schemas.team import TeamEventSchema, TeamEventType, TeamTaskStatus
        from oas_core.team_runtime.events import emit_team_task_started

        team_name, team_task = _ensure_team_runtime_task(task, command, route, args)
        if team_name is None or team_task is None:
            return

        worker_name = _team_worker_name(command, route)
        if team_task.status in (TeamTaskStatus.PENDING, TeamTaskStatus.BLOCKED):
            team_task.transition_to(
                TeamTaskStatus.IN_PROGRESS,
                owner=worker_name,
            )
            store.upsert_task(team_name, team_task)

        store.append_event(
            team_name,
            TeamEventSchema(
                team_name=team_name,
                event_type=TeamEventType.TASK_STARTED,
                task_id=team_task.task_id,
                worker_name=worker_name,
                payload={
                    "command": command,
                    "skill": route.skill,
                    "task_type": route.task_type.value,
                },
            ),
        )
        await _sync_team_journal(task, team_name)

        await emit_team_task_started(
            request_id=task.task_id,
            team_name=team_name,
            task_id=team_task.task_id,
            worker_name=worker_name,
            device=route.node,
            payload={
                "command": command,
                "skill": route.skill,
                "task_type": route.task_type.value,
            },
        )
    except Exception as exc:
        logger.debug("team_runtime_started_skip", error=str(exc), command=command)


async def _team_runtime_mark_completed(
    task: Task,
    command: str,
    route: Route,
    result: TaskResult,
) -> None:
    store = _get_team_state_store()
    if store is None:
        return

    try:
        from oas_core.schemas.team import TeamEventSchema, TeamEventType, TeamTaskStatus
        from oas_core.team_runtime.events import emit_team_task_completed

        team_name = _team_name_from_task(task)
        worker_name = _team_worker_name(command, route)
        team_task = store.get_task(team_name, task.task_id)
        if team_task is None:
            _, team_task = _ensure_team_runtime_task(task, command, route, task.payload.get("args", ""))
            if team_task is None:
                return

        if team_task.status == TeamTaskStatus.PENDING:
            team_task.transition_to(TeamTaskStatus.IN_PROGRESS, owner=worker_name)
        if team_task.status in (TeamTaskStatus.IN_PROGRESS, TeamTaskStatus.BLOCKED):
            team_task.transition_to(TeamTaskStatus.COMPLETED, owner=worker_name)
        store.upsert_task(team_name, team_task)

        store.append_event(
            team_name,
            TeamEventSchema(
                team_name=team_name,
                event_type=TeamEventType.TASK_COMPLETED,
                task_id=team_task.task_id,
                worker_name=worker_name,
                payload={
                    "command": command,
                    "skill": route.skill,
                    "task_type": route.task_type.value,
                    "status": result.status,
                    "result_preview": _safe_preview(result.result),
                },
            ),
        )
        await _sync_team_journal(task, team_name)

        await emit_team_task_completed(
            request_id=task.task_id,
            team_name=team_name,
            task_id=team_task.task_id,
            worker_name=worker_name,
            device=route.node,
            payload={
                "command": command,
                "skill": route.skill,
                "status": result.status,
                "result_preview": _safe_preview(result.result),
            },
        )
    except Exception as exc:
        logger.debug("team_runtime_completed_skip", error=str(exc), command=command)


async def _team_runtime_mark_failed(
    task: Task,
    command: str,
    route: Route,
    error: str,
) -> None:
    store = _get_team_state_store()
    if store is None:
        return

    try:
        from oas_core.schemas.team import TeamEventSchema, TeamEventType, TeamTaskStatus
        from oas_core.team_runtime.events import emit_team_task_failed

        team_name = _team_name_from_task(task)
        worker_name = _team_worker_name(command, route)
        team_task = store.get_task(team_name, task.task_id)
        if team_task is None:
            _, team_task = _ensure_team_runtime_task(task, command, route, task.payload.get("args", ""))
            if team_task is None:
                return

        if team_task.status == TeamTaskStatus.PENDING:
            team_task.transition_to(TeamTaskStatus.FAILED, owner=worker_name, error=error)
        elif team_task.status in (TeamTaskStatus.IN_PROGRESS, TeamTaskStatus.BLOCKED):
            team_task.transition_to(TeamTaskStatus.FAILED, owner=worker_name, error=error)
        else:
            team_task.error = error
        store.upsert_task(team_name, team_task)

        store.append_event(
            team_name,
            TeamEventSchema(
                team_name=team_name,
                event_type=TeamEventType.TASK_FAILED,
                task_id=team_task.task_id,
                worker_name=worker_name,
                payload={
                    "command": command,
                    "skill": route.skill,
                    "task_type": route.task_type.value,
                    "error": error,
                },
            ),
        )
        await _sync_team_journal(task, team_name)

        await emit_team_task_failed(
            request_id=task.task_id,
            team_name=team_name,
            task_id=team_task.task_id,
            worker_name=worker_name,
            device=route.node,
            error=error,
            payload={
                "command": command,
                "skill": route.skill,
                "task_type": route.task_type.value,
            },
        )
    except Exception as exc:
        logger.debug("team_runtime_failed_skip", error=str(exc), command=command)


async def pre_dispatch_hook(task: Task, text: str) -> dict | None:
    """Pre-dispatch hook: budget check + issue creation for PicoClaw requests.

    Returns None on success, or a dict with error info if the request is blocked.
    This runs before any routing decision so that every incoming request
    (whether from PicoClaw/Telegram or direct HTTP) is governed.
    """
    request_id = task.task_id
    source = task.payload.get("source", "unknown")

    # --- Budget pre-check ---
    budget = _get_budget_mw()
    if budget:
        try:
            await budget.check_budget(request_id, "LeaderDispatch", "leader")
        except RuntimeError as exc:
            logger.warning("pre_dispatch_budget_blocked", request_id=request_id, error=str(exc))
            return {"blocked": True, "reason": "budget_exhausted", "detail": str(exc)}

    # --- DRVP: emit request.created ---
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        await emit(DRVPEvent(
            event_type=DRVPEventType.REQUEST_CREATED,
            request_id=request_id,
            agent_name="LeaderDispatch",
            device="leader",
            payload={"title": text[:200], "source": source},
        ))
    except Exception:
        pass  # DRVP is best-effort

    # --- Governance: auto-create issue for PicoClaw requests ---
    gov = _get_governance()
    if gov and source in ("picoclaw", "telegram", "boss"):
        try:
            issue = await gov.open_issue(
                request_id=request_id,
                title=text[:120] or "PicoClaw request",
                agent_name="LeaderDispatch",
                device="leader",
                description=f"Auto-created from {source} request",
            )
            if issue:
                task.payload["_issue_id"] = issue.get("id")
                task.payload["_issue_key"] = issue.get("key")
        except Exception as exc:
            logger.debug("pre_dispatch_issue_skip", error=str(exc))

    return None


async def get_swarm_app() -> Any | None:
    """Lazily initialise and return the LangGraph swarm, or None if unavailable."""
    global _swarm_app, _swarm_init_failed

    if _swarm_app is not None:
        return _swarm_app
    if _swarm_init_failed:
        return None

    lock = _get_lock()
    async with lock:
        # Double-check after acquiring lock
        if _swarm_app is not None:
            return _swarm_app
        if _swarm_init_failed:
            return None

        try:
            from oas_core.swarm import build_swarm, SWARM_AVAILABLE
            if not SWARM_AVAILABLE:
                logger.info("swarm_unavailable", reason="langgraph not installed")
                _swarm_init_failed = True
                return None

            from leader.swarm_registry import get_agent_registry
            registry = get_agent_registry()

            _swarm_app = build_swarm(
                agent_registry=registry,
                anthropic_api_key=settings.anthropic_api_key,
            )
            logger.info("swarm_initialized", n_agents=len(registry))
            return _swarm_app
        except Exception as exc:
            logger.warning("swarm_init_error", error=str(exc))
            _swarm_init_failed = True
            return None


@dataclass(frozen=True)
class Route:
    node: str        # "academic" | "experiment" | "leader"
    skill: str       # OpenClaw skill name
    task_type: TaskType


ROUTING_TABLE: dict[str, Route] = {
    # Academic
    "research":     Route("academic",    "darklab-research",      TaskType.RESEARCH),
    "literature":   Route("academic",    "darklab-literature",    TaskType.LITERATURE),
    "doe":          Route("academic",    "darklab-doe",           TaskType.DOE),
    "paper":        Route("academic",    "darklab-paper",         TaskType.PAPER),
    "perplexity":   Route("academic",    "darklab-perplexity",    TaskType.PERPLEXITY),
    # Experiment
    "simulate":     Route("experiment",  "darklab-simulation",    TaskType.SIMULATE),
    "analyze":      Route("experiment",  "darklab-analysis",      TaskType.ANALYZE),
    "synthetic":    Route("experiment",  "darklab-synthetic",     TaskType.SYNTHETIC),
    "report-data":  Route("experiment",  "darklab-report-data",   TaskType.REPORT_DATA),
    "autoresearch": Route("leader",      "darklab-autoresearch",  TaskType.AUTORESEARCH),
    "deerflow":     Route("leader",      "darklab-deerflow",      TaskType.DEERFLOW),
    # Leader
    "synthesize":   Route("leader",      "darklab-synthesis",     TaskType.SYNTHESIZE),
    "report":       Route("leader",      "darklab-media-gen",     TaskType.MEDIA_GEN),
    "notebooklm":   Route("leader",      "darklab-notebooklm",   TaskType.NOTEBOOKLM),
    # Deep Research + Swarm Research + Parameter Golf
    "deepresearch":  Route("leader",      "darklab-deepresearch",    TaskType.DEEP_RESEARCH),
    "swarmresearch": Route("leader",      "darklab-deepresearch",    TaskType.SWARM_RESEARCH),
    "parametergolf": Route("experiment",  "darklab-parameter-golf",  TaskType.PARAMETER_GOLF),
    # RL + Debate
    "debate":       Route("leader",      "darklab-debate",       TaskType.DEBATE),
    "rl-train":     Route("leader",      "darklab-rl-train",     TaskType.RL_TRAIN),
    "rl-status":    Route("leader",      "darklab-rl-train",     TaskType.RL_TRAIN),
    "rl-rollback":  Route("leader",      "darklab-rl-train",     TaskType.RL_TRAIN),
    "rl-freeze":    Route("leader",      "darklab-rl-train",     TaskType.RL_TRAIN),
    "prorl-status": Route("leader",      "darklab-rl-train",     TaskType.RL_TRAIN),
    "prorl-run":    Route("leader",      "darklab-rl-train",     TaskType.RL_TRAIN),
    # TurboQuant
    "turboq-status":Route("leader",      "darklab-rl-train",     TaskType.TURBOQ_STATUS),
    # Research management
    "results":      Route("leader",      "darklab-deepresearch",  TaskType.RESULTS),
    "schedule":     Route("leader",      "darklab-deepresearch",  TaskType.SCHEDULE),
    # Full swarm pipeline
    "fullswarm":    Route("leader",      "darklab-fullswarm",     TaskType.FULL_SWARM),
    # TurboSwarm (max-performance orchestration)
    "turboswarm":   Route("leader",      "darklab-turboswarm",    TaskType.TURBO_SWARM),
    # Paper review swarm
    "paperreview":  Route("leader",      "darklab-paper-review",  TaskType.PAPER_REVIEW),
    # DFT quantum chemistry
    "dft":          Route("leader",      "darklab-dft",           TaskType.DFT),
    # ANE Research — Apple Neural Engine + MLX + CUDA unified stack
    "ane-research": Route("leader",      "darklab-ane-research",  TaskType.ANE_RESEARCH),
    # Gemma Swarm — local Ollama-hosted Gemma 4 workers
    "gemma-swarm":  Route("leader",      "darklab-gemma-swarm",   TaskType.GEMMA_SWARM),
    # UniPat Swarm — UniScientist polymathic research loop on local Ollama
    "unipat":       Route("leader",      "darklab-unipat-swarm",  TaskType.UNIPAT_SWARM),
    # Orchestrator — plan-file based campaign execution (v2 Phase 24)
    "orchestrate":  Route("leader",      "darklab-orchestrator",  TaskType.ORCHESTRATE),
    # KAIROS — background ambient reasoning daemon (v2 Phase 24)
    "kairos":       Route("leader",      "darklab-kairos",        TaskType.KAIROS),
}

COMMAND_ALIASES: dict[str, str] = {
    "start": "help",
    "commands": "help",
    "ane_research": "ane-research",
    "aneresearch": "ane-research",
    "gemma_swarm": "gemma-swarm",
    "gemmaswarm": "gemma-swarm",
    "gemma": "gemma-swarm",
    "unipat_swarm": "unipat",
    "unipatswarm": "unipat",
    "uniscientist": "unipat",
    "orchestrator": "orchestrate",
    "kairos_daemon": "kairos",
    "report_data": "report-data",
    "rl_train": "rl-train",
    "rl_status": "rl-status",
    "rl_rollback": "rl-rollback",
    "rl_freeze": "rl-freeze",
    "prorl_status": "prorl-status",
    "prorl_run": "prorl-run",
    "turboq_status": "turboq-status",
}

HELP_OUTPUT = """\
DarkLab Research Commands
=========================

Quick Start
  /turboswarm <topic>      — MAX performance 5-angle research
  /fullswarm auto <topic>  — run ALL 18 agents overnight ($0)
  /fullswarm semi <topic>  — auto discovery, pause for review
  /deepresearch <topic>    — iterative deep research
  /swarmresearch <topic>   — 5-angle parallel research

Research
  /research <topic>     — literature search + gap analysis
  /literature <query>   — deep literature review
  /perplexity <query>   — web search (Perplexity AI)
  /deerflow <objective> — deep multi-step research
  /debate <topic>       — multi-agent debate

Experiments
  /doe <spec>           — design experiments
  /simulate <params>    — run simulations
  /analyze <data>       — analyze data
  /synthetic <spec>     — generate synthetic data
  /autoresearch <prog>  — autonomous ML loop
  /parametergolf <spec> — parameter optimization
  /dft <topic>          — DFT quantum chemistry (adsorption, orbitals, DOS)

Output
  /synthesize <topic>   — combine findings
  /report <scope>       — final report
  /paper <topic>        — draft paper
  /report-data <scope>  — charts and figures
  /notebooklm <sources> — audio study guide

Management
  /fullswarm status     — list swarm runs
  /fullswarm resume <id> — resume paused run
  /results [N]          — recent research results
  /schedule <topic>     — schedule recurring research
  /boost on|off|status  — toggle free AI models

Orchestration
  /orchestrate <plan.md> — execute a plan file as a campaign
  /kairos status         — KAIROS daemon health + last heartbeat
  /kairos heartbeat      — run one heartbeat cycle
  /kairos autodream      — run autoDream knowledge consolidation
  /kairos suggest        — run proactive suggestion scan

System
  /status               — cluster health
  /rl-status            — RL training status
  /prorl-status         — ProRL sidecar readiness
  /prorl-run <prompt>   — bounded ProRL experimental run
  /turboq-status        — KV cache pool status

Tip: /fullswarm help for full pipeline guide.
In Telegram, use underscores for hyphens: /rl_status, /prorl_status, /report_data
"""


def _normalize_command(command: str | None) -> str | None:
    """Normalize Telegram-safe aliases to the canonical command names."""
    if command is None:
        return None
    return COMMAND_ALIASES.get(command, command)


def _build_help_result(task: Task) -> TaskResult:
    """Return a fast local help payload with no remote calls."""
    return TaskResult(
        task_id=task.task_id,
        agent_name="LeaderDispatch",
        status="ok",
        result={
            "action": "help",
            "output": HELP_OUTPUT,
            "command_aliases": COMMAND_ALIASES,
        },
    )


def _build_command_payload(payload: dict[str, Any], args: str) -> dict[str, Any]:
    """Normalize slash-command payloads before local or remote execution."""
    command_payload = dict(payload)
    raw_text = command_payload.get("raw_text", command_payload.get("text", ""))
    command_payload["raw_text"] = raw_text
    command_payload["text"] = args
    command_payload["args"] = args
    command_payload["query"] = args
    return command_payload


def _is_plan_file_task(task: Task) -> bool:
    """Whether a task should be routed through the plan-file orchestrator."""
    from leader.orchestrator import is_plan_file_task

    return is_plan_file_task(task)


async def _handle_plan_file_task(task: Task) -> TaskResult:
    """Route a plan-file task through the dedicated orchestrator."""
    from leader.orchestrator import OrchestratorAgent

    orchestrator = OrchestratorAgent(
        campaign_engine=_get_campaign_engine(),
        governance=_get_governance(),
        plan_dir=settings.darklab_plan_dir,
    )
    return await orchestrator.handle_task(task)


def parse_command(text: str) -> tuple[str | None, str]:
    """Extract slash command and arguments from user text.

    Returns (command_name, arguments) or (None, original_text) if no command found.
    """
    match = re.match(r"^/([A-Za-z0-9_-]+)(?:@[A-Za-z0-9_]+)?(?:\s+(.*))?$", text, re.DOTALL)
    if match:
        return match.group(1).lower(), (match.group(2) or "").strip()
    return None, text


def resolve_route(command: str) -> Route | None:
    """Look up the routing destination for a command."""
    return ROUTING_TABLE.get(_normalize_command(command))


def build_node_invoke(route: Route, payload: dict) -> dict:
    """Build an OpenClaw node.invoke message for dispatching to a remote agent.

    This is the JSON structure the gateway sends over WebSocket to invoke
    a skill on a remote node-host.
    """
    return {
        "node": f"darklab-{route.node}",
        "command": route.skill,
        "payload": payload,
    }


PLANNER_PROMPT = """\
You are the DarkLab campaign planner. Given a research request, decompose it
into a sequence of steps using the available commands.

Available commands:
- /research <topic> - Literature search and gap analysis (Academic)
- /literature <query> - Deep literature review (Academic)
- /doe <spec> - Design of Experiments (Academic)
- /paper <topic> - Draft a paper (Academic)
- /perplexity <query> - Web research via Perplexity (Academic)
- /simulate <params> - Run simulations (Experiment)
- /analyze <data> - Analyze data (Experiment)
- /synthetic <spec> - Generate synthetic datasets (Experiment)
- /report-data <scope> - Publication-quality data visualizations (Experiment)
- /autoresearch <program> - Autonomous ML loop (Experiment)
- /deerflow <objective> - Deep multi-step research with sub-agents, reports, and artifacts (Leader)
- /synthesize <topic> - Synthesize findings (Leader)
- /report <scope> - Generate formatted report (Leader)
- /notebooklm <sources> - Generate audio/study guide via NotebookLM (Leader)
- /deepresearch <topic> - Iterative deep research with academic sources and convergence scoring (Leader)
- /swarmresearch <topic> - Multi-angle parallel research with 5 specialist perspectives (Leader)
- /debate <topic> - Generate multi-agent debate simulation via MiroShark (Leader)
- /prorl-status - Check NVIDIA ProRL sidecar readiness and LLM server registration (Leader)
- /prorl-run <prompt> - Run bounded experimental execution through NVIDIA ProRL backend (Leader)
- /fullswarm auto|semi|manual <topic> - Full 18-step swarm pipeline (Leader)
- /dft <topic> - DFT quantum chemistry: adsorption energy, HOMO-LUMO, DOS, charge analysis (Leader)

Output a JSON array of steps:
[
  {"step": 1, "command": "research", "args": "...", "depends_on": []},
  {"step": 2, "command": "simulate", "args": "...", "depends_on": [1]},
  ...
]
"""


async def plan_campaign(request: str) -> list[dict]:
    """Use Claude to decompose a complex research request into ordered steps.

    Uses force_planning=True to ensure Anthropic is used for detailed planning.
    Falls back to Ollama only if credits are completely exhausted.
    """
    response = await call_routed(
        f"Research request: {request}\n\nDecompose into steps.",
        system=PLANNER_PROMPT,
        force_planning=True,
    )
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        logger.warning(
            "plan_campaign_json_parse_failed",
            response_preview=response[:200],
            fallback="single_research_step",
        )
        return [{"step": 1, "command": "research", "args": request, "depends_on": []}]


_LOCAL_HANDLERS: dict[str, Any] = {}


def _get_local_handler(command: str):
    """Get a local handler for leader-routed commands.

    Imports handlers lazily and individually to avoid pulling in heavy
    dependencies (numpy, torch) from experiment agents.
    Returns the async handle() function, or None if not available locally.
    """
    if command in _LOCAL_HANDLERS:
        return _LOCAL_HANDLERS[command]

    handler = None
    try:
        if command == "deerflow":
            from experiment.deerflow_research import handle
            handler = handle
        elif command == "autoresearch":
            from leader.autoresearch_cmd import handle
            handler = handle
        elif command == "synthesize":
            from leader.synthesis import handle
            handler = handle
        elif command == "report":
            from leader.media_gen import handle
            handler = handle
        elif command == "notebooklm":
            from leader.notebooklm import handle
            handler = handle
        elif command == "deepresearch":
            from leader.deep_research_cmd import handle
            handler = handle
        elif command == "swarmresearch":
            from leader.swarm_research_cmd import handle
            handler = handle
        elif command == "debate":
            from leader.rl_commands import handle_debate as handle
            handler = handle
        elif command == "rl-train":
            from leader.rl_commands import handle_rl_train as handle
            handler = handle
        elif command == "rl-status":
            from leader.rl_commands import handle_rl_status as handle
            handler = handle
        elif command == "rl-rollback":
            from leader.rl_commands import handle_rl_rollback as handle
            handler = handle
        elif command == "rl-freeze":
            from leader.rl_commands import handle_rl_freeze as handle
            handler = handle
        elif command == "prorl-status":
            from leader.rl_commands import handle_prorl_status as handle
            handler = handle
        elif command == "prorl-run":
            from leader.rl_commands import handle_prorl_run as handle
            handler = handle
        elif command == "turboq-status":
            from leader.turboq_cmd import handle
            handler = handle
        elif command == "results":
            from leader.research_mgmt_cmd import handle_results as handle
            handler = handle
        elif command == "schedule":
            from leader.research_mgmt_cmd import handle_schedule as handle
            handler = handle
        elif command == "fullswarm":
            from leader.fullswarm_cmd import handle
            handler = handle
        elif command == "turboswarm":
            from leader.turboswarm_cmd import handle
            handler = handle
        elif command == "paperreview":
            from leader.paper_review_cmd import handle
            handler = handle
        elif command == "dft":
            from leader.dft_cmd import handle
            handler = handle
        elif command == "ane-research":
            from leader.ane_research_cmd import handle
            handler = handle
        elif command == "gemma-swarm":
            from leader.gemma_swarm_cmd import handle
            handler = handle
        elif command == "unipat":
            from leader.unipat_swarm_cmd import handle
            handler = handle
        elif command == "orchestrate":
            from leader.orchestrator import handle
            handler = handle
        elif command == "kairos":
            from leader.kairos import handle
            handler = handle
    except ImportError as exc:
        logger.debug("local_handler_import_skip", command=command, error=str(exc))

    _LOCAL_HANDLERS[command] = handler
    return handler


def _node_url(node: str) -> str | None:
    """Resolve node name to HTTP URL if configured, else return None."""
    if node == "academic" and settings.academic_host:
        return f"http://{settings.academic_host}:{settings.academic_port}/task"
    if node == "experiment" and settings.experiment_host:
        return f"http://{settings.experiment_host}:{settings.experiment_port}/task"
    return None


async def _forward_to_node(url: str, task: Task, route: Route, command_payload: dict[str, Any]) -> dict:
    """Forward a task to a remote node via HTTP POST."""
    import httpx

    payload = {
        "text": command_payload.get("text", ""),
        "task_type": route.task_type.value,
        "user_id": task.user_id,
        "payload": command_payload,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def _apply_boost_toggle(enabled: bool) -> None:
    """Apply boost toggle to router + Paperclip (best-effort)."""
    settings.boost_enabled = enabled  # type: ignore[misc]
    router = get_model_router()
    if router:
        router.config.boost_enabled = enabled
    log_event("boost_toggled", enabled=enabled, source="dispatch")

    if settings.paperclip_url and settings.paperclip_api_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{settings.paperclip_url}/api/companies/{settings.paperclip_company_id}"
                    f"/agents/{settings.paperclip_agent_id}/boost",
                    json={"enabled": enabled},
                    headers={"Authorization": f"Bearer {settings.paperclip_api_key}"},
                )
        except Exception as exc:
            logger.debug("boost_paperclip_sync_failed", error=str(exc))


async def _handle_boost_command(task: Task, args: str) -> TaskResult:
    """Handle /boost on|off|status — toggle AIClient boost tier.

    Requires Paperclip to persist state. Falls back to local toggle
    if Paperclip is unavailable.
    """
    action = args.strip().lower() or "status"

    if action == "status":
        router = get_model_router()
        if router:
            stats = router.stats
            on_off = "ON" if stats["boost_enabled"] else "OFF"
            exhausted = " (CREDITS EXHAUSTED)" if stats["credits_exhausted"] else ""
            output = (
                f"Boost: {on_off}{exhausted}\n"
                f"Today: {stats['boost_today']}/{stats['boost_daily_limit']} calls\n"
                f"Model: {stats['models']['boost']}\n"
                f"Toggle: /boost on or /boost off"
            )
            return TaskResult(
                task_id=task.task_id,
                agent_name="LeaderDispatch",
                status="ok",
                result={
                    "action": "boost_status",
                    "output": output,
                    "enabled": stats["boost_enabled"],
                    "today_calls": stats["boost_today"],
                    "daily_limit": stats["boost_daily_limit"],
                    "credits_exhausted": stats["credits_exhausted"],
                },
            )
        enabled = getattr(settings, "boost_enabled", False)
        return TaskResult(
            task_id=task.task_id,
            agent_name="LeaderDispatch",
            status="ok",
            result={
                "action": "boost_status",
                "output": f"Boost: {'ON' if enabled else 'OFF'}\nToggle: /boost on or /boost off",
                "enabled": enabled,
            },
        )

    if action in ("on", "enable", "true", "1"):
        await _apply_boost_toggle(True)
        return TaskResult(
            task_id=task.task_id,
            agent_name="LeaderDispatch",
            status="ok",
            result={"action": "boost_enabled", "output": "Boost tier ENABLED. Free AI models active for eligible tasks."},
        )

    if action in ("off", "disable", "false", "0"):
        await _apply_boost_toggle(False)
        return TaskResult(
            task_id=task.task_id,
            agent_name="LeaderDispatch",
            status="ok",
            result={"action": "boost_disabled", "output": "Boost tier DISABLED. Using local Ollama only."},
        )

    return TaskResult(
        task_id=task.task_id,
        agent_name="LeaderDispatch",
        status="error",
        result={"error": f"Unknown boost action: {action}. Use: on, off, or status"},
    )


async def handle(task: Task) -> TaskResult:
    """Leader dispatch handler.

    Accepts a task, determines routing, and returns either:
    - A direct result (if node is reachable via HTTP)
    - A dispatch instruction (for the gateway to forward via node.invoke)
    - A campaign plan (for multi-step requests)
    """
    text = task.payload.get("text", "")
    raw_command, args = parse_command(text)
    command = _normalize_command(raw_command)

    # Fast local Telegram-safe help path: no governance, memory, or LLM hop.
    if command == "help":
        return _build_help_result(task)

    # Pre-dispatch hook: budget check + issue creation + DRVP event
    hook_text = text or str(task.payload.get("plan_path") or task.payload.get("source", ""))
    blocked = await pre_dispatch_hook(task, hook_text)
    if blocked:
        return TaskResult(
            task_id=task.task_id,
            agent_name="LeaderDispatch",
            status="error",
            result=blocked,
        )

    # Audit: log task arrival
    audit = _get_audit_mw()
    if audit:
        audit.log_task_start(task.task_id, "LeaderDispatch", task.payload)

    # Memory: pre-load relevant context if available
    memory = _get_memory_mw()
    if memory and text:
        try:
            prior_context = await memory.pre_load(
                task.task_id, "LeaderDispatch", "leader", text
            )
            if prior_context:
                task.payload["prior_context"] = prior_context
        except Exception as exc:
            logger.debug("memory_preload_skip", error=str(exc))

    if _is_plan_file_task(task):
        return await _handle_plan_file_task(task)

    if command == "status":
        log_event("status_check", source="leader")
        n_cmds = len(ROUTING_TABLE)
        team_runtime = _team_runtime_status_summary()
        if team_runtime.get("enabled"):
            runtime_line = (
                f"Team Runtime: {team_runtime['team_count']} teams, "
                f"{team_runtime['total_tasks']} tasks, {team_runtime['total_events']} events"
            )
        else:
            runtime_line = "Team Runtime: unavailable"
        return TaskResult(
            task_id=task.task_id,
            agent_name="LeaderDispatch",
            status="ok",
            result={
                "action": "status",
                "output": (
                    "DarkLab Cluster: OK\n"
                    f"Commands: {n_cmds} registered\n"
                    "Role: leader\n"
                    f"{runtime_line}\n"
                    "Send /help for command list."
                ),
                "team_runtime": team_runtime,
            },
        )

    if command == "boost":
        return await _handle_boost_command(task, args)

    if command and command in ROUTING_TABLE:
        route = ROUTING_TABLE[command]
        log_event("dispatch", command=command, target_node=route.node, skill=route.skill)
        await _team_runtime_record_pending(task, command, route, args)
        worktree_block = await _ensure_worktree_allocation(task, command, route)
        if worktree_block:
            return TaskResult(
                task_id=task.task_id,
                agent_name="LeaderDispatch",
                status="error",
                result=worktree_block,
            )
        command_payload = _build_command_payload(task.payload, args)

        # Leader-local commands: execute handler directly if registered
        if route.node == "leader":
            handler = _get_local_handler(command)
            if handler:
                try:
                    task.payload = command_payload
                    await _team_runtime_mark_started(task, command, route, args)
                    result = await handler(task)
                    log_event("dispatch_local_ok", command=command)
                    await _team_runtime_mark_completed(task, command, route, result)
                    return result
                except Exception as exc:
                    logger.warning("local_handler_failed", command=command, error=str(exc))
                    await _team_runtime_mark_failed(task, command, route, str(exc))
                    return TaskResult(
                        task_id=task.task_id,
                        agent_name="LeaderDispatch",
                        status="error",
                        result={"error": str(exc), "command": command},
                    )

        # Try direct HTTP forwarding if node address is configured
        node_url = _node_url(route.node)
        if node_url:
            try:
                await _team_runtime_mark_started(task, command, route, args)
                result_data = await _forward_to_node(node_url, task, route, command_payload)
                log_event("dispatch_http_ok", command=command, node=route.node)
                forwarded = TaskResult(
                    task_id=task.task_id,
                    agent_name="LeaderDispatch",
                    status="ok",
                    result={"action": "forwarded", "node_result": result_data},
                )
                await _team_runtime_mark_completed(task, command, route, forwarded)
                return forwarded
            except Exception as e:
                logger.warning("http_forward_failed", node=route.node, error=str(e))
                await _team_runtime_mark_failed(task, command, route, str(e))

        # Fallback: return OpenClaw node.invoke instruction
        invoke_msg = build_node_invoke(route, command_payload)
        return TaskResult(
            task_id=task.task_id,
            agent_name="LeaderDispatch",
            status="ok",
            result={
                "action": "dispatch",
                "route": {"node": route.node, "skill": route.skill},
                "node_invoke": invoke_msg,
            },
        )

    # No direct command — try LangGraph swarm for intelligent routing
    swarm = await get_swarm_app()
    if swarm is not None:
        try:
            return await _dispatch_via_swarm(swarm, task, text)
        except Exception as exc:
            logger.warning("swarm_dispatch_error", error=str(exc))
            # Fall through to plan_campaign

    # Fallback: use Claude to plan a campaign
    plan = await plan_campaign(text)
    log_event("campaign_plan", n_steps=len(plan))

    # Create Paperclip issue for tracking
    gov = _get_governance()
    issue = None
    if gov:
        issue = await gov.open_issue(
            request_id=task.task_id,
            title=text[:120],
            agent_name="LeaderDispatch",
            device="leader",
            description=f"Campaign plan with {len(plan)} steps",
        )

    issue_id = issue.get("id") if issue else None
    issue_key = issue.get("key") if issue else None

    # Request approval for multi-step campaigns
    needs_approval = len(plan) > 1
    approval = None
    if gov and needs_approval:
        approval = await gov.request_campaign_approval(
            request_id=task.task_id,
            plan=plan,
            issue_id=issue_id,
        )

    # requires_approval = True if multi-step and not yet approved
    approved = approval["approved"] if approval else False

    # If approved (or single-step), execute via CampaignEngine
    if approved or not needs_approval:
        engine = _get_campaign_engine()
        if engine:
            try:
                campaign_result = await engine.execute(
                    request_id=task.task_id,
                    plan=plan,
                    agent_name="LeaderDispatch",
                    device="leader",
                )
                log_event(
                    "campaign_executed",
                    status=campaign_result.status,
                    completed=len(campaign_result.completed_steps),
                    failed=len(campaign_result.failed_steps),
                )
                return TaskResult(
                    task_id=task.task_id,
                    agent_name="LeaderDispatch",
                    status="ok",
                    result={
                        "action": "campaign_executed",
                        "campaign": campaign_result.to_dict(),
                        "issue_id": issue_id,
                        "issue_key": issue_key,
                    },
                )
            except Exception as exc:
                logger.warning("campaign_execution_error", error=str(exc))

    return TaskResult(
        task_id=task.task_id,
        agent_name="LeaderDispatch",
        status="ok",
        result={
            "action": "campaign",
            "plan": plan,
            "requires_approval": needs_approval and not approved,
            "approval": approval,
            "issue_id": issue_id,
            "issue_key": issue_key,
        },
    )


async def _dispatch_via_swarm(swarm: Any, task: Task, text: str) -> TaskResult:
    """Route a free-form request through the LangGraph swarm.

    Invokes the swarm graph which uses the leader LLM to select and hand off
    to the most appropriate agent. Returns the last AIMessage as a TaskResult.
    """
    from langchain_core.messages import HumanMessage

    thread_id = task.task_id
    result = await swarm.ainvoke(
        {"messages": [HumanMessage(content=text)], "request_id": task.task_id},
        config={"configurable": {"thread_id": thread_id}},
    )

    # Extract last AI message content
    messages = result.get("messages", [])
    content = ""
    agent_name = "swarm"
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            agent_name = getattr(msg, "name", None) or "swarm"
            break

    # Try to parse as JSON, otherwise wrap as string result
    try:
        result_data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        result_data = {"raw": content}

    log_event("swarm_dispatch_ok", agent=agent_name)
    return TaskResult(
        task_id=task.task_id,
        agent_name=agent_name,
        status="ok",
        result={"action": "swarm", "agent": agent_name, "data": result_data},
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="LeaderDispatch")
