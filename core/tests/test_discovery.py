"""Tests for the node capability discovery service."""

import pytest

from oas_core.scheduler.discovery import DiscoveryService, NodeCapabilities
from oas_core.scheduler.heartbeat import HeartbeatService, NodeState


@pytest.fixture
def svc():
    hb = HeartbeatService()
    hb.register("leader")
    hb.register("academic")
    hb.register("experiment")
    discovery = DiscoveryService(hb, load_defaults=True)
    return discovery, hb


class TestDiscoveryService:
    def test_default_capabilities_loaded(self, svc):
        discovery, hb = svc
        assert discovery.node_count == 3
        assert discovery.get_capabilities("leader") is not None

    def test_find_capable_research(self, svc):
        discovery, hb = svc
        nodes = discovery.find_capable("research")
        assert len(nodes) >= 1
        assert any(n.node_id == "academic" for n in nodes)

    def test_find_capable_simulate(self, svc):
        discovery, hb = svc
        nodes = discovery.find_capable("simulate")
        assert len(nodes) >= 1
        assert any(n.node_id == "experiment" for n in nodes)

    def test_find_capable_excludes_offline(self, svc):
        discovery, hb = svc
        node = hb.get_node("academic")
        assert node is not None
        node.state = NodeState.OFFLINE

        nodes = discovery.find_capable("research")
        assert not any(n.node_id == "academic" for n in nodes)

    def test_register_custom_capabilities(self, svc):
        discovery, hb = svc
        hb.register("custom_node")
        discovery.register_capabilities(NodeCapabilities(
            node_id="custom_node",
            supported_commands=["custom_task"],
            memory_gb=32,
        ))
        assert discovery.node_count == 4
        nodes = discovery.find_capable("custom_task")
        assert len(nodes) == 1

    def test_find_by_model(self, svc):
        discovery, hb = svc
        nodes = discovery.find_by_model("qwen3:8b")
        assert "academic" in nodes or "experiment" in nodes

    def test_unregister(self, svc):
        discovery, hb = svc
        assert discovery.unregister("leader") is True
        assert discovery.node_count == 2

    def test_list_all(self, svc):
        discovery, hb = svc
        all_nodes = discovery.list_all()
        assert len(all_nodes) == 3
        assert all("node_id" in n for n in all_nodes)
