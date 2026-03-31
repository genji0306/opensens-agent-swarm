"""Tests for the artifact lineage graph."""

import pytest

from oas_core.lineage import (
    LineageGraph,
    LineageNode,
    LineageEdge,
    NodeType,
    EdgeType,
)


class TestLineageGraph:
    def test_add_nodes_and_edges(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("c1", NodeType.CAMPAIGN, "Campaign 1"))
        graph.add_node(LineageNode("s1", NodeType.STEP, "Research"))
        graph.add_edge(LineageEdge("s1", "c1", EdgeType.PRODUCED_BY))

        assert graph.node_count == 2
        assert graph.edge_count == 1

    def test_ancestors(self):
        """Ancestors follow backward edges: if edge(s1→a1) exists, s1 is ancestor of a1."""
        graph = LineageGraph()
        graph.add_node(LineageNode("c1", NodeType.CAMPAIGN))
        graph.add_node(LineageNode("s1", NodeType.STEP))
        graph.add_node(LineageNode("a1", NodeType.ARTIFACT))
        # c1 → s1 → a1 (forward direction)
        graph.add_edge(LineageEdge("c1", "s1", EdgeType.PRODUCED_BY))
        graph.add_edge(LineageEdge("s1", "a1", EdgeType.PRODUCED_BY))

        ancestors = graph.ancestors("a1")
        assert len(ancestors) == 2
        ancestor_ids = {n.node_id for n in ancestors}
        assert "s1" in ancestor_ids
        assert "c1" in ancestor_ids

    def test_descendants(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("c1", NodeType.CAMPAIGN))
        graph.add_node(LineageNode("s1", NodeType.STEP))
        graph.add_node(LineageNode("s2", NodeType.STEP))
        graph.add_edge(LineageEdge("c1", "s1", EdgeType.PRODUCED_BY))
        graph.add_edge(LineageEdge("c1", "s2", EdgeType.PRODUCED_BY))

        descendants = graph.descendants("c1")
        assert len(descendants) == 2

    def test_path(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("a", NodeType.CAMPAIGN))
        graph.add_node(LineageNode("b", NodeType.STEP))
        graph.add_node(LineageNode("c", NodeType.ARTIFACT))
        graph.add_edge(LineageEdge("a", "b", EdgeType.PRODUCED_BY))
        graph.add_edge(LineageEdge("b", "c", EdgeType.DEPENDS_ON))

        p = graph.path("a", "c")
        assert p == ["a", "b", "c"]

    def test_path_not_found(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("a", NodeType.CAMPAIGN))
        graph.add_node(LineageNode("b", NodeType.STEP))
        # No edge
        assert graph.path("a", "b") is None

    def test_path_same_node(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("a", NodeType.CAMPAIGN))
        assert graph.path("a", "a") == ["a"]

    def test_nodes_by_type(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("c1", NodeType.CAMPAIGN))
        graph.add_node(LineageNode("s1", NodeType.STEP))
        graph.add_node(LineageNode("s2", NodeType.STEP))

        steps = graph.nodes_by_type(NodeType.STEP)
        assert len(steps) == 2

    def test_edges_by_type(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("a", NodeType.CAMPAIGN))
        graph.add_node(LineageNode("b", NodeType.STEP))
        graph.add_edge(LineageEdge("a", "b", EdgeType.PRODUCED_BY))
        graph.add_edge(LineageEdge("a", "b", EdgeType.DEPENDS_ON))

        produced = graph.edges_by_type(EdgeType.PRODUCED_BY)
        assert len(produced) == 1

    def test_build_from_journal(self):
        graph = LineageGraph()
        journal_entries = [
            {"campaign_id": "c1", "event_type": "campaign.started", "payload": {"title": "Test"}, "actor": "leader"},
            {"campaign_id": "c1", "event_type": "step.started", "payload": {"step": 1, "command": "research"}, "actor": "academic"},
            {"campaign_id": "c1", "event_type": "step.completed", "payload": {"step": 1, "depends_on": []}, "actor": "academic"},
            {"campaign_id": "c1", "event_type": "artifact.created", "payload": {"artifact_id": "ka-abc", "evidence_type": "literature", "step_id": 1}, "actor": "academic"},
            {"campaign_id": "c1", "event_type": "cost.recorded", "payload": {"cost_id": "cost_1", "cost_usd": 0.05, "step_id": 1}, "hash": "abc123def456"},
        ]
        graph.build_from_journal(journal_entries)

        assert graph.node_count >= 3  # campaign + step + artifact
        campaigns = graph.nodes_by_type(NodeType.CAMPAIGN)
        assert len(campaigns) == 1

    def test_to_dot(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("c1", NodeType.CAMPAIGN, "Campaign"))
        graph.add_node(LineageNode("s1", NodeType.STEP, "Research"))
        graph.add_edge(LineageEdge("s1", "c1", EdgeType.PRODUCED_BY))

        dot = graph.to_dot()
        assert "digraph lineage" in dot
        assert '"c1"' in dot
        assert '"s1"' in dot

    def test_to_json(self):
        graph = LineageGraph()
        graph.add_node(LineageNode("c1", NodeType.CAMPAIGN, "Campaign"))
        graph.add_edge(LineageEdge("c1", "c1", EdgeType.PRODUCED_BY))

        data = graph.to_json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 1
