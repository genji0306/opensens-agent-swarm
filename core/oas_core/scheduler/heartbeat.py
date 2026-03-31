"""Node health heartbeat and lease model.

Each cluster node registers itself on startup and sends periodic
heartbeats. The service tracks node state transitions (online →
degraded → offline) and manages task leases.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

__all__ = ["HeartbeatService", "NodeState", "NodeInfo"]

logger = logging.getLogger("oas.scheduler.heartbeat")


class NodeState(str, Enum):
    ONLINE = "online"
    DEGRADED = "degraded"  # missed 1 heartbeat
    OFFLINE = "offline"  # missed 3+ heartbeats
    UNKNOWN = "unknown"


@dataclass
class NodeInfo:
    """Registered node with health tracking."""

    node_id: str
    address: str = ""
    capabilities: list[str] = field(default_factory=list)
    state: NodeState = NodeState.UNKNOWN
    registered_at: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)
    active_tasks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "address": self.address,
            "capabilities": self.capabilities,
            "state": self.state.value,
            "active_tasks": self.active_tasks,
            "last_heartbeat_age_s": round(time.monotonic() - self.last_heartbeat, 1),
            "metadata": self.metadata,
        }


@dataclass
class TaskLease:
    """A lease on a task claimed by a node."""

    task_id: str
    node_id: str
    granted_at: float = field(default_factory=time.monotonic)
    duration: float = 300.0  # seconds

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.granted_at > self.duration


class HeartbeatService:
    """Tracks node health via periodic heartbeats.

    Usage::

        hb = HeartbeatService()
        hb.register("leader", capabilities=["research", "synthesize"], address="192.168.23.25:8100")
        hb.heartbeat("leader")

        # Periodic check
        hb.check_health()
        healthy = hb.get_healthy_nodes()

        # Task leasing
        hb.lease("leader", "task_123", duration=120.0)
    """

    def __init__(
        self,
        *,
        heartbeat_interval: float = 10.0,
        degraded_after: int = 1,  # missed heartbeats before degraded
        offline_after: int = 3,  # missed heartbeats before offline
    ):
        self._interval = heartbeat_interval
        self._degraded_threshold = degraded_after
        self._offline_threshold = offline_after
        self._nodes: dict[str, NodeInfo] = {}
        self._leases: dict[str, TaskLease] = {}  # task_id → lease

    def register(
        self,
        node_id: str,
        capabilities: list[str] | None = None,
        address: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> NodeInfo:
        """Register a node. If already registered, updates capabilities."""
        now = time.monotonic()
        if node_id in self._nodes:
            node = self._nodes[node_id]
            if capabilities is not None:
                node.capabilities = capabilities
            node.address = address or node.address
            node.state = NodeState.ONLINE
            node.last_heartbeat = now
            if metadata:
                node.metadata.update(metadata)
        else:
            node = NodeInfo(
                node_id=node_id,
                address=address,
                capabilities=capabilities or [],
                state=NodeState.ONLINE,
                registered_at=now,
                last_heartbeat=now,
                metadata=metadata or {},
            )
            self._nodes[node_id] = node

        logger.info(
            "node_registered",
            extra={"node_id": node_id, "capabilities": node.capabilities},
        )
        return node

    def unregister(self, node_id: str) -> bool:
        """Remove a node from tracking."""
        node = self._nodes.pop(node_id, None)
        if node:
            # Release any leases held by this node
            for task_id in list(self._leases):
                if self._leases[task_id].node_id == node_id:
                    del self._leases[task_id]
            logger.info("node_unregistered", extra={"node_id": node_id})
            return True
        return False

    def heartbeat(self, node_id: str) -> bool:
        """Record a heartbeat from a node. Returns False if node unknown."""
        node = self._nodes.get(node_id)
        if not node:
            return False
        node.last_heartbeat = time.monotonic()
        if node.state != NodeState.ONLINE:
            logger.info(
                "node_recovered",
                extra={"node_id": node_id, "from_state": node.state.value},
            )
            node.state = NodeState.ONLINE
        return True

    def check_health(self) -> dict[str, NodeState]:
        """Check all nodes and update state based on heartbeat freshness.

        Returns a dict of node_id → current state.
        """
        now = time.monotonic()
        results: dict[str, NodeState] = {}

        for node_id, node in self._nodes.items():
            elapsed = now - node.last_heartbeat
            missed = int(elapsed / self._interval)
            old_state = node.state

            if missed >= self._offline_threshold:
                node.state = NodeState.OFFLINE
            elif missed >= self._degraded_threshold:
                node.state = NodeState.DEGRADED
            else:
                node.state = NodeState.ONLINE

            if node.state != old_state:
                logger.info(
                    "node_state_changed",
                    extra={
                        "node_id": node_id,
                        "from": old_state.value,
                        "to": node.state.value,
                        "missed_heartbeats": missed,
                    },
                )

            results[node_id] = node.state

        return results

    def get_healthy_nodes(self) -> list[NodeInfo]:
        """Get all nodes in ONLINE or DEGRADED state."""
        return [
            n for n in self._nodes.values()
            if n.state in (NodeState.ONLINE, NodeState.DEGRADED)
        ]

    def get_node(self, node_id: str) -> NodeInfo | None:
        return self._nodes.get(node_id)

    def lease(self, node_id: str, task_id: str, duration: float = 300.0) -> bool:
        """Grant a task lease to a node. Returns False if node not healthy."""
        node = self._nodes.get(node_id)
        if not node or node.state == NodeState.OFFLINE:
            return False

        self._leases[task_id] = TaskLease(
            task_id=task_id,
            node_id=node_id,
            duration=duration,
        )
        if task_id not in node.active_tasks:
            node.active_tasks.append(task_id)
        return True

    def release_lease(self, task_id: str) -> bool:
        """Release a task lease."""
        lease = self._leases.pop(task_id, None)
        if lease:
            node = self._nodes.get(lease.node_id)
            if node and task_id in node.active_tasks:
                node.active_tasks.remove(task_id)
            return True
        return False

    def get_expired_leases(self) -> list[TaskLease]:
        """Find all leases that have expired."""
        return [l for l in self._leases.values() if l.expired]

    def list_nodes(self) -> list[dict[str, Any]]:
        """List all nodes with current state."""
        return [n.to_dict() for n in self._nodes.values()]

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def online_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.state == NodeState.ONLINE)
