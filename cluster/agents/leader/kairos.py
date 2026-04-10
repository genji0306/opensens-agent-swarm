"""KairosDaemon — ambient intelligence daemon for Leader (Phase 24).

KAIROS (Ancient Greek: 'the right moment') runs at OS-level idle priority
on Leader and performs:

1. **Heartbeat loop** (60s) — scan idle budget, expired leases, stuck campaigns
2. **autoDream** (nightly 03:00) — knowledge base consolidation in a forked subprocess
3. **Proactive suggestions** — gap detection, follow-up research queueing
4. **RL rollout curation** — identify high-quality training traces

Hard rules (non-negotiable):
- Never calls Sonnet or Opus. KAIROS is local-only by policy.
- Subject to IdleBudgetRule: refuses to act if today's cost > 20% of daily cap.
- All actions emit ``kairos.*`` DRVP events for Boss visibility.

Dispatch handler ``handle()`` is the entry point for ``/kairos`` commands.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

try:
    import structlog
except ImportError:  # pragma: no cover
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

from shared.models import Task, TaskResult

__all__ = ["KairosDaemon", "KairosDaemonConfig", "handle"]

logger = structlog.get_logger("darklab.kairos")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_KAIROS_ENABLED = os.environ.get("KAIROS_ENABLED", "true").lower() in ("1", "true", "yes")
_DARKLAB_HOME = Path(os.environ.get("DARKLAB_HOME", str(Path.home() / ".darklab")))


# ---------------------------------------------------------------------------
# DRVP event helper (best-effort, never crash)
# ---------------------------------------------------------------------------

async def _emit_drvp(event_type_value: str, payload: dict[str, Any]) -> None:
    """Best-effort DRVP event emission."""
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

        et = DRVPEventType(event_type_value)
        await emit(DRVPEvent(
            event_type=et,
            request_id=f"kairos-{uuid.uuid4().hex[:8]}",
            agent_name="KairosDaemon",
            device="leader",
            payload=payload,
        ))
    except Exception as exc:
        logger.debug("kairos_drvp_emit_skip", error=str(exc))


# ---------------------------------------------------------------------------
# KairosDaemonConfig
# ---------------------------------------------------------------------------

class KairosDaemonConfig:
    """Configuration for the KAIROS daemon."""

    def __init__(
        self,
        *,
        kb_dir: str | Path = "~/.darklab/data",
        rollout_dir: str | Path | None = None,
        heartbeat_interval_s: float = 60.0,
        autodream_hour: int = 3,
        idle_budget_cap: float = 0.2,
        enabled: bool = True,
    ) -> None:
        self.kb_dir = Path(kb_dir).expanduser().resolve()
        self.rollout_dir = Path(rollout_dir) if rollout_dir else None
        self.heartbeat_interval_s = heartbeat_interval_s
        self.autodream_hour = int(os.environ.get("KAIROS_AUTODREAM_HOUR", str(autodream_hour)))
        self.idle_budget_cap = idle_budget_cap
        self.enabled = _KAIROS_ENABLED and enabled


# ---------------------------------------------------------------------------
# KairosDaemon
# ---------------------------------------------------------------------------

class KairosDaemon:
    """Main KAIROS daemon -- runs on Leader as a background asyncio task.

    Three loops:
    - Heartbeat (every 60s): health checks, budget, stuck campaigns
    - autoDream (nightly at autodream_hour): knowledge consolidation
    - Proactive suggestions: gap detection, RL rollout curation
    """

    def __init__(
        self,
        config: KairosDaemonConfig | None = None,
        *,
        heartbeat: Any | None = None,
        on_suggestion: Callable[..., Awaitable[None]] | None = None,
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config or KairosDaemonConfig()
        self._on_suggestion = on_suggestion
        self._on_event = on_event
        self._task: asyncio.Task[None] | None = None
        self._last_autodream_date: str = ""
        self._running = False
        self._started_at: str | None = None

        # Lazy-init core kairos components
        self._heartbeat: Any = heartbeat
        self._autodream: Any = None
        self._suggester: Any = None

    def _ensure_components(self) -> None:
        """Lazily initialise core kairos components."""
        if self._heartbeat is not None and self._autodream is not None:
            return
        try:
            from oas_core.kairos.heartbeat import KairosHeartbeat
            from oas_core.kairos.autodream import AutoDream
            from oas_core.kairos.proactive import ProactiveSuggester

            if self._heartbeat is None:
                self._heartbeat = KairosHeartbeat(
                    idle_budget_cap=self.config.idle_budget_cap,
                )
            if self._autodream is None:
                self._autodream = AutoDream(kb_dir=self.config.kb_dir)
            if self._suggester is None:
                self._suggester = ProactiveSuggester(
                    kb_dir=self.config.kb_dir,
                    rollout_dir=self.config.rollout_dir,
                )
        except ImportError as exc:
            logger.warning("kairos_core_import_error", error=str(exc))

    @property
    def running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the daemon loop."""
        if not self.config.enabled or self._running:
            return
        self._ensure_components()
        self._running = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._task = asyncio.create_task(self._run(), name="kairos-daemon")
        await self._emit("kairos.started", {
            "started_at": self._started_at,
            "heartbeat_interval": self.config.heartbeat_interval_s,
            "autodream_hour": self.config.autodream_hour,
        })
        logger.info("kairos_started")

    async def stop(self) -> None:
        """Gracefully stop the daemon."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, BaseException):
                pass
            self._task = None
        await self._emit("kairos.stopped", {
            "started_at": self._started_at,
            "stopped_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("kairos_stopped")

    def status(self) -> dict[str, Any]:
        """Return daemon status snapshot."""
        snap = None
        is_blocked = False
        if self._heartbeat is not None:
            snap = getattr(self._heartbeat, "last_snapshot", None)
            is_blocked = getattr(self._heartbeat, "is_blocked", False)
        return {
            "running": self.running,
            "enabled": self.config.enabled,
            "started_at": self._started_at,
            "budget_blocked": is_blocked,
            "last_heartbeat": snap.to_dict() if snap else None,
            "last_autodream_date": self._last_autodream_date,
        }

    async def run_heartbeat(self) -> dict[str, Any]:
        """Execute a single heartbeat scan (callable from /kairos heartbeat)."""
        self._ensure_components()
        if self._heartbeat is None:
            return {"error": "heartbeat component unavailable"}
        snapshot = await self._heartbeat.scan()
        result = snapshot.to_dict()
        await self._emit("kairos.heartbeat.tick", result)
        return result

    async def run_autodream(self) -> dict[str, Any]:
        """Execute a single autoDream cycle (callable from /kairos autodream)."""
        self._ensure_components()
        await self._emit("kairos.autodream.started", {"phase": "24"})
        if self._autodream is None:
            result = {"error": "autodream component unavailable", "succeeded": False}
            await self._emit("kairos.autodream.completed", result)
            return result
        try:
            result = self._autodream.consolidate()
        except Exception as exc:
            result = {"succeeded": False, "error": str(exc)}
        await self._emit("kairos.autodream.completed", result)
        return result

    async def run_proactive_suggest(self) -> dict[str, Any]:
        """Execute a single proactive suggestion scan."""
        self._ensure_components()
        if self._suggester is None:
            return {"suggestions": [], "error": "proactive component unavailable"}
        try:
            suggestions = self._suggester.scan()
            for s in suggestions[:3]:
                await self._emit("kairos.proactive.suggested", s.to_dict())
                if self._on_suggestion is not None:
                    await self._on_suggestion(s)
            return {
                "suggestions_found": len(suggestions),
                "suggestions": [s.to_dict() for s in suggestions[:10]],
            }
        except Exception as exc:
            logger.warning("kairos_suggestion_error", error=str(exc))
            return {"suggestions": [], "error": str(exc)}

    # -- Internal loop --

    async def _run(self) -> None:
        try:
            while self._running:
                try:
                    await self._tick()
                except Exception as exc:
                    logger.error("kairos_tick_error", error=str(exc))
                await asyncio.sleep(self.config.heartbeat_interval_s)
        except asyncio.CancelledError:
            pass

    async def _tick(self) -> None:
        # 1. Heartbeat scan
        if self._heartbeat is not None:
            snapshot = await self._heartbeat.scan()
            await self._emit("kairos.heartbeat.tick", snapshot.to_dict())

            if snapshot.budget_blocked:
                await self._emit("kairos.blocked", {
                    "reason": "idle_budget_exceeded",
                    "ratio": snapshot.budget_ratio,
                })
                return

        # 2. Check for nightly autoDream
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        if (
            now.hour == self.config.autodream_hour
            and self._last_autodream_date != today
        ):
            self._last_autodream_date = today
            await self.run_autodream()

        # 3. Proactive suggestions (every tick when not blocked)
        await self.run_proactive_suggest()

    async def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Emit a DRVP event (best-effort)."""
        if self._on_event is not None:
            try:
                await self._on_event(event_type, payload)
            except Exception:
                pass
        await _emit_drvp(event_type, payload)


