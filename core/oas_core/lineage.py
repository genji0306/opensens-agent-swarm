"""Artifact lineage graph — queryable provenance connecting campaigns to outputs.

Builds an in-memory directed graph from campaign journal entries, linking
campaigns → steps → artifacts → approvals → cost events. Supports
ancestor/descendant queries and export to DOT and JSON formats.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "LineageGraph",
    "LineageNode",
    "LineageEdge",
    "NodeType",
    "EdgeType",
]

logger = logging.getLogger("oas.lineage")


class NodeType(str, Enum):
    CAMPAIGN = "campaign"
    STEP = "step"
    ARTIFACT = "artifact"
    APPROVAL = "approval"
    COST_EVENT = "cost_event"


class EdgeType(str, Enum):
    PRODUCED_BY = "produced_by"
    DEPENDS_ON = "depends_on"
    APPROVED_BY = "approved_by"
    DERIVED_FROM = "derived_from"
    COST_OF = "cost_of"


@dataclass
class LineageNode:
    """A node in the lineage graph."""

    node_id: str
    node_type: NodeType
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageEdge:
    """A directed edge in the lineage graph."""

    source: str  # node_id
    target: str  # node_id
    edge_type: EdgeType
    metadata: dict[str, Any] = field(default_factory=dict)


class LineageGraph:
    """In-memory directed graph for artifact provenance.

    Usage::

        graph = LineageGraph()
        graph.add_node(LineageNode("camp_1", NodeType.CAMPAIGN, "EIT Study"))
        graph.add_node(LineageNode("step_1", NodeType.STEP, "Research"))
        graph.add_edge(LineageEdge("step_1", "camp_1", EdgeType.PRODUCED_BY))

        # Query
        ancestors = graph.ancestors("step_1")
        descendants = graph.descendants("camp_1")

        # Export
        dot_str = graph.to_dot()
    """

    def __init__(self) -> None:
        self._nodes: dict[str, LineageNode] = {}
        self._edges: list[LineageEdge] = []
        # Adjacency lists
        self._forward: dict[str, list[str]] = {}  # source → targets
        self._backward: dict[str, list[str]] = {}  # target → sources

    def add_node(self, node: LineageNode) -> None:
        self._nodes[node.node_id] = node
        if node.node_id not in self._forward:
            self._forward[node.node_id] = []
        if node.node_id not in self._backward:
            self._backward[node.node_id] = []

    def add_edge(self, edge: LineageEdge) -> None:
        self._edges.append(edge)
        if edge.source not in self._forward:
            self._forward[edge.source] = []
        if edge.target not in self._backward:
            self._backward[edge.target] = []
        self._forward[edge.source].append(edge.target)
        self._backward[edge.target].append(edge.source)

    def get_node(self, node_id: str) -> LineageNode | None:
        return self._nodes.get(node_id)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def ancestors(self, node_id: str) -> list[LineageNode]:
        """All nodes reachable by following edges backward."""
        visited: set[str] = set()
        result: list[LineageNode] = []
        self._traverse_backward(node_id, visited, result)
        return result

    def descendants(self, node_id: str) -> list[LineageNode]:
        """All nodes reachable by following edges forward."""
        visited: set[str] = set()
        result: list[LineageNode] = []
        self._traverse_forward(node_id, visited, result)
        return result

    def _traverse_backward(
        self, node_id: str, visited: set[str], result: list[LineageNode]
    ) -> None:
        for parent_id in self._backward.get(node_id, []):
            if parent_id not in visited:
                visited.add(parent_id)
                node = self._nodes.get(parent_id)
                if node:
                    result.append(node)
                self._traverse_backward(parent_id, visited, result)

    def _traverse_forward(
        self, node_id: str, visited: set[str], result: list[LineageNode]
    ) -> None:
        for child_id in self._forward.get(node_id, []):
            if child_id not in visited:
                visited.add(child_id)
                node = self._nodes.get(child_id)
                if node:
                    result.append(node)
                self._traverse_forward(child_id, visited, result)

    def path(self, from_id: str, to_id: str) -> list[str] | None:
        """Find a path from source to target (BFS). Returns node IDs or None."""
        if from_id == to_id:
            return [from_id]

        from collections import deque

        queue: deque[list[str]] = deque([[from_id]])
        visited: set[str] = {from_id}

        while queue:
            current_path = queue.popleft()
            current = current_path[-1]

            for neighbor in self._forward.get(current, []):
                if neighbor == to_id:
                    return current_path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(current_path + [neighbor])

        return None

    def nodes_by_type(self, node_type: NodeType) -> list[LineageNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def edges_by_type(self, edge_type: EdgeType) -> list[LineageEdge]:
        return [e for e in self._edges if e.edge_type == edge_type]

    def build_from_journal(self, entries: list[dict[str, Any]]) -> None:
        """Populate the graph from campaign journal entries.

        Expects journal entries with event_type and payload fields.
        """
        for entry in entries:
            event_type = entry.get("event_type", "")
            payload = entry.get("payload", {})
            campaign_id = entry.get("campaign_id", "")
            actor = entry.get("actor", "")

            if event_type == "campaign.started":
                self.add_node(LineageNode(
                    node_id=campaign_id,
                    node_type=NodeType.CAMPAIGN,
                    label=payload.get("title", campaign_id),
                    metadata={"actor": actor, "objective": payload.get("objective", "")},
                ))

            elif event_type == "step.started":
                step_id = f"{campaign_id}:step_{payload.get('step', 0)}"
                self.add_node(LineageNode(
                    node_id=step_id,
                    node_type=NodeType.STEP,
                    label=payload.get("command", ""),
                    metadata=payload,
                ))
                self.add_edge(LineageEdge(
                    source=step_id,
                    target=campaign_id,
                    edge_type=EdgeType.PRODUCED_BY,
                ))

            elif event_type == "step.completed":
                step_id = f"{campaign_id}:step_{payload.get('step', 0)}"
                # Add dependencies
                for dep in payload.get("depends_on", []):
                    dep_id = f"{campaign_id}:step_{dep}"
                    self.add_edge(LineageEdge(
                        source=step_id,
                        target=dep_id,
                        edge_type=EdgeType.DEPENDS_ON,
                    ))

            elif event_type == "artifact.created":
                artifact_id = payload.get("artifact_id", "")
                if artifact_id:
                    self.add_node(LineageNode(
                        node_id=artifact_id,
                        node_type=NodeType.ARTIFACT,
                        label=payload.get("evidence_type", "artifact"),
                        metadata=payload,
                    ))
                    # Link to producing step or campaign
                    source_step = payload.get("step_id")
                    if source_step:
                        step_node_id = f"{campaign_id}:step_{source_step}"
                        self.add_edge(LineageEdge(
                            source=artifact_id,
                            target=step_node_id,
                            edge_type=EdgeType.PRODUCED_BY,
                        ))

            elif event_type == "approval.recorded":
                approval_id = payload.get("approval_id", "")
                if approval_id:
                    self.add_node(LineageNode(
                        node_id=approval_id,
                        node_type=NodeType.APPROVAL,
                        label=f"Approval by {actor}",
                        metadata=payload,
                    ))
                    self.add_edge(LineageEdge(
                        source=campaign_id,
                        target=approval_id,
                        edge_type=EdgeType.APPROVED_BY,
                    ))

            elif event_type == "cost.recorded":
                cost_id = payload.get("cost_id", entry.get("hash", "")[:16])
                if cost_id:
                    self.add_node(LineageNode(
                        node_id=cost_id,
                        node_type=NodeType.COST_EVENT,
                        label=f"${payload.get('cost_usd', 0):.3f}",
                        metadata=payload,
                    ))
                    step_num = payload.get("step_id")
                    if step_num is not None:
                        step_node_id = f"{campaign_id}:step_{step_num}"
                        self.add_edge(LineageEdge(
                            source=cost_id,
                            target=step_node_id,
                            edge_type=EdgeType.COST_OF,
                        ))

    def to_dot(self) -> str:
        """Export as Graphviz DOT format."""
        lines = ["digraph lineage {", "  rankdir=LR;"]

        type_shapes = {
            NodeType.CAMPAIGN: "doubleoctagon",
            NodeType.STEP: "box",
            NodeType.ARTIFACT: "ellipse",
            NodeType.APPROVAL: "diamond",
            NodeType.COST_EVENT: "note",
        }

        for node in self._nodes.values():
            shape = type_shapes.get(node.node_type, "ellipse")
            label = node.label or node.node_id
            lines.append(f'  "{node.node_id}" [label="{label}" shape={shape}];')

        for edge in self._edges:
            lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{edge.edge_type.value}"];')

        lines.append("}")
        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Export as JSON-serializable dict."""
        return {
            "nodes": [
                {
                    "id": n.node_id,
                    "type": n.node_type.value,
                    "label": n.label,
                    "metadata": n.metadata,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "type": e.edge_type.value,
                    "metadata": e.metadata,
                }
                for e in self._edges
            ],
        }
