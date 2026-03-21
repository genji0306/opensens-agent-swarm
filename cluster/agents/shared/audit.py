"""Append-only JSONL audit logger for DarkLab agents."""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from shared.config import settings
from shared.models import Task, TaskResult


def _audit_path() -> Path:
    return settings.logs_dir / "audit.jsonl"


def _write_entry(entry: dict) -> None:
    path = _audit_path()
    with open(path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def log_task(task: Task) -> None:
    _write_entry({
        "event": "task_created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task.task_id,
        "task_type": task.task_type.value,
        "user_id": task.user_id,
        "payload_hash": hashlib.sha256(
            json.dumps(task.payload, sort_keys=True, default=str).encode()
        ).hexdigest(),
    })


def log_result(result: TaskResult) -> None:
    _write_entry({
        "event": "task_completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": result.task_id,
        "agent_name": result.agent_name,
        "status": result.status,
        "artifact_count": len(result.artifacts),
    })


def log_event(event_type: str, **kwargs) -> None:
    _write_entry({
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    })
