"""Tests for the node heartbeat service."""

import time
import pytest

from oas_core.scheduler.heartbeat import HeartbeatService, NodeState, NodeInfo


@pytest.fixture
def hb():
    return HeartbeatService(heartbeat_interval=0.1, degraded_after=1, offline_after=3)


class TestHeartbeatService:
    def test_register_node(self, hb):
        node = hb.register("leader", capabilities=["research"], address="192.168.23.25")
        assert node.node_id == "leader"
        assert node.state == NodeState.ONLINE
        assert hb.node_count == 1

    def test_heartbeat_keeps_online(self, hb):
        hb.register("academic")
        assert hb.heartbeat("academic") is True
        node = hb.get_node("academic")
        assert node is not None
        assert node.state == NodeState.ONLINE

    def test_heartbeat_unknown_node(self, hb):
        assert hb.heartbeat("unknown") is False

    def test_health_check_detects_degraded(self, hb):
        hb.register("test_node")
        # Simulate time passing
        node = hb.get_node("test_node")
        assert node is not None
        node.last_heartbeat = time.monotonic() - 0.15  # 1.5 intervals

        states = hb.check_health()
        assert states["test_node"] == NodeState.DEGRADED

    def test_health_check_detects_offline(self, hb):
        hb.register("test_node")
        node = hb.get_node("test_node")
        assert node is not None
        node.last_heartbeat = time.monotonic() - 0.5  # 5 intervals

        states = hb.check_health()
        assert states["test_node"] == NodeState.OFFLINE

    def test_get_healthy_nodes(self, hb):
        hb.register("a")
        hb.register("b")
        node_b = hb.get_node("b")
        assert node_b is not None
        node_b.state = NodeState.OFFLINE

        healthy = hb.get_healthy_nodes()
        assert len(healthy) == 1
        assert healthy[0].node_id == "a"

    def test_lease_and_release(self, hb):
        hb.register("leader")
        assert hb.lease("leader", "task_1") is True

        node = hb.get_node("leader")
        assert node is not None
        assert "task_1" in node.active_tasks

        assert hb.release_lease("task_1") is True
        assert "task_1" not in node.active_tasks

    def test_lease_fails_for_offline_node(self, hb):
        hb.register("dead")
        node = hb.get_node("dead")
        assert node is not None
        node.state = NodeState.OFFLINE
        assert hb.lease("dead", "task_x") is False

    def test_expired_leases(self, hb):
        hb.register("leader")
        hb.lease("leader", "task_old", duration=0.0)  # already expired

        expired = hb.get_expired_leases()
        assert len(expired) == 1
        assert expired[0].task_id == "task_old"

    def test_unregister(self, hb):
        hb.register("temp")
        hb.lease("temp", "t1")
        assert hb.unregister("temp") is True
        assert hb.node_count == 0

    def test_list_nodes(self, hb):
        hb.register("a")
        hb.register("b")
        nodes = hb.list_nodes()
        assert len(nodes) == 2
        assert nodes[0]["node_id"] in ("a", "b")

    def test_node_recovery(self, hb):
        hb.register("recovering")
        node = hb.get_node("recovering")
        assert node is not None
        node.state = NodeState.OFFLINE

        hb.heartbeat("recovering")
        assert node.state == NodeState.ONLINE
