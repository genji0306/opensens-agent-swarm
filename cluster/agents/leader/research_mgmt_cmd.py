"""Research management commands — /results and /schedule.

/results — lists recent deep research results from the knowledge base
/schedule — manages recurring auto-research schedules
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.models import Task, TaskResult
from shared.config import settings

__all__ = ["handle_results", "handle_schedule"]

logger = logging.getLogger("darklab.research_mgmt")

SCHEDULE_PATH = Path.home() / ".darklab" / "deep-research" / "schedule.json"


async def handle_results(task: Task) -> TaskResult:
    """List recent deep research results.

    Usage: /results
           /results 10  (last N results)
    """
    args = task.payload.get("text", "").strip()
    limit = 10
    if args.isdigit():
        limit = int(args)

    try:
        from oas_core.deep_research.knowledge_base import KnowledgeBase
        kb = KnowledgeBase(settings.darklab_home / "deep-research")

        if not kb.knowledge_path.exists():
            return TaskResult(
                task_id=task.task_id,
                agent_name="research-mgmt",
                status="ok",
                result={"results": [], "message": "No research results yet."},
            )

        entries: list[dict[str, Any]] = []
        with open(kb.knowledge_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        # Return most recent
        recent = entries[-limit:]
        recent.reverse()

        formatted = []
        for i, e in enumerate(recent, 1):
            formatted.append({
                "rank": i,
                "topic": e.get("topic", ""),
                "score": e.get("score", 0),
                "sources": e.get("sources_count", 0),
                "iterations": e.get("iterations", 0),
                "converged": e.get("converged", False),
                "timestamp": e.get("timestamp", ""),
            })

        stats = kb.get_stats()
        return TaskResult(
            task_id=task.task_id,
            agent_name="research-mgmt",
            status="ok",
            result={
                "results": formatted,
                "total": stats["knowledge_entries"],
                "lessons": stats["lessons"],
            },
        )
    except Exception as exc:
        return TaskResult(
            task_id=task.task_id,
            agent_name="research-mgmt",
            status="error",
            result={"error": str(exc)},
        )


async def handle_schedule(task: Task) -> TaskResult:
    """Manage recurring auto-research schedules.

    Usage: /schedule <topic>              — add a daily research schedule
           /schedule --interval 48h <topic> — custom interval
           /schedule --list               — list active schedules
           /schedule --remove <id>        — remove a schedule
    """
    text = task.payload.get("text", "").strip()

    if not text or text == "--list":
        return _list_schedules(task)

    if text.startswith("--remove"):
        schedule_id = text.replace("--remove", "").strip()
        return _remove_schedule(task, schedule_id)

    # Parse interval
    interval_hours = 24
    topic = text
    if "--interval" in text:
        parts = text.split("--interval")
        rest = parts[1].strip()
        interval_str, topic = rest.split(None, 1) if " " in rest else (rest, "")
        interval_str = interval_str.strip().lower()
        if interval_str.endswith("h"):
            try:
                interval_hours = int(interval_str[:-1])
            except ValueError:
                pass
        elif interval_str == "weekly":
            interval_hours = 168

    topic = topic.strip().strip('"').strip("'")
    if not topic:
        return TaskResult(
            task_id=task.task_id,
            agent_name="research-mgmt",
            status="error",
            result={"error": "Usage: /schedule <topic>"},
        )

    # Add schedule
    schedules = _load_schedules()
    schedule_id = f"sched-{len(schedules) + 1:03d}"
    schedules.append({
        "id": schedule_id,
        "topic": topic,
        "interval_hours": interval_hours,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "active": True,
    })
    _save_schedules(schedules)

    return TaskResult(
        task_id=task.task_id,
        agent_name="research-mgmt",
        status="ok",
        result={
            "message": f"Scheduled: '{topic}' every {interval_hours}h",
            "schedule_id": schedule_id,
            "interval_hours": interval_hours,
            "active_schedules": len([s for s in schedules if s.get("active")]),
        },
    )


def _list_schedules(task: Task) -> TaskResult:
    schedules = _load_schedules()
    active = [s for s in schedules if s.get("active")]
    return TaskResult(
        task_id=task.task_id,
        agent_name="research-mgmt",
        status="ok",
        result={
            "schedules": active,
            "total": len(active),
        },
    )


def _remove_schedule(task: Task, schedule_id: str) -> TaskResult:
    schedules = _load_schedules()
    found = False
    for s in schedules:
        if s.get("id") == schedule_id:
            s["active"] = False
            found = True
            break
    if found:
        _save_schedules(schedules)
    return TaskResult(
        task_id=task.task_id,
        agent_name="research-mgmt",
        status="ok",
        result={
            "removed": schedule_id if found else None,
            "message": f"Removed {schedule_id}" if found else f"Schedule {schedule_id} not found",
        },
    )


def _load_schedules() -> list[dict[str, Any]]:
    if SCHEDULE_PATH.exists():
        try:
            return json.loads(SCHEDULE_PATH.read_text())
        except (json.JSONDecodeError, Exception):
            pass
    return []


def _save_schedules(schedules: list[dict[str, Any]]) -> None:
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(json.dumps(schedules, indent=2))
