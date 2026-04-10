"""Background plan watcher service for automatic plan-file execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from oas_core.plan_file import PlanFile
from oas_core.plan_watcher import PlanWatcher

try:
    from oas_core.plan_store_client import PlanStoreClient
except ImportError:  # pragma: no cover - httpx not always present
    PlanStoreClient = None  # type: ignore[assignment,misc]

from shared.models import Task, TaskType

try:
    import structlog
except ImportError:  # pragma: no cover - exercised in minimal test envs
    import logging

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

    class _StructlogCompat:
        @staticmethod
        def get_logger(name: str) -> _StructlogCompatLogger:
            return _StructlogCompatLogger(name)

    structlog = _StructlogCompat()  # type: ignore[assignment]

logger = structlog.get_logger("darklab.plan_watcher")

__all__ = ["PlanWatcherService"]


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "plan"


class PlanWatcherService:
    """Poll a plans directory and execute new stable plan files."""

    def __init__(
        self,
        *,
        plan_dir: str | Path,
        data_dir: str | Path,
        enabled: bool = False,
        interval_seconds: float = 5.0,
        stable_seconds: float = 0.5,
        watcher: PlanWatcher | None = None,
        orchestrator_factory: Callable[[], Any] | None = None,
        task_id_factory: Callable[[], str] | None = None,
        # v2: HTTP mode (§5.1) — takes precedence over filesystem mode
        plan_store_url: str | None = None,
        plan_store_token: str | None = None,
        plan_store_client: Any | None = None,
    ) -> None:
        self.plan_dir = Path(plan_dir).expanduser().resolve()
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.enabled = enabled
        self.interval_seconds = interval_seconds
        self.receipts_dir = self.data_dir / "plan-watcher" / "receipts"
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

        self._watcher = watcher or PlanWatcher(
            self.plan_dir,
            stable_seconds=stable_seconds,
        )
        self._orchestrator_factory = orchestrator_factory
        self._task_id_factory = task_id_factory or (lambda: uuid.uuid4().hex[:12])

        # v2 HTTP plan store
        self._plan_store_client = plan_store_client
        if plan_store_url and PlanStoreClient is not None and plan_store_client is None:
            self._plan_store_client = PlanStoreClient(
                plan_store_url, auth_token=plan_store_token,
            )
        self._http_mode: bool = self._plan_store_client is not None

        self._loop_task: asyncio.Task | None = None
        self._last_scan_at: str | None = None
        self._last_scan_result: dict[str, Any] = {
            "processed": [],
            "skipped": [],
            "errors": [],
            "processed_count": 0,
            "skipped_count": 0,
            "error_count": 0,
        }

    @property
    def running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    def status(self) -> dict[str, Any]:
        """Summarize current watcher state."""
        return {
            "enabled": self.enabled,
            "running": self.running,
            "mode": "http" if self._http_mode else "filesystem",
            "plan_dir": str(self.plan_dir),
            "interval_seconds": self.interval_seconds,
            "receipts_dir": str(self.receipts_dir),
            "receipt_count": self._count_receipts(),
            "last_scan_at": self._last_scan_at,
            "last_scan_result": self._last_scan_result,
        }

    async def start(self) -> None:
        """Start the background polling loop if enabled."""
        if not self.enabled or self.running:
            return
        self._loop_task = asyncio.create_task(self._run_loop(), name="darklab-plan-watcher")
        logger.info(
            "plan_watcher_started",
            plan_dir=str(self.plan_dir),
            interval_seconds=self.interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the background polling loop."""
        task = self._loop_task
        self._loop_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("plan_watcher_stopped", plan_dir=str(self.plan_dir))

    async def scan_once(self) -> dict[str, Any]:
        """Scan for new plans and execute them.

        In HTTP mode (v2), polls the Plan Store API. In filesystem mode
        (legacy), scans the local plan directory.
        """
        if self._http_mode:
            return await self._scan_http()
        return await self._scan_filesystem()

    async def _scan_http(self) -> dict[str, Any]:
        """Poll the OAS Plan Store for new plans over HTTP (§5.1)."""
        processed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        store = self._plan_store_client

        try:
            payloads = await store.fetch_new()
        except Exception as exc:
            logger.error("plan_store_fetch_failed", error=str(exc))
            summary = {
                "processed": [], "skipped": [], "errors": [{"error": str(exc)}],
                "processed_count": 0, "skipped_count": 0, "error_count": 1,
            }
            self._last_scan_at = datetime.now(timezone.utc).isoformat()
            self._last_scan_result = summary
            return summary

        for payload in payloads:
            plan_id = payload.get("id", "unknown")
            try:
                plan_file = store.parse_plan(payload)
            except Exception as exc:
                errors.append({"plan_id": plan_id, "error": str(exc)})
                logger.warning("plan_store_parse_failed", plan_id=plan_id, error=str(exc))
                continue

            receipt_path = self._receipt_path(plan_file)
            if receipt_path.exists():
                skipped.append({"plan_id": plan_id, "reason": "already_processed"})
                continue

            task = Task(
                task_id=self._task_id_factory(),
                task_type=TaskType.PLAN,
                payload={
                    "source": "plan_file",
                    "plan_markdown": payload.get("markdown", ""),
                    "text": plan_file.title,
                },
            )
            try:
                orchestrator = self._build_orchestrator()
                result = await orchestrator.handle_task(task)
                self._write_receipt(
                    plan_id=plan_file.id,
                    source_path=Path(f"http://{plan_id}"),
                    source_sha256=plan_file.source_sha256,
                    payload={
                        "status": "ok",
                        "task_id": task.task_id,
                        "result_action": result.result.get("action"),
                        "mode": "http",
                    },
                )
                try:
                    await store.mark_accepted(plan_id)
                except Exception:
                    pass
                processed.append({
                    "plan_id": plan_id,
                    "task_id": task.task_id,
                    "action": result.result.get("action"),
                })
                logger.info(
                    "plan_store_processed",
                    plan_id=plan_id,
                    task_id=task.task_id,
                )
            except Exception as exc:
                self._write_receipt(
                    plan_id=plan_file.id,
                    source_path=Path(f"http://{plan_id}"),
                    source_sha256=plan_file.source_sha256,
                    payload={"status": "error", "task_id": task.task_id, "error": str(exc)},
                )
                errors.append({"plan_id": plan_id, "task_id": task.task_id, "error": str(exc)})
                logger.error("plan_store_execution_failed", plan_id=plan_id, error=str(exc))

        summary = {
            "processed": processed, "skipped": skipped, "errors": errors,
            "processed_count": len(processed), "skipped_count": len(skipped),
            "error_count": len(errors),
        }
        self._last_scan_at = datetime.now(timezone.utc).isoformat()
        self._last_scan_result = summary
        return summary

    async def _scan_filesystem(self) -> dict[str, Any]:
        """Legacy filesystem scan (pre-v2)."""
        processed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for path in self._watcher.scan():
            # Emit plan.detected
            await _emit_drvp("PLAN_DETECTED", "plan-watcher", {"path": str(path)})

            try:
                plan_file = PlanFile.from_path(path)
            except Exception as exc:
                file_sha = self._sha256_file(path)
                receipt = self._write_receipt(
                    plan_id=None,
                    source_path=path,
                    source_sha256=file_sha,
                    payload={
                        "status": "error",
                        "error": str(exc),
                        "source_path": str(path),
                    },
                )
                errors.append(
                    {
                        "path": str(path),
                        "error": str(exc),
                        "receipt": str(receipt),
                    }
                )
                logger.warning("plan_watcher_parse_failed", path=str(path), error=str(exc))
                await _emit_drvp("PLAN_ERROR", "plan-watcher", {
                    "path": str(path), "error": str(exc),
                })
                continue

            # Emit plan.parsed
            await _emit_drvp("PLAN_PARSED", "plan-watcher", {
                "plan_id": plan_file.id, "title": plan_file.title,
                "path": str(path), "steps": len(plan_file.steps),
            })

            receipt_path = self._receipt_path(plan_file)
            if receipt_path.exists():
                skipped.append(
                    {
                        "plan_id": plan_file.id,
                        "path": str(path),
                        "reason": "already_processed",
                        "receipt": str(receipt_path),
                    }
                )
                continue

            task = Task(
                task_id=self._task_id_factory(),
                task_type=TaskType.PLAN,
                payload={
                    "source": "plan_file",
                    "plan_path": str(path),
                    "text": plan_file.title,
                },
            )
            try:
                orchestrator = self._build_orchestrator()
                result = await orchestrator.handle_task(task)
                receipt = self._write_receipt(
                    plan_id=plan_file.id,
                    source_path=path,
                    source_sha256=plan_file.source_sha256,
                    payload={
                        "status": "ok",
                        "task_id": task.task_id,
                        "result_action": result.result.get("action"),
                        "path": str(path),
                    },
                )
                processed.append(
                    {
                        "plan_id": plan_file.id,
                        "task_id": task.task_id,
                        "path": str(path),
                        "action": result.result.get("action"),
                        "receipt": str(receipt),
                    }
                )
                logger.info(
                    "plan_watcher_processed",
                    plan_id=plan_file.id,
                    task_id=task.task_id,
                    path=str(path),
                )
            except Exception as exc:
                receipt = self._write_receipt(
                    plan_id=plan_file.id,
                    source_path=path,
                    source_sha256=plan_file.source_sha256,
                    payload={
                        "status": "error",
                        "task_id": task.task_id,
                        "error": str(exc),
                        "path": str(path),
                    },
                )
                errors.append(
                    {
                        "plan_id": plan_file.id,
                        "task_id": task.task_id,
                        "path": str(path),
                        "error": str(exc),
                        "receipt": str(receipt),
                    }
                )
                logger.error(
                    "plan_watcher_execution_failed",
                    plan_id=plan_file.id,
                    task_id=task.task_id,
                    error=str(exc),
                )

        summary = {
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
            "processed_count": len(processed),
            "skipped_count": len(skipped),
            "error_count": len(errors),
        }
        self._last_scan_at = datetime.now(timezone.utc).isoformat()
        self._last_scan_result = summary
        return summary

    async def _run_loop(self) -> None:
        try:
            while True:
                try:
                    await self.scan_once()
                except Exception as exc:
                    logger.error("plan_watcher_scan_loop_failed", error=str(exc))
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            raise

    def _build_orchestrator(self) -> Any:
        if self._orchestrator_factory is not None:
            return self._orchestrator_factory()

        from leader.dispatch import _get_campaign_engine, _get_governance
        from leader.orchestrator import OrchestratorAgent

        return OrchestratorAgent(
            campaign_engine=_get_campaign_engine(),
            governance=_get_governance(),
            plan_dir=self.plan_dir,
        )

    def _receipt_path(self, plan_file: PlanFile) -> Path:
        stem = _slug(plan_file.id)
        return self.receipts_dir / f"{stem}-{plan_file.source_sha256[:16]}.json"

    def _write_receipt(
        self,
        *,
        plan_id: str | None,
        source_path: Path,
        source_sha256: str,
        payload: dict[str, Any],
    ) -> Path:
        stem = _slug(plan_id or source_path.stem)
        receipt = self.receipts_dir / f"{stem}-{source_sha256[:16]}.json"
        content = {
            "plan_id": plan_id,
            "source_path": str(source_path),
            "source_sha256": source_sha256,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        tmp = receipt.with_suffix(receipt.suffix + ".tmp")
        tmp.write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")
        tmp.replace(receipt)
        return receipt

    @staticmethod
    def _sha256_file(path: Path) -> str:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            return ""

    def _count_receipts(self) -> int:
        return sum(1 for _ in self.receipts_dir.glob("*.json"))


async def _emit_drvp(event_name: str, request_id: str, payload: dict[str, Any]) -> None:
    """Emit a DRVP event. Best-effort — swallows all errors."""
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        event_type = getattr(DRVPEventType, event_name, None)
        if event_type is None:
            return
        await emit(DRVPEvent(
            event_type=event_type,
            request_id=request_id,
            agent_name="PlanWatcher",
            device="leader",
            payload=payload,
        ))
    except Exception:
        pass
