"""Failure isolation — containment for partial cluster outages.

Handles node failures and individual task failures with classification,
retry policies, and circuit breaker patterns to prevent cascade failures.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from oas_core.scheduler.task_queue import TaskQueue, QueuedTask
from oas_core.scheduler.heartbeat import HeartbeatService, NodeState

__all__ = ["IsolationPolicy", "FailureClass"]

logger = logging.getLogger("oas.scheduler.isolation")


class FailureClass(str, Enum):
    """Classification of task failures."""

    TRANSIENT = "transient"  # retry immediately
    RESOURCE = "resource"  # retry with backoff
    PERMANENT = "permanent"  # fail the step
    NODE_DOWN = "node_down"  # requeue to different node


@dataclass
class CircuitState:
    """Circuit breaker state for a (node, task_type) pair."""

    failures: int = 0
    last_failure: float = 0.0
    state: str = "closed"  # closed, open, half_open
    opened_at: float = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure = time.monotonic()

    def record_success(self) -> None:
        self.failures = 0
        self.state = "closed"

    def should_open(self, threshold: int = 3) -> bool:
        return self.failures >= threshold


class IsolationPolicy:
    """Failure containment and recovery for the distributed scheduler.

    Usage::

        isolation = IsolationPolicy(queue, heartbeat)

        # Handle node going offline
        actions = await isolation.on_node_failure("academic")

        # Handle task failure
        action = await isolation.on_task_failure("task_123", error="timeout")

        # Check circuit breakers
        if isolation.is_circuit_open("academic", "research"):
            # Skip this node for this task type
            ...
    """

    def __init__(
        self,
        queue: TaskQueue,
        heartbeat: HeartbeatService,
        *,
        circuit_threshold: int = 3,
        circuit_recovery_seconds: float = 60.0,
    ):
        self._queue = queue
        self._heartbeat = heartbeat
        self._circuit_threshold = circuit_threshold
        self._recovery_time = circuit_recovery_seconds
        self._circuits: dict[str, CircuitState] = {}  # "node:task_type" → state

    def classify_failure(self, error: str) -> FailureClass:
        """Classify a failure to determine retry strategy."""
        error_lower = error.lower()

        if any(kw in error_lower for kw in ("timeout", "temporary", "retry", "rate limit")):
            return FailureClass.TRANSIENT

        if any(kw in error_lower for kw in ("memory", "oom", "resource", "capacity", "quota")):
            return FailureClass.RESOURCE

        if any(kw in error_lower for kw in ("connection", "unreachable", "node", "offline")):
            return FailureClass.NODE_DOWN

        # Default to permanent for unknown errors
        return FailureClass.PERMANENT

    async def on_node_failure(self, node_id: str) -> list[dict[str, Any]]:
        """Handle a node going offline.

        Returns a list of actions taken (requeued tasks, etc.).
        """
        actions: list[dict[str, Any]] = []

        node = self._heartbeat.get_node(node_id)
        if not node:
            return actions

        # Get tasks that were on this node
        active_tasks = list(node.active_tasks)

        for task_id in active_tasks:
            # Release the lease
            self._heartbeat.release_lease(task_id)

            # Nack to requeue
            requeued = await self._queue.nack(task_id, f"node_{node_id}_offline")
            actions.append({
                "action": "requeued" if requeued else "dlq",
                "task_id": task_id,
                "reason": f"node {node_id} went offline",
            })

        logger.warning(
            "node_failure_handled",
            extra={
                "node_id": node_id,
                "tasks_affected": len(active_tasks),
                "actions": len(actions),
            },
        )

        return actions

    async def on_task_failure(
        self,
        task_id: str,
        error: str = "",
        node_id: str = "",
        task_type: str = "",
    ) -> dict[str, Any]:
        """Handle an individual task failure.

        Returns the action taken.
        """
        failure_class = self.classify_failure(error)

        # Update circuit breaker
        if node_id and task_type:
            circuit_key = f"{node_id}:{task_type}"
            circuit = self._circuits.setdefault(circuit_key, CircuitState())
            circuit.record_failure()
            if circuit.should_open(self._circuit_threshold):
                circuit.state = "open"
                circuit.opened_at = time.monotonic()
                logger.warning(
                    "circuit_opened",
                    extra={"node": node_id, "task_type": task_type, "failures": circuit.failures},
                )

        if failure_class == FailureClass.TRANSIENT:
            requeued = await self._queue.nack(task_id, "transient_error")
            action = "requeued" if requeued else "dlq"
        elif failure_class == FailureClass.RESOURCE:
            requeued = await self._queue.nack(task_id, "resource_constraint")
            action = "requeued_backoff" if requeued else "dlq"
        elif failure_class == FailureClass.NODE_DOWN:
            self._heartbeat.release_lease(task_id)
            requeued = await self._queue.nack(task_id, "node_down")
            action = "requeued_different_node" if requeued else "dlq"
        else:
            # Permanent failure — don't retry
            await self._queue.ack(task_id)
            action = "failed_permanently"

        result = {
            "action": action,
            "task_id": task_id,
            "failure_class": failure_class.value,
            "error": error[:200],
        }

        logger.info(
            "task_failure_handled",
            extra=result,
        )

        return result

    def is_circuit_open(self, node_id: str, task_type: str) -> bool:
        """Check if the circuit breaker is open for a (node, task_type) pair."""
        key = f"{node_id}:{task_type}"
        circuit = self._circuits.get(key)
        if not circuit:
            return False

        if circuit.state == "open":
            # Check if recovery time has passed
            if time.monotonic() - circuit.opened_at > self._recovery_time:
                circuit.state = "half_open"
                return False
            return True

        return False

    def record_success(self, node_id: str, task_type: str) -> None:
        """Record a successful execution, resetting the circuit breaker."""
        key = f"{node_id}:{task_type}"
        circuit = self._circuits.get(key)
        if circuit:
            circuit.record_success()

    def get_circuit_status(self) -> list[dict[str, Any]]:
        """Get status of all circuit breakers."""
        return [
            {
                "key": key,
                "state": circuit.state,
                "failures": circuit.failures,
                "age_s": round(time.monotonic() - circuit.last_failure, 1) if circuit.last_failure else 0,
            }
            for key, circuit in self._circuits.items()
        ]