# ---------------------------------------------------------------------------
# Dispatch handler for /kairos command
# ---------------------------------------------------------------------------

# Module-level daemon singleton (lazy init, only via /kairos start)
_daemon: KairosDaemon | None = None


def _format_status(status: dict[str, Any]) -> str:
    lines = ["KAIROS Daemon Status", "=" * 40]
    lines.append(f"Running: {status.get('running', False)}")
    lines.append(f"Enabled: {status.get('enabled', False)}")
    if status.get("started_at"):
        lines.append(f"Started: {status['started_at']}")
    lines.append(f"Budget blocked: {status.get('budget_blocked', False)}")
    hb = status.get("last_heartbeat")
    if hb:
        lines.append(f"Last heartbeat: budget_ratio={hb.get('budget_ratio', '?')}, "
                      f"stuck={hb.get('stuck_campaigns', 0)}")
    return "\n".join(lines)


def _format_heartbeat(result: dict[str, Any]) -> str:
    lines = ["KAIROS Heartbeat", "-" * 30]
    lines.append(f"Budget blocked: {result.get('budget_blocked', False)}")
    lines.append(f"Budget ratio: {result.get('budget_ratio', 0):.0%}")
    lines.append(f"Stuck campaigns: {result.get('stuck_campaigns', 0)}")
    lines.append(f"DEV reachable: {result.get('dev_reachable', False)}")
    return "\n".join(lines)


