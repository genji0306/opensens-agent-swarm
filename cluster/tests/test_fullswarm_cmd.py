"""Tests for /fullswarm command handler."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from shared.models import Task, TaskType


@pytest.fixture
def tmp_darklab(tmp_path, monkeypatch):
    """Set up a temporary darklab home."""
    monkeypatch.setattr("shared.config.settings.darklab_home", tmp_path)
    # Patch the module-level constant
    import leader.fullswarm_cmd as mod
    monkeypatch.setattr(mod, "SWARM_STATE_DIR", tmp_path / "fullswarm")
    return tmp_path


def _make_task(text: str = "") -> Task:
    return Task(
        task_id="test-001",
        task_type=TaskType.FULL_SWARM,
        payload={"text": text, "args": text},
    )


class TestFullSwarmHelp:
    @pytest.mark.asyncio
    async def test_help_no_args(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task(""))
        assert result.status == "ok"
        assert "Full Swarm Research Pipeline" in result.result["output"]
        assert "auto" in result.result["output"]
        assert "semi" in result.result["output"]
        assert "manual" in result.result["output"]

    @pytest.mark.asyncio
    async def test_help_explicit(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task("help"))
        assert result.status == "ok"
        assert "MODES" in result.result["output"]


class TestFullSwarmManual:
    @pytest.mark.asyncio
    async def test_manual_shows_plan(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task("manual quantum computing"))
        assert result.status == "ok"
        assert result.result["mode"] == "manual"
        assert result.result["status"] == "planned"
        assert result.result["total"] == 18
        assert "FULL SWARM PLAN" in result.result["output"]
        assert "quantum computing" in result.result["output"]

    @pytest.mark.asyncio
    async def test_manual_creates_run_state(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task("manual test topic"))
        run_id = result.result["run_id"]
        state_file = tmp_darklab / "fullswarm" / f"{run_id}.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text())
        assert state["mode"] == "manual"
        assert state["status"] == "planned"
        assert state["topic"] == "test topic"

    @pytest.mark.asyncio
    async def test_manual_no_topic_error(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task("manual"))
        assert result.status == "error"


class TestFullSwarmStatus:
    @pytest.mark.asyncio
    async def test_status_empty(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task("status"))
        assert result.status == "ok"
        assert "No swarm runs" in result.result["output"]

    @pytest.mark.asyncio
    async def test_status_with_runs(self, tmp_darklab):
        from leader.fullswarm_cmd import handle, _save_run
        _save_run({
            "run_id": "swarm-test001",
            "mode": "auto",
            "topic": "test topic",
            "status": "completed",
            "completed_steps": [1, 2, 3],
            "total_steps": 18,
            "current_phase": "discovery",
        })
        result = await handle(_make_task("status"))
        assert result.result["runs"] == 1
        assert "swarm-test001" in result.result["output"]


class TestFullSwarmResults:
    @pytest.mark.asyncio
    async def test_results_empty(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task("results"))
        assert result.status == "ok"
        assert "No completed" in result.result["output"]


class TestBuildPlan:
    def test_full_plan_has_18_steps(self):
        from leader.fullswarm_cmd import _build_full_plan
        plan = _build_full_plan("test topic")
        assert len(plan) == 18

    def test_plan_substitutes_topic(self):
        from leader.fullswarm_cmd import _build_full_plan
        plan = _build_full_plan("quantum error correction")
        for step in plan:
            assert "{topic}" not in step["args"]
            if step["command"] == "research":
                assert "quantum error correction" in step["args"]

    def test_plan_phase_labels(self):
        from leader.fullswarm_cmd import _build_full_plan
        plan = _build_full_plan("test")
        phases = {s["phase"] for s in plan}
        assert "discovery" in phases
        assert "deep_analysis" in phases
        assert "experimentation" in phases
        assert "optimization" in phases
        assert "deliverables" in phases
        assert "extras" in phases

    def test_plan_dependencies_valid(self):
        from leader.fullswarm_cmd import _build_full_plan
        plan = _build_full_plan("test")
        step_ids = {s["step"] for s in plan}
        for step in plan:
            for dep in step["depends_on"]:
                assert dep in step_ids, f"Step {step['step']} depends on {dep} which doesn't exist"

    def test_partial_phases(self):
        from leader.fullswarm_cmd import _build_full_plan
        plan = _build_full_plan("test", include_phases=["discovery"])
        assert len(plan) == 4
        assert all(s["phase"] == "discovery" for s in plan)


class TestFormatStatus:
    def test_format_running(self):
        from leader.fullswarm_cmd import _format_status
        output = _format_status({
            "run_id": "swarm-abc",
            "mode": "auto",
            "topic": "quantum dots",
            "status": "running",
            "completed_steps": [1, 2],
            "total_steps": 18,
            "current_phase": "discovery",
        })
        assert "swarm-abc" in output
        assert "auto" in output
        assert "2/18" in output

    def test_format_paused_shows_resume(self):
        from leader.fullswarm_cmd import _format_status
        output = _format_status({
            "run_id": "swarm-xyz",
            "mode": "semi",
            "topic": "batteries",
            "status": "paused",
            "completed_steps": [1, 2, 3, 4, 5, 6, 7],
            "total_steps": 18,
            "current_phase": "experimentation",
            "paused_at": "2026-03-30T12:00:00",
        })
        assert "/fullswarm resume swarm-xyz" in output


class TestResumeErrors:
    @pytest.mark.asyncio
    async def test_resume_missing_id(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task("resume"))
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_resume_not_found(self, tmp_darklab):
        from leader.fullswarm_cmd import handle
        result = await handle(_make_task("resume swarm-nonexistent"))
        assert result.status == "error"
        assert "not found" in result.result["error"]

    @pytest.mark.asyncio
    async def test_resume_not_resumable(self, tmp_darklab):
        from leader.fullswarm_cmd import handle, _save_run
        _save_run({
            "run_id": "swarm-done",
            "mode": "auto",
            "topic": "test",
            "status": "completed",
            "plan": [],
            "completed_steps": [],
            "failed_steps": [],
            "step_results": {},
        })
        result = await handle(_make_task("resume swarm-done"))
        assert result.status == "error"
        assert "not resumable" in result.result["error"]


class TestDefaultsToAuto:
    @pytest.mark.asyncio
    async def test_no_subcommand_defaults_auto(self, tmp_darklab):
        """Bare /fullswarm <topic> should default to auto mode."""
        from leader.fullswarm_cmd import handle
        with patch("leader.fullswarm_cmd._execute_plan_via_dispatch") as mock_exec:
            mock_exec.return_value = {
                "status": "completed",
                "completed_steps": list(range(1, 19)),
                "failed_steps": [],
                "step_results": {},
                "duration_seconds": 100,
            }
            result = await handle(_make_task("quantum error correction"))
            assert result.status == "ok"
            assert result.result["mode"] == "auto"


class TestRoutingRegistration:
    def test_fullswarm_in_routing_table(self):
        from leader.dispatch import ROUTING_TABLE
        assert "fullswarm" in ROUTING_TABLE
        route = ROUTING_TABLE["fullswarm"]
        assert route.node == "leader"
        assert route.task_type == TaskType.FULL_SWARM

    def test_fullswarm_task_type_exists(self):
        assert hasattr(TaskType, "FULL_SWARM")
        assert TaskType.FULL_SWARM.value == "full_swarm"


class TestModelRouterBoostEligible:
    def test_full_swarm_is_boost_eligible(self):
        pytest.importorskip("oas_core")
        from oas_core.model_router import BOOST_ELIGIBLE_TASKS
        assert "FULL_SWARM" in BOOST_ELIGIBLE_TASKS
