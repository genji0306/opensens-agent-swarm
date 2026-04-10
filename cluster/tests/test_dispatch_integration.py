"""Integration tests for the Leader dispatch handler."""
import json
from unittest.mock import patch, AsyncMock

import pytest

from shared.models import Task, TaskResult, TaskType
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
        "darklab-deerflow",
        "darklab-synthesis", "darklab-media-gen", "darklab-notebooklm",
        "darklab-deepresearch", "darklab-parameter-golf",
        "darklab-debate", "darklab-rl-train",
        "darklab-fullswarm",
        "darklab-turboswarm",
        "darklab-paper-review",
        "darklab-dft",
        "darklab-ane-research",
        "darklab-gemma-swarm",
        "darklab-unipat-swarm",
        "darklab-orchestrator",
        "darklab-kairos",
        "darklab-knowledge-wiki",
        "darklab-eval-harness",
    }

    def test_all_skills_routable(self):
        routed_skills = {r.skill for r in ROUTING_TABLE.values()}
        assert routed_skills == self.EXPECTED_SKILLS

    def test_route_count(self):
        assert len(ROUTING_TABLE) == 40

    def test_all_routes_have_valid_nodes(self):
        valid_nodes = {"academic", "experiment", "leader"}
        for cmd, route in ROUTING_TABLE.items():
            assert route.node in valid_nodes, f"Route '{cmd}' has invalid node: {route.node}"

    def test_new_routes_exist(self):
        """Verify key routes are present."""
        assert "perplexity" in ROUTING_TABLE
        assert "synthetic" in ROUTING_TABLE
        assert "report-data" in ROUTING_TABLE
        assert "prorl-status" in ROUTING_TABLE
        assert "prorl-run" in ROUTING_TABLE

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

    def test_prorl_status_routes_to_leader(self):
        route = resolve_route("prorl-status")
        assert route.node == "leader"
        assert route.skill == "darklab-rl-train"
        assert route.task_type == TaskType.RL_TRAIN

    def test_prorl_run_routes_to_leader(self):
        route = resolve_route("prorl-run")
        assert route.node == "leader"
        assert route.skill == "darklab-rl-train"
        assert route.task_type == TaskType.RL_TRAIN


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
    async def test_status_command_includes_team_runtime_summary(self):
        task = Task(task_type=TaskType.STATUS, payload={"text": "/status"})
        with patch("leader.dispatch.log_event"), \
             patch(
                 "leader.dispatch._team_runtime_status_summary",
                 return_value={
                     "enabled": True,
                     "team_count": 2,
                     "total_tasks": 5,
                     "total_events": 12,
                     "task_counts": {"completed": 3, "in_progress": 2},
                     "teams": [],
                 },
             ):
            result = await handle(task)

        assert result.status == "ok"
        assert result.result["action"] == "status"
        assert result.result["team_runtime"]["enabled"] is True
        assert "Team Runtime: 2 teams, 5 tasks, 12 events" in result.result["output"]

    @pytest.mark.asyncio
    async def test_help_command_returns_fast_local_response(self):
        task = Task(task_type=TaskType.STATUS, payload={"text": "/help"})
        with patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "help"
        assert "/research <topic>" in result.result["output"]

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
        assert invoke["payload"]["text"] == "MnO2 sensors"
        assert invoke["payload"]["raw_text"] == "/research MnO2 sensors"

    @pytest.mark.asyncio
    async def test_team_runtime_pending_recorded_for_remote_dispatch(self):
        task = Task(task_type=TaskType.RESEARCH, payload={"text": "/research TiO2 nanotubes"})
        with patch("leader.dispatch.log_event"), \
             patch("leader.dispatch._team_runtime_record_pending", new_callable=AsyncMock) as pending, \
             patch("leader.dispatch._team_runtime_mark_started", new_callable=AsyncMock) as started, \
             patch("leader.dispatch._team_runtime_mark_completed", new_callable=AsyncMock) as completed, \
             patch("leader.dispatch._team_runtime_mark_failed", new_callable=AsyncMock) as failed:
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "dispatch"
        pending.assert_awaited_once()
        started.assert_not_awaited()
        completed.assert_not_awaited()
        failed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_team_runtime_lifecycle_recorded_for_local_success(self):
        task = Task(task_type=TaskType.SYNTHESIZE, payload={"text": "/synthesize summary"})

        async def _fake_local_handler(_task):
            return TaskResult(
                task_id=_task.task_id,
                agent_name="LocalSynthesis",
                status="ok",
                result={"output": "done"},
            )

        with patch("leader.dispatch.log_event"), \
             patch("leader.dispatch._get_local_handler", return_value=_fake_local_handler), \
             patch("leader.dispatch._team_runtime_record_pending", new_callable=AsyncMock) as pending, \
             patch("leader.dispatch._team_runtime_mark_started", new_callable=AsyncMock) as started, \
             patch("leader.dispatch._team_runtime_mark_completed", new_callable=AsyncMock) as completed, \
             patch("leader.dispatch._team_runtime_mark_failed", new_callable=AsyncMock) as failed:
            result = await handle(task)

        assert result.status == "ok"
        pending.assert_awaited_once()
        started.assert_awaited_once()
        completed.assert_awaited_once()
        failed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_team_runtime_marks_failed_for_local_exception(self):
        task = Task(task_type=TaskType.SYNTHESIZE, payload={"text": "/synthesize summary"})

        async def _failing_local_handler(_task):
            raise RuntimeError("boom")

        with patch("leader.dispatch.log_event"), \
             patch("leader.dispatch._get_local_handler", return_value=_failing_local_handler), \
             patch("leader.dispatch._team_runtime_record_pending", new_callable=AsyncMock) as pending, \
             patch("leader.dispatch._team_runtime_mark_started", new_callable=AsyncMock) as started, \
             patch("leader.dispatch._team_runtime_mark_completed", new_callable=AsyncMock) as completed, \
             patch("leader.dispatch._team_runtime_mark_failed", new_callable=AsyncMock) as failed:
            result = await handle(task)

        assert result.status == "error"
        pending.assert_awaited_once()
        started.assert_awaited_once()
        completed.assert_not_awaited()
        failed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_worktree_guard_blocks_mutating_task_when_allocation_fails(self):
        task = Task(
            task_type=TaskType.SYNTHESIZE,
            payload={"text": "/synthesize summary", "mutating": True},
        )

        with patch("leader.dispatch.log_event"), \
             patch("leader.dispatch._team_runtime_record_pending", new_callable=AsyncMock), \
             patch(
                 "leader.dispatch._ensure_worktree_allocation",
                 new_callable=AsyncMock,
                 return_value={"blocked": True, "reason": "worktree_allocation_failed"},
             ) as guard:
            result = await handle(task)

        assert result.status == "error"
        assert result.result["blocked"] is True
        assert result.result["reason"] == "worktree_allocation_failed"
        guard.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_perplexity_command_dispatches(self):
        task = Task(task_type=TaskType.PERPLEXITY, payload={"text": "/perplexity latest EIT papers"})
        with patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "dispatch"
        assert result.result["route"]["skill"] == "darklab-perplexity"

    @pytest.mark.asyncio
    async def test_telegram_alias_dispatches(self):
        task = Task(task_type=TaskType.REPORT_DATA, payload={"text": "/report_data charts"})
        with patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "dispatch"
        assert result.result["route"]["skill"] == "darklab-report-data"
        assert result.result["node_invoke"]["payload"]["text"] == "charts"

    @pytest.mark.asyncio
    async def test_prorl_alias_dispatches(self):
        task = Task(task_type=TaskType.RL_TRAIN, payload={"text": "/prorl_status"})
        with patch("leader.dispatch.log_event"), \
             patch("leader.dispatch._get_local_handler", return_value=None):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "dispatch"
        assert result.result["route"]["skill"] == "darklab-rl-train"

    @pytest.mark.asyncio
    async def test_unknown_command_triggers_campaign_plan(self):
        task = Task(task_type=TaskType.PLAN, payload={"text": "Investigate MnO2 nanoparticles for EIT sensors"})
        mock_plan = [
            {"step": 1, "command": "research", "args": "MnO2 nanoparticles EIT", "depends_on": []},
            {"step": 2, "command": "simulate", "args": "MnO2 sensor response", "depends_on": [1]},
        ]
        with patch("leader.dispatch.call_routed", new_callable=AsyncMock, return_value=json.dumps(mock_plan)), \
             patch("leader.dispatch.call_anthropic", new_callable=AsyncMock, return_value=json.dumps(mock_plan)), \
             patch("leader.dispatch._get_governance", return_value=None), \
             patch("leader.dispatch._get_campaign_engine", return_value=None), \
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
             patch("leader.dispatch._get_governance", return_value=None), \
             patch("leader.dispatch._get_campaign_engine", return_value=None), \
             patch("leader.dispatch.log_event"):
            result = await handle(task)
        assert result.status == "ok"
        assert result.result["action"] == "campaign"
        # Should fall back to a single research step
        assert len(result.result["plan"]) == 1
        assert result.result["plan"][0]["command"] == "research"

    @pytest.mark.asyncio
    async def test_plan_file_task_short_circuits_to_orchestrator(self):
        task = Task(
            task_type=TaskType.PLAN,
            payload={"source": "plan_file", "plan_path": "/tmp/demo-plan.md"},
        )
        orchestrated = TaskResult(
            task_id=task.task_id,
            agent_name="OrchestratorAgent",
            status="ok",
            result={"action": "campaign", "plan": []},
        )

        with patch("leader.dispatch._handle_plan_file_task", new_callable=AsyncMock, return_value=orchestrated) as handler, \
             patch("leader.dispatch.get_swarm_app", new_callable=AsyncMock) as swarm, \
             patch("leader.dispatch.log_event"):
            result = await handle(task)

        assert result.result["action"] == "campaign"
        handler.assert_awaited_once()
        swarm.assert_not_called()


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
