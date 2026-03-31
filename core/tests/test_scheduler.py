"""Tests for the resource-aware scheduler."""

import pytest

from oas_core.scheduler.scheduler import Scheduler, ScheduleResult
from oas_core.scheduler.task_queue import TaskQueue, TaskPriority
from oas_core.scheduler.heartbeat import HeartbeatService, NodeState
from oas_core.scheduler.discovery import DiscoveryService, NodeCapabilities


@pytest.fixture
def setup():
    queue = TaskQueue()
    hb = HeartbeatService()
    hb.register("leader", capabilities=["synthesize", "report"])
    hb.register("academic", capabilities=["research", "literature"])
    hb.register("experiment", capabilities=["simulate", "analyze"])
    discovery = DiscoveryService(hb, load_defaults=False)
    discovery.register_capabilities(NodeCapabilities(
        node_id="academic", supported_commands=["research", "literature"],
    ))
    discovery.register_capabilities(NodeCapabilities(
        node_id="experiment", supported_commands=["simulate", "analyze"],
    ))
    discovery.register_capabilities(NodeCapabilities(
        node_id="leader", supported_commands=["synthesize", "report"],
    ))
    scheduler = Scheduler(queue, hb, discovery)
    return scheduler, queue, hb


class TestScheduler:
    @pytest.mark.asyncio
    async def test_schedule_research(self, setup):
        scheduler, queue, hb = setup
        result = await scheduler.schedule("research", "quantum dots")
        assert result.scheduled is True
        assert result.node_id == "academic"

    @pytest.mark.asyncio
    async def test_schedule_simulation(self, setup):
        scheduler, queue, hb = setup
        result = await scheduler.schedule("simulate", "model X")
        assert result.scheduled is True
        assert result.node_id == "experiment"

    @pytest.mark.asyncio
    async def test_schedule_with_device_hint(self, setup):
        scheduler, queue, hb = setup
        result = await scheduler.schedule(
            "research", "test", device_hint="academic"
        )
        assert result.scheduled is True
        assert result.node_id == "academic"

    @pytest.mark.asyncio
    async def test_schedule_to_dict(self, setup):
        scheduler, queue, hb = setup
        result = await scheduler.schedule("research", "test")
        d = result.to_dict()
        assert d["scheduled"] is True
        assert d["node_id"] == "academic"

    @pytest.mark.asyncio
    async def test_rebalance_expired_leases(self, setup):
        scheduler, queue, hb = setup
        hb.lease("academic", "old_task", duration=0.0)  # already expired
        requeued = await scheduler.rebalance()
        assert "old_task" in requeued

    @pytest.mark.asyncio
    async def test_get_status(self, setup):
        scheduler, queue, hb = setup
        await scheduler.schedule("research", "test")
        status = await scheduler.get_status()
        assert "queue" in status
        assert "nodes" in status
        assert status["total_nodes"] == 3

    @pytest.mark.asyncio
    async def test_schedule_no_capable_node(self, setup):
        scheduler, queue, hb = setup
        # Unregister all nodes
        for node in list(hb._nodes.keys()):
            hb.unregister(node)
        # Discovery has no healthy nodes
        result = await scheduler.schedule("research", "test")
        # Falls back to static mapping
        assert result.scheduled is True  # static fallback always works
