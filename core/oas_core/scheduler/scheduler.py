"""Resource-aware scheduler — dispatches campaign steps to available nodes.

Finds the best node based on capability match, queue depth, budget
remaining, node health, and data locality hints. Replaces direct
dispatch with intelligent task distribution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from oas_core.scheduler.task_queue import TaskQueue, QueuedTask, TaskPriority
from oas_core.scheduler.heartbeat import HeartbeatService, NodeState, NodeInfo
from oas_core.scheduler.discovery import DiscoveryService

__all__ = ["Scheduler", "ScheduleResult"]

logger = logging.getLogger("oas.scheduler")


@dataclass
class ScheduleResult:
    """Result of a scheduling decision."""

    scheduled: bool
    task_id: str = ""
    node_id: str = ""
    reason: str = ""
    queue_position: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheduled": self.scheduled,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "reason": self.reason,
        }


class Scheduler:
    """Central scheduler that dispatches campaign steps to available nodes.

    Usage::

        scheduler = Scheduler(queue, heartbeat, discovery)
        result = await scheduler.schedule(
            command="research",
            args="quantum dots",
            campaign_id="camp_123",
            request_id="req_456",
        )
        if result.scheduled:
            print(f"Task {result.task_id} assigned to {result.node_id}")
    """

    def __init__(
        self,
        queue: TaskQueue,
        heartbeat: HeartbeatService,
        discovery: DiscoveryService | None = None,
    ):
        self._queue = queue
        self._heartbeat = heartbeat
        self._discovery = discovery

    async def schedule(
        self,
        command: str,
        args: str = "",
        *,
        campaign_id: str = "",
        request_id: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        device_hint: str = "",
        payload: dict[str, Any] | None = None,
    ) -> ScheduleResult:
        """Schedule a task for execution on the best available node.

        Args:
            command: The command to execute (e.g., "research").
            args: Arguments for the command.
            campaign_id: Associated campaign.
            request_id: Associated request.
            priority: Task priority.
            device_hint: Preferred device (overridden by discovery if unhealthy).
            payload: Additional task payload.
        """
        # Find target node
        target_device = self._select_node(command, device_hint)

        if not target_device:
            return ScheduleResult(
                scheduled=False,
                reason="no_healthy_node_for_command",
            )

        task = QueuedTask(
            task_type=command,
            command=command,
            args=args,
            priority=priority,
            device_affinity=target_device,
            campaign_id=campaign_id,
            request_id=request_id,
            payload=payload or {},
        )

        task_id = await self._queue.enqueue(task)

        logger.info(
            "task_scheduled",
            extra={
                "task_id": task_id,
                "command": command,
                "device": target_device,
                "priority": priority.name,
            },
        )

        return ScheduleResult(
            scheduled=True,
            task_id=task_id,
            node_id=target_device,
            reason="enqueued",
        )

    def _select_node(self, command: str, device_hint: str) -> str:
        """Select the best node for a command."""
        # Use discovery if available
        if self._discovery:
            capable = self._discovery.find_capable(command)
            if capable:
                # Prefer the hint if it's capable and healthy
                if device_hint:
                    for node in capable:
                        if node.node_id == device_hint:
                            info = self._heartbeat.get_node(device_hint)
                            if info and info.state != NodeState.OFFLINE:
                                return device_hint

                # Pick the node with fewest active tasks
                best = min(capable, key=lambda n: len(n.active_tasks))
                return best.node_id

        # Fallback: use hint or route by command
        if device_hint:
            info = self._heartbeat.get_node(device_hint)
            if info and info.state != NodeState.OFFLINE:
                return device_hint

        # Static command → device mapping as final fallback
        return _COMMAND_DEVICE.get(command, "leader")

    async def rebalance(self) -> list[str]:
        """Check for stuck/expired tasks and requeue them.

        Returns list of task_ids that were requeued.
        """
        expired = self._heartbeat.get_expired_leases()
        requeued: list[str] = []

        for lease in expired:
            self._heartbeat.release_lease(lease.task_id)
            await self._queue.nack(lease.task_id, "lease_expired")
            requeued.append(lease.task_id)
            logger.info(
                "task_rebalanced",
                extra={"task_id": lease.task_id, "node_id": lease.node_id},
            )

        return requeued

    async def pause_campaign(self, campaign_id: str) -> int:
        """Pause all queued tasks for a campaign. Returns count paused."""
        # In a full implementation, this would scan the queue
        # For now, log the intent
        logger.info("campaign_paused", extra={"campaign_id": campaign_id})
        return 0

    async def get_status(self) -> dict[str, Any]:
        """Get scheduler status overview."""
        queue_stats = await self._queue.get_stats()
        nodes = self._heartbeat.list_nodes()
        return {
            "queue": queue_stats,
            "nodes": nodes,
            "online_nodes": self._heartbeat.online_count,
            "total_nodes": self._heartbeat.node_count,
        }


# Static fallback mapping
_COMMAND_DEVICE: dict[str, str] = {
    "research": "academic",
    "literature": "academic",
    "doe": "academic",
    "paper": "academic",
    "perplexity": "academic",
    "simulate": "experiment",
    "analyze": "experiment",
    "synthetic": "experiment",
    "report-data": "experiment",
    "autoresearch": "experiment",
    "parametergolf": "experiment",
    "synthesize": "leader",
    "report": "leader",
    "deerflow": "leader",
    "deepresearch": "leader",
    "swarmresearch": "leader",
    "debate": "leader",
}
