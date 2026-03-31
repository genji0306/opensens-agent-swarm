"""OAS scheduler — multi-node task distribution and health management.

Provides Redis-backed task queuing, node heartbeats, resource-aware
scheduling, capability discovery, and failure isolation for distributed
campaign execution across the DarkLab cluster.
"""

from oas_core.scheduler.task_queue import TaskQueue, TaskPriority, QueuedTask
from oas_core.scheduler.heartbeat import HeartbeatService, NodeState
from oas_core.scheduler.scheduler import Scheduler, ScheduleResult
from oas_core.scheduler.discovery import DiscoveryService, NodeCapabilities
from oas_core.scheduler.isolation import IsolationPolicy, FailureClass

__all__ = [
    "TaskQueue",
    "TaskPriority",
    "QueuedTask",
    "HeartbeatService",
    "NodeState",
    "Scheduler",
    "ScheduleResult",
    "DiscoveryService",
    "NodeCapabilities",
    "IsolationPolicy",
    "FailureClass",
]
