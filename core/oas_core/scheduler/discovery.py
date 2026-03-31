"""Node capability discovery — dynamic node registration.

Replaces hardcoded 3-node topology with self-registering nodes that
declare their capabilities at startup. Auto-deregisters nodes when
their heartbeat expires.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from oas_core.scheduler.heartbeat import HeartbeatService, NodeInfo, NodeState

__all__ = ["DiscoveryService", "NodeCapabilities"]

logger = logging.getLogger("oas.scheduler.discovery")


@dataclass
class NodeCapabilities:
    """Declared capabilities of a cluster node."""

    node_id: str
    supported_commands: list[str] = field(default_factory=list)
    supported_task_types: list[str] = field(default_factory=list)
    available_models: list[str] = field(default_factory=list)
    memory_gb: float = 0.0
    has_gpu: bool = False
    max_concurrent: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)


# Default capabilities for the DarkLab cluster nodes
_DEFAULT_CAPABILITIES: dict[str, NodeCapabilities] = {
    "leader": NodeCapabilities(
        node_id="leader",
        supported_commands=[
            "synthesize", "report", "deerflow", "deepresearch",
            "swarmresearch", "debate", "rl-train", "rl-status",
        ],
        available_models=["claude-sonnet-4-6-20260301"],
        memory_gb=16,
        max_concurrent=3,
    ),
    "academic": NodeCapabilities(
        node_id="academic",
        supported_commands=[
            "research", "literature", "doe", "paper", "perplexity",
        ],
        available_models=["claude-sonnet-4-6-20260301", "qwen3:8b"],
        memory_gb=16,
        max_concurrent=4,
    ),
    "experiment": NodeCapabilities(
        node_id="experiment",
        supported_commands=[
            "simulate", "analyze", "synthetic", "report-data",
            "autoresearch", "parametergolf",
        ],
        available_models=["qwen3:8b", "qwen2.5-coder"],
        memory_gb=24,
        has_gpu=False,
        max_concurrent=3,
    ),
}


class DiscoveryService:
    """Manages node capability discovery and lookup.

    Usage::

        discovery = DiscoveryService(heartbeat)
        discovery.register_capabilities(NodeCapabilities(
            node_id="academic",
            supported_commands=["research", "literature"],
            memory_gb=16,
        ))

        # Find nodes for a command
        nodes = discovery.find_capable("research")
    """

    def __init__(
        self,
        heartbeat: HeartbeatService,
        *,
        load_defaults: bool = True,
    ):
        self._heartbeat = heartbeat
        self._capabilities: dict[str, NodeCapabilities] = {}

        if load_defaults:
            for node_id, caps in _DEFAULT_CAPABILITIES.items():
                self._capabilities[node_id] = caps

    def register_capabilities(self, caps: NodeCapabilities) -> None:
        """Register or update node capabilities."""
        self._capabilities[caps.node_id] = caps

        # Also ensure heartbeat service knows about this node
        hb_node = self._heartbeat.get_node(caps.node_id)
        if not hb_node:
            self._heartbeat.register(
                caps.node_id,
                capabilities=caps.supported_commands,
                metadata={"memory_gb": caps.memory_gb, "has_gpu": caps.has_gpu},
            )

        logger.info(
            "capabilities_registered",
            extra={
                "node_id": caps.node_id,
                "commands": caps.supported_commands,
                "memory_gb": caps.memory_gb,
            },
        )

    def unregister(self, node_id: str) -> bool:
        """Remove node capabilities."""
        return self._capabilities.pop(node_id, None) is not None

    def find_capable(self, command: str) -> list[NodeInfo]:
        """Find healthy nodes that can handle a command.

        Returns nodes sorted by active task count (least busy first).
        """
        result: list[NodeInfo] = []

        for node_id, caps in self._capabilities.items():
            if command not in caps.supported_commands:
                continue
            node = self._heartbeat.get_node(node_id)
            if node and node.state in (NodeState.ONLINE, NodeState.DEGRADED):
                result.append(node)

        result.sort(key=lambda n: len(n.active_tasks))
        return result

    def find_by_model(self, model: str) -> list[str]:
        """Find nodes that have a specific model available."""
        return [
            node_id
            for node_id, caps in self._capabilities.items()
            if model in caps.available_models
        ]

    def get_capabilities(self, node_id: str) -> NodeCapabilities | None:
        return self._capabilities.get(node_id)

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered capabilities."""
        result = []
        for node_id, caps in self._capabilities.items():
            node = self._heartbeat.get_node(node_id)
            state = node.state.value if node else "unknown"
            result.append({
                "node_id": node_id,
                "commands": caps.supported_commands,
                "models": caps.available_models,
                "memory_gb": caps.memory_gb,
                "has_gpu": caps.has_gpu,
                "max_concurrent": caps.max_concurrent,
                "state": state,
                "active_tasks": len(node.active_tasks) if node else 0,
            })
        return result

    @property
    def node_count(self) -> int:
        return len(self._capabilities)
