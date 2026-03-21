"""Integration tests for the Leader dispatch handler."""
import json
from unittest.mock import patch, AsyncMock

import pytest

from shared.models import Task, TaskType
from leader.dispatch import (
    handle,
    parse_command,
    resolve_route,
    build_node_invoke,
    ROUTING_TABLE,
)


class TestRoutingTableCompleteness:
    """Verify all skills have routes and all routes map to valid skills."""

    EXPECTED_SKILLS = {
        "darklab-research", "darklab-literature", "darklab-doe", "darklab-paper",
        "darklab-perplexity", "darklab-simulation", "darklab-analysis",
        "darklab-synthetic", "darklab-report-data", "darklab-autoresearch",
        "darklab-synthesis", "darklab-media-gen", "darklab-notebooklm",
    }

    def test_all_skills_routable(self):
        routed_skills = {r.skill for r in ROUTING_TABLE.values()}
        assert routed_skills == self.EXPECTED_SKILLS

    def test_route_count(self):
        assert len(ROUTING_TABLE) == 13

    def test_all_routes_have_valid_nodes(self):
        valid_nodes = {"academic", "experiment", "leader"}
        for cmd, route in ROUTING_TABLE.items():
            assert route.node in valid_nodes, f"Route '{cmd}' has invalid node: {route.node}"

    def test_new_routes_exist(self):
        """Verify the 3 previously missing routes are now present."""
        assert "perplexity" in ROUTING_TABLE
        assert "synthetic" in ROUTING_TABLE
        assert "report-data" in ROUTING_TABLE

    def test_perplexity_routes_to_academic(self):
        route = resolve_route("perplexity")
        assert route.node == "academic"
        assert route.skill == "darklab-perplexity"
        assert route.task_type == TaskType.PERPLEXITY

    def test_synthetic_routes_to_experiment(self):
        route = resolve_route("synthetic")
        assert route.node == "experiment"
        assert route.skill == "darklab-synthetic"
        assert route.task_type == TaskType.SYNTHETIC

    def test_report_data_routes_to_experiment(self):
        route = resolve_route("report-data")
        assert route.node == "experiment"
        assert route.skill == "darklab-report-data"
        assert route.task_type == TaskType.REPORT_DATA


class TestDispatchHandler:
    """Test the async handle() function end-to-end."""

    @pytest.mark.asyncio
    async def test_status_command(self):
        task = Task(task_type=TaskType.STATUS, payload={"text": "/status"})
        with patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "status"

    @pytest.mark.asyncio
    async def test_known_command_dispatches(self):
        task = Task(task_type=TaskType.RESEARCH, payload={"text": "/research MnO2 sensors"})
        with patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "dispatch"
        assert result.result["route"]["node"] == "academic"
        assert result.result["route"]["skill"] == "darklab-research"
        # node_invoke should have the right structure
        invoke = result.result["node_invoke"]
        assert invoke["node"] == "darklab-academic"
        assert invoke["command"] == "darklab-research"
        assert "MnO2 sensors" in invoke["payload"]["text"]

    @pytest.mark.asyncio
    async def test_perplexity_command_dispatches(self):
        task = Task(task_type=TaskType.PERPLEXITY, payload={"text": "/perplexity latest EIT papers"})
        with patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "dispatch"
        assert result.result["route"]["skill"] == "darklab-perplexity"

    @pytest.mark.asyncio
    async def test_unknown_command_triggers_campaign_plan(self):
        task = Task(task_type=TaskType.PLAN, payload={"text": "Investigate MnO2 nanoparticles for EIT sensors"})
        mock_plan = [
            {"step": 1, "command": "research", "args": "MnO2 nanoparticles EIT", "depends_on": []},
            {"step": 2, "command": "simulate", "args": "MnO2 sensor response", "depends_on": [1]},
        ]
        with patch("leader.dispatch.call_routed", new_callable=AsyncMock, return_value=json.dumps(mock_plan)), \
             patch("leader.dispatch.call_anthropic", new_callable=AsyncMock, return_value=json.dumps(mock_plan)), \
             patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "campaign"
        assert len(result.result["plan"]) == 2
        assert result.result["requires_approval"] is True

    @pytest.mark.asyncio
    async def test_campaign_plan_fallback_on_invalid_llm_response(self):
        task = Task(task_type=TaskType.PLAN, payload={"text": "Do something complex"})
        with patch("leader.dispatch.call_routed", new_callable=AsyncMock, return_value="not valid json"), \
             patch("leader.dispatch.call_anthropic", new_callable=AsyncMock, return_value="not valid json"), \
             patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "campaign"
        # Should fall back to a single research step
        assert len(result.result["plan"]) == 1
        assert result.result["plan"][0]["command"] == "research"


class TestBuildNodeInvoke:
    """Test node invoke message construction."""

    def test_invoke_for_each_node_type(self):
        for cmd, route in ROUTING_TABLE.items():
            payload = {"text": f"test {cmd}"}
            msg = build_node_invoke(route, payload)
            assert msg["node"].startswith("darklab-")
            assert msg["command"].startswith("darklab-")
            assert msg["payload"]["text"] == f"test {cmd}"

    def test_payload_passthrough(self):
        route = resolve_route("simulate")
        payload = {"text": "test", "temperature": 300, "n_samples": 1000}
        msg = build_node_invoke(route, payload)
        assert msg["payload"]["temperature"] == 300
        assert msg["payload"]["n_samples"] == 1000
