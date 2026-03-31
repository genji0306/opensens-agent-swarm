"""Tests for the failure isolation policy."""

import time
import pytest

from oas_core.scheduler.isolation import IsolationPolicy, FailureClass
from oas_core.scheduler.task_queue import TaskQueue, QueuedTask
from oas_core.scheduler.heartbeat import HeartbeatService, NodeState


@pytest.fixture
def setup():
    queue = TaskQueue()
    hb = HeartbeatService()
    hb.register("academic", capabilities=["research"])
    hb.register("experiment", capabilities=["simulate"])
    isolation = IsolationPolicy(queue, hb, circuit_threshold=2, circuit_recovery_seconds=0.1)
    return isolation, queue, hb


class TestFailureClassification:
    def test_classify_transient(self, setup):
        isolation, _, _ = setup
        assert isolation.classify_failure("Connection timeout") == FailureClass.TRANSIENT
        assert isolation.classify_failure("rate limit exceeded") == FailureClass.TRANSIENT

    def test_classify_resource(self, setup):
        isolation, _, _ = setup
        assert isolation.classify_failure("Out of memory (OOM)") == FailureClass.RESOURCE
        assert isolation.classify_failure("quota exceeded") == FailureClass.RESOURCE

    def test_classify_node_down(self, setup):
        isolation, _, _ = setup
        assert isolation.classify_failure("node unreachable") == FailureClass.NODE_DOWN
        assert isolation.classify_failure("connection refused") == FailureClass.NODE_DOWN

    def test_classify_permanent(self, setup):
        isolation, _, _ = setup
        assert isolation.classify_failure("invalid argument") == FailureClass.PERMANENT


class TestNodeFailure:
    @pytest.mark.asyncio
    async def test_on_node_failure_requeues_tasks(self, setup):
        isolation, queue, hb = setup
        # Add a task to the node
        task = QueuedTask(command="research", task_type="research")
        await queue.enqueue(task)
        dequeued = await queue.dequeue(device="academic")
        assert dequeued is not None
        hb.lease("academic", dequeued.task_id)

        actions = await isolation.on_node_failure("academic")
        assert len(actions) == 1
        assert actions[0]["action"] in ("requeued", "dlq")


class TestTaskFailure:
    @pytest.mark.asyncio
    async def test_transient_failure_requeues(self, setup):
        isolation, queue, hb = setup
        task = QueuedTask(command="test", max_attempts=3)
        await queue.enqueue(task)
        dequeued = await queue.dequeue()
        assert dequeued is not None

        result = await isolation.on_task_failure(
            dequeued.task_id, error="timeout", node_id="academic", task_type="research"
        )
        assert result["failure_class"] == "transient"

    @pytest.mark.asyncio
    async def test_permanent_failure_no_retry(self, setup):
        isolation, queue, hb = setup
        task = QueuedTask(command="test")
        await queue.enqueue(task)
        dequeued = await queue.dequeue()
        assert dequeued is not None

        result = await isolation.on_task_failure(dequeued.task_id, error="invalid input")
        assert result["action"] == "failed_permanently"


class TestCircuitBreaker:
    def test_circuit_opens_after_threshold(self, setup):
        isolation, _, _ = setup

        # Record failures
        for _ in range(2):
            isolation._circuits.setdefault("academic:research", __import__(
                "oas_core.scheduler.isolation", fromlist=["CircuitState"]
            ).CircuitState()).record_failure()

        # Manually set to open
        circuit = isolation._circuits["academic:research"]
        if circuit.should_open(2):
            circuit.state = "open"
            circuit.opened_at = time.monotonic()

        assert isolation.is_circuit_open("academic", "research") is True

    def test_circuit_recovers(self, setup):
        isolation, _, _ = setup

        from oas_core.scheduler.isolation import CircuitState
        circuit = CircuitState(failures=3, state="open", opened_at=time.monotonic() - 1.0)
        isolation._circuits["academic:research"] = circuit

        # Recovery time is 0.1s, 1.0s has passed
        assert isolation.is_circuit_open("academic", "research") is False

    def test_record_success_resets(self, setup):
        isolation, _, _ = setup

        from oas_core.scheduler.isolation import CircuitState
        circuit = CircuitState(failures=5, state="half_open")
        isolation._circuits["academic:research"] = circuit

        isolation.record_success("academic", "research")
        assert circuit.failures == 0
        assert circuit.state == "closed"

    def test_get_circuit_status(self, setup):
        isolation, _, _ = setup
        from oas_core.scheduler.isolation import CircuitState
        isolation._circuits["test:cmd"] = CircuitState(failures=2, state="closed")

        status = isolation.get_circuit_status()
        assert len(status) == 1
        assert status[0]["key"] == "test:cmd"