def _format_autodream(result: dict[str, Any]) -> str:
    lines = ["KAIROS autoDream", "-" * 30]
    lines.append(f"Entries before: {result.get('entries_before', 0)}")
    lines.append(f"Entries after: {result.get('entries_after', 0)}")
    lines.append(f"Deduplicated: {result.get('deduplicated', 0)}")
    lines.append(f"Pruned: {result.get('pruned', 0)}")
    lines.append(f"Merged: {result.get('merged', 0)}")
    lines.append(f"Succeeded: {result.get('succeeded', '?')}")
    return "\n".join(lines)


def _format_suggest(result: dict[str, Any]) -> str:
    lines = ["KAIROS Proactive Suggestions", "-" * 30]
    lines.append(f"Suggestions found: {result.get('suggestions_found', 0)}")
    for s in result.get("suggestions", [])[:5]:
        kind = s.get("kind", "?")
        topic = s.get("topic", "?")
        lines.append(f"  [{kind}] {topic}")
    return "\n".join(lines)


async def handle(task: Task) -> TaskResult:
    """Handle /kairos command.

    Subcommands:
      /kairos status    -- daemon health + last heartbeat
      /kairos heartbeat -- run one heartbeat cycle
      /kairos autodream -- run autoDream manually
      /kairos suggest   -- run proactive suggestion scan
      /kairos start     -- start the daemon loops
      /kairos stop      -- stop the daemon loops
    """
    global _daemon

    text = task.payload.get("text", "")
    parts = text.strip().split()
    subcommand = parts[0].lower() if parts else "status"

    # Normalise: if first word is the main command, look at second word
    if subcommand in ("kairos", "/kairos"):
        subcommand = parts[1].lower() if len(parts) > 1 else "status"

    logger.info("kairos_handle", subcommand=subcommand)

    try:
        if subcommand == "status":
            if _daemon is not None:
                status_data = _daemon.status()
            else:
                status_data = {
                    "running": False,
                    "enabled": _KAIROS_ENABLED,
                    "budget_blocked": False,
                    "last_heartbeat": None,
                    "last_autodream_date": "",
                }
            return TaskResult(
                task_id=task.task_id,
                agent_name="KairosDaemon",
                status="ok",
                result={
                    "action": "kairos_status",
                    "output": _format_status(status_data),
                    **status_data,
                },
            )

        elif subcommand == "heartbeat":
            daemon = _daemon or KairosDaemon()
            result = await daemon.run_heartbeat()
            return TaskResult(
                task_id=task.task_id,
                agent_name="KairosDaemon",
                status="ok",
                result={
                    "action": "kairos_heartbeat",
                    "output": _format_heartbeat(result),
                    **result,
                },
            )

        elif subcommand == "autodream":
            daemon = _daemon or KairosDaemon()
            result = await daemon.run_autodream()
            return TaskResult(
                task_id=task.task_id,
                agent_name="KairosDaemon",
                status="ok",
                result={
                    "action": "kairos_autodream",
                    "output": _format_autodream(result),
                    **result,
                },
            )

        elif subcommand == "suggest":
            daemon = _daemon or KairosDaemon()
            result = await daemon.run_proactive_suggest()
            return TaskResult(
                task_id=task.task_id,
                agent_name="KairosDaemon",
                status="ok",
                result={
                    "action": "kairos_suggest",
                    "output": _format_suggest(result),
                    **result,
                },
            )

        elif subcommand == "start":
            if _daemon is None:
                _daemon = KairosDaemon()
            await _daemon.start()
            return TaskResult(
                task_id=task.task_id,
                agent_name="KairosDaemon",
                status="ok",
                result={"action": "kairos_start", "output": "KAIROS daemon started."},
            )

        elif subcommand == "stop":
            if _daemon is not None:
                await _daemon.stop()
            return TaskResult(
                task_id=task.task_id,
                agent_name="KairosDaemon",
                status="ok",
                result={"action": "kairos_stop", "output": "KAIROS daemon stopped."},
            )

        else:
            return TaskResult(
                task_id=task.task_id,
                agent_name="KairosDaemon",
                status="error",
                result={
                    "action": "kairos_unknown",
                    "error": f"Unknown subcommand: {subcommand}",
                    "usage": "Subcommands: status, heartbeat, autodream, suggest, start, stop",
                },
            )

    except Exception as exc:
        logger.error("kairos_handle_error", error=str(exc), subcommand=subcommand)
        return TaskResult(
            task_id=task.task_id,
            agent_name="KairosDaemon",
            status="error",
            result={"action": "kairos_error", "error": str(exc)},
        )


# ---------------------------------------------------------------------------
# Main entry (for direct execution via OpenClaw system.run)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from shared.node_bridge import run_agent
    run_agent(handle, agent_name="KairosDaemon")
