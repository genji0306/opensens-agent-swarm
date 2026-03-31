"""Tests for the Redis-backed task queue."""

import pytest

from oas_core.scheduler.task_queue import TaskQueue, QueuedTask, TaskPriority


@pytest.fixture
def queue():
    """In-memory task queue (no Redis)."""
    return TaskQueue()


class TestQueuedTask:
    def test_json_roundtrip(self):
        task = QueuedTask(command="research", args="quantum dots", priority=TaskPriority.HIGH)
        json_str = task.to_json()
        restored = QueuedTask.from_json(json_str)
        assert restored.command == "research"
        assert restored.args == "quantum dots"
        assert restored.priority == TaskPriority.HIGH

    def test_default_fields(self):
        task = QueuedTask()
        assert task.task_id != ""
        assert task.priority == TaskPriority.NORMAL
        assert task.attempts == 0


class TestTaskQueue:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, queue):
        task = QueuedTask(command="research", args="test")
        await queue.enqueue(task)

        result = await queue.dequeue()
        assert result is not None
        assert result.command == "research"

    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue):
        await queue.enqueue(QueuedTask(command="low", priority=TaskPriority.LOW))
        await queue.enqueue(QueuedTask(command="critical", priority=TaskPriority.CRITICAL))
        await queue.enqueue(QueuedTask(command="normal", priority=TaskPriority.NORMAL))

        t1 = await queue.dequeue()
        assert t1 is not None
        assert t1.command == "critical"

        t2 = await queue.dequeue()
        assert t2 is not None
        assert t2.command == "normal"

    @pytest.mark.asyncio
    async def test_device_affinity_filter(self, queue):
        await queue.enqueue(QueuedTask(command="research", device_affinity="academic"))
        await queue.enqueue(QueuedTask(command="simulate", device_affinity="experiment"))

        result = await queue.dequeue(device="experiment")
        assert result is not None
        assert result.command == "simulate"

    @pytest.mark.asyncio
    async def test_ack_removes_inflight(self, queue):
        task = QueuedTask(command="test")
        await queue.enqueue(task)
        dequeued = await queue.dequeue()
        assert dequeued is not None

        ok = await queue.ack(dequeued.task_id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_nack_requeues(self, queue):
        task = QueuedTask(command="test", max_attempts=3)
        await queue.enqueue(task)
        dequeued = await queue.dequeue()
        assert dequeued is not None

        await queue.nack(dequeued.task_id, "transient")

        requeued = await queue.dequeue()
        assert requeued is not None
        assert requeued.command == "test"

    @pytest.mark.asyncio
    async def test_nack_sends_to_dlq_after_max_attempts(self, queue):
        task = QueuedTask(command="failing", max_attempts=1, attempts=0)
        await queue.enqueue(task)
        dequeued = await queue.dequeue()
        assert dequeued is not None

        await queue.nack(dequeued.task_id, "permanent")
        assert queue.dlq_size == 1

    @pytest.mark.asyncio
    async def test_empty_dequeue_returns_none(self, queue):
        result = await queue.dequeue()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_stats(self, queue):
        await queue.enqueue(QueuedTask(command="a", priority=TaskPriority.HIGH))
        await queue.enqueue(QueuedTask(command="b", priority=TaskPriority.NORMAL))

        stats = await queue.get_stats()
        assert stats["queued"]["high"] == 1
        assert stats["queued"]["normal"] == 1
        assert stats["dlq"] == 0

    @pytest.mark.asyncio
    async def test_capability_filter(self, queue):
        await queue.enqueue(QueuedTask(command="research", task_type="research"))
        await queue.enqueue(QueuedTask(command="simulate", task_type="simulate"))

        result = await queue.dequeue(capabilities=["simulate"])
        assert result is not None
        assert result.task_type == "simulate"
