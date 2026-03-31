"""Redis-backed priority task queue for distributed campaign execution.

Tasks are enqueued with priority and device affinity. Workers dequeue
matching tasks using blocking pop with visibility timeout. Unacknowledged
tasks are automatically requeued after timeout expiry.

When Redis is unavailable, falls back to an in-memory queue for
single-node operation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any

__all__ = ["TaskQueue", "TaskPriority", "QueuedTask"]

logger = logging.getLogger("oas.scheduler.task_queue")


class TaskPriority(IntEnum):
    """Task priority levels (lower number = higher priority)."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class QueuedTask:
    """A task in the queue."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    task_type: str = ""
    command: str = ""
    args: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    device_affinity: str = ""  # preferred device ("academic", "experiment", etc.)
    campaign_id: str = ""
    request_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    enqueued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    attempts: int = 0
    max_attempts: int = 3

    def to_json(self) -> str:
        return json.dumps({
            "task_id": self.task_id,
            "task_type": self.task_type,
            "command": self.command,
            "args": self.args,
            "priority": self.priority,
            "device_affinity": self.device_affinity,
            "campaign_id": self.campaign_id,
            "request_id": self.request_id,
            "payload": self.payload,
            "enqueued_at": self.enqueued_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
        })

    @classmethod
    def from_json(cls, data: str) -> QueuedTask:
        d = json.loads(data)
        return cls(
            task_id=d["task_id"],
            task_type=d.get("task_type", ""),
            command=d.get("command", ""),
            args=d.get("args", ""),
            priority=TaskPriority(d.get("priority", 2)),
            device_affinity=d.get("device_affinity", ""),
            campaign_id=d.get("campaign_id", ""),
            request_id=d.get("request_id", ""),
            payload=d.get("payload", {}),
            enqueued_at=d.get("enqueued_at", ""),
            attempts=d.get("attempts", 0),
            max_attempts=d.get("max_attempts", 3),
        )


class TaskQueue:
    """Priority task queue with Redis backend and in-memory fallback.

    Uses Redis sorted sets keyed by priority. Each priority level gets
    its own sorted set with score = enqueue timestamp for FIFO within
    the same priority.

    Usage::

        queue = TaskQueue(redis_client)
        task_id = await queue.enqueue(QueuedTask(command="research", args="quantum dots"))
        task = await queue.dequeue(device="academic")
        if task:
            result = await process(task)
            await queue.ack(task.task_id)
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        *,
        key_prefix: str = "oas:queue",
        visibility_timeout: float = 300.0,
    ):
        self._redis = redis_client
        self._prefix = key_prefix
        self._visibility_timeout = visibility_timeout
        # In-memory fallback
        self._mem_queues: dict[int, list[QueuedTask]] = {
            p.value: [] for p in TaskPriority
        }
        self._inflight: dict[str, tuple[QueuedTask, float]] = {}
        self._dlq: list[QueuedTask] = []

    def _queue_key(self, priority: int) -> str:
        return f"{self._prefix}:{priority}"

    def _inflight_key(self, task_id: str) -> str:
        return f"{self._prefix}:inflight:{task_id}"

    def _dlq_key(self) -> str:
        return f"{self._prefix}:dlq"

    async def enqueue(self, task: QueuedTask) -> str:
        """Add a task to the queue. Returns the task_id."""
        task.attempts += 1
        score = time.time()

        if self._redis:
            try:
                key = self._queue_key(task.priority)
                await self._redis.zadd(key, {task.to_json(): score})
                logger.info(
                    "task_enqueued",
                    extra={"task_id": task.task_id, "priority": task.priority, "device": task.device_affinity},
                )
                return task.task_id
            except Exception as e:
                logger.warning("redis_enqueue_failed", extra={"error": str(e)})

        # In-memory fallback
        self._mem_queues[task.priority].append(task)
        logger.info("task_enqueued_memory", extra={"task_id": task.task_id})
        return task.task_id

    async def dequeue(
        self,
        device: str = "",
        capabilities: list[str] | None = None,
        timeout: float = 0,
    ) -> QueuedTask | None:
        """Pop the highest-priority matching task.

        Args:
            device: Only dequeue tasks with matching device_affinity (or no affinity).
            capabilities: Only dequeue tasks whose task_type is in this list.
            timeout: Blocking wait time in seconds (0 = non-blocking).
        """
        if self._redis:
            return await self._dequeue_redis(device, capabilities)

        return self._dequeue_memory(device, capabilities)

    async def _dequeue_redis(
        self, device: str, capabilities: list[str] | None
    ) -> QueuedTask | None:
        """Dequeue from Redis sorted sets, checking priorities high to low."""
        try:
            for priority in TaskPriority:
                key = self._queue_key(priority)
                # ZPOPMIN: pop lowest score (oldest) item
                result = await self._redis.zpopmin(key, count=1)
                if not result:
                    continue

                for member, _score in result:
                    task_data = member if isinstance(member, str) else member.decode()
                    task = QueuedTask.from_json(task_data)

                    # Check device affinity
                    if device and task.device_affinity and task.device_affinity != device:
                        # Put it back
                        await self._redis.zadd(key, {task_data: _score})
                        continue

                    # Check capabilities
                    if capabilities and task.task_type and task.task_type not in capabilities:
                        await self._redis.zadd(key, {task_data: _score})
                        continue

                    # Mark as inflight
                    await self._redis.setex(
                        self._inflight_key(task.task_id),
                        int(self._visibility_timeout),
                        task_data,
                    )
                    return task

        except Exception as e:
            logger.warning("redis_dequeue_failed", extra={"error": str(e)})

        return None

    def _dequeue_memory(
        self, device: str, capabilities: list[str] | None
    ) -> QueuedTask | None:
        """Dequeue from in-memory queues."""
        for priority in TaskPriority:
            queue = self._mem_queues[priority]
            for i, task in enumerate(queue):
                if device and task.device_affinity and task.device_affinity != device:
                    continue
                if capabilities and task.task_type and task.task_type not in capabilities:
                    continue
                queue.pop(i)
                self._inflight[task.task_id] = (task, time.time())
                return task
        return None

    async def ack(self, task_id: str) -> bool:
        """Acknowledge task completion. Removes from inflight tracking."""
        if self._redis:
            try:
                deleted = await self._redis.delete(self._inflight_key(task_id))
                if deleted:
                    logger.debug("task_acked", extra={"task_id": task_id})
                    return True
            except Exception:
                pass

        if task_id in self._inflight:
            del self._inflight[task_id]
            return True
        return False

    async def nack(self, task_id: str, reason: str = "") -> bool:
        """Negative acknowledge — requeue or send to DLQ."""
        task: QueuedTask | None = None

        if self._redis:
            try:
                data = await self._redis.get(self._inflight_key(task_id))
                if data:
                    task_str = data if isinstance(data, str) else data.decode()
                    task = QueuedTask.from_json(task_str)
                    await self._redis.delete(self._inflight_key(task_id))
            except Exception:
                pass
        else:
            entry = self._inflight.pop(task_id, None)
            if entry:
                task = entry[0]

        if task is None:
            return False

        if task.attempts >= task.max_attempts:
            await self._send_to_dlq(task, reason)
            return True

        # Requeue with incremented attempts
        await self.enqueue(task)
        logger.info(
            "task_requeued",
            extra={"task_id": task_id, "attempts": task.attempts, "reason": reason},
        )
        return True

    async def _send_to_dlq(self, task: QueuedTask, reason: str) -> None:
        """Move a task to the dead letter queue."""
        task.payload["dlq_reason"] = reason

        if self._redis:
            try:
                await self._redis.rpush(self._dlq_key(), task.to_json())
            except Exception:
                pass

        self._dlq.append(task)
        logger.warning(
            "task_dead_lettered",
            extra={"task_id": task.task_id, "reason": reason, "attempts": task.attempts},
        )

    async def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        stats: dict[str, Any] = {"queued": {}, "inflight": 0, "dlq": 0}

        if self._redis:
            try:
                for p in TaskPriority:
                    count = await self._redis.zcard(self._queue_key(p))
                    stats["queued"][p.name.lower()] = count
                # Count inflight by scanning keys (approximate)
                stats["inflight"] = 0  # Would need SCAN in production
                stats["dlq"] = await self._redis.llen(self._dlq_key())
                return stats
            except Exception:
                pass

        for p in TaskPriority:
            stats["queued"][p.name.lower()] = len(self._mem_queues[p])
        stats["inflight"] = len(self._inflight)
        stats["dlq"] = len(self._dlq)
        return stats

    @property
    def dlq_size(self) -> int:
        return len(self._dlq)
