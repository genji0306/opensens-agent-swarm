"""Tests for FullSwarm v2 — plan-only dispatch, approval, local execution, sync."""
from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from shared.models import Task, TaskResult, TaskType


# ── PlanOnlyDispatcher tests ─────────────────────────────────────────────


class TestPlanStep:
    def test_plan_step_creation(self):
        from leader.plan_only_dispatcher import PlanStep

        step = PlanStep(
            step=1,
            command="research",
            args="quantum error correction",
            execution_tier="leader_4b",
            depends_on=(),
            phase="discovery",
            estimated_minutes=5,
        )
        assert step.step == 1
        assert step.command == "research"
        assert step.execution_tier == "leader_4b"
        assert step.depends_on == ()

    def test_plan_step_to_dict(self):
        from leader.plan_only_dispatcher import PlanStep

        step = PlanStep(
            step=3, command="perplexity", args="topic",
            execution_tier="leader_4b", depends_on=(1, 2),
            phase="discovery", estimated_minutes=3,
        )
        d = step.to_dict()
        assert d["step"] == 3
        assert d["depends_on"] == [1, 2]
        assert d["execution_tier"] == "leader_4b"


class TestFullSwarmPlan:
    def test_plan_creation(self):
        from leader.plan_only_dispatcher import FullSwarmPlan, PlanStep

        steps = (
            PlanStep(1, "research", "topic", "leader_4b", (), "discovery", 5),
            PlanStep(2, "literature", "topic", "leader_4b", (), "discovery", 5),
        )
        plan = FullSwarmPlan(
            run_id="swarm-test123",
            topic="quantum error correction",
            steps=steps,
            created_by="claude-sonnet",
            created_at="2026-04-09T12:00:00Z",
            approval_status="pending_approval",
            estimated_duration_minutes=10,
        )
        assert plan.run_id == "swarm-test123"
        assert len(plan.steps) == 2
        assert plan.approval_status == "pending_approval"

    def test_plan_roundtrip_json(self):
        from leader.plan_only_dispatcher import FullSwarmPlan, PlanStep

        steps = (
            PlanStep(1, "research", "topic", "leader_4b", (), "discovery", 5),
            PlanStep(5, "deepresearch", "topic", "dev_27b", (1,), "deep_analysis", 15),
        )
        plan = FullSwarmPlan(
            run_id="swarm-roundtrip",
            topic="test topic",
            steps=steps,
            created_by="template",
            created_at="2026-04-09T12:00:00Z",
            approval_status="pending_approval",
            estimated_duration_minutes=20,
        )

        json_str = plan.to_json()
        data = json.loads(json_str)
        restored = FullSwarmPlan.from_dict(data)

        assert restored.run_id == plan.run_id
        assert restored.topic == plan.topic
        assert len(restored.steps) == 2
        assert restored.steps[0].command == "research"
        assert restored.steps[1].depends_on == (1,)

    def test_plan_to_dict(self):
        from leader.plan_only_dispatcher import FullSwarmPlan, PlanStep

        plan = FullSwarmPlan(
            run_id="swarm-dict",
            topic="test",
            steps=(PlanStep(1, "research", "t", "leader_4b", (), "d", 5),),
            created_by="template",
            created_at="2026-04-09T12:00:00Z",
            approval_status="created",
        )
        d = plan.to_dict()
        assert d["run_id"] == "swarm-dict"
        assert len(d["steps"]) == 1


class TestPlanOnlyDispatcher:
    def test_save_and_load_plan(self, tmp_path: Path):
        from leader.plan_only_dispatcher import PlanOnlyDispatcher, FullSwarmPlan, PlanStep

        dispatcher = PlanOnlyDispatcher(state_dir=tmp_path)
        plan = FullSwarmPlan(
            run_id="swarm-save",
            topic="ionic liquids",
            steps=(PlanStep(1, "research", "IL", "leader_4b", (), "d", 5),),
            created_by="test",
            created_at="2026-04-09T12:00:00Z",
            approval_status="pending_approval",
        )

        dispatcher.save_plan(plan)
        loaded = dispatcher.load_plan("swarm-save")

        assert loaded is not None
        assert loaded.run_id == "swarm-save"
        assert loaded.topic == "ionic liquids"

    def test_load_missing_plan(self, tmp_path: Path):
        from leader.plan_only_dispatcher import PlanOnlyDispatcher

        dispatcher = PlanOnlyDispatcher(state_dir=tmp_path)
        assert dispatcher.load_plan("nonexistent") is None

    def test_approve_plan(self, tmp_path: Path):
        from leader.plan_only_dispatcher import PlanOnlyDispatcher, FullSwarmPlan, PlanStep

        dispatcher = PlanOnlyDispatcher(state_dir=tmp_path)
        plan = FullSwarmPlan(
            run_id="swarm-approve",
            topic="test",
            steps=(PlanStep(1, "research", "t", "leader_4b", (), "d", 5),),
            created_by="test",
            created_at="2026-04-09T12:00:00Z",
            approval_status="pending_approval",
        )
        dispatcher.save_plan(plan)

        approved = dispatcher.approve_plan("swarm-approve", approved_by="boss")
        assert approved is not None
        assert approved.approval_status == "approved"
        assert approved.approved_by == "boss"

        # Verify persisted
        reloaded = dispatcher.load_plan("swarm-approve")
        assert reloaded.approval_status == "approved"

    def test_approve_already_approved(self, tmp_path: Path):
        from leader.plan_only_dispatcher import PlanOnlyDispatcher, FullSwarmPlan, PlanStep

        dispatcher = PlanOnlyDispatcher(state_dir=tmp_path)
        plan = FullSwarmPlan(
            run_id="swarm-double",
            topic="test",
            steps=(PlanStep(1, "research", "t", "leader_4b", (), "d", 5),),
            created_by="test",
            created_at="2026-04-09T12:00:00Z",
            approval_status="approved",
        )
        dispatcher.save_plan(plan)

        result = dispatcher.approve_plan("swarm-double")
        assert result is None  # Can't approve already-approved

    def test_reject_plan(self, tmp_path: Path):
        from leader.plan_only_dispatcher import PlanOnlyDispatcher, FullSwarmPlan, PlanStep

        dispatcher = PlanOnlyDispatcher(state_dir=tmp_path)
        plan = FullSwarmPlan(
            run_id="swarm-reject",
            topic="test",
            steps=(PlanStep(1, "research", "t", "leader_4b", (), "d", 5),),
            created_by="test",
            created_at="2026-04-09T12:00:00Z",
            approval_status="pending_approval",
        )
        dispatcher.save_plan(plan)

        rejected = dispatcher.reject_plan("swarm-reject")
        assert rejected is not None
        assert rejected.approval_status == "rejected"

    def test_list_pending(self, tmp_path: Path):
        from leader.plan_only_dispatcher import PlanOnlyDispatcher, FullSwarmPlan, PlanStep

        dispatcher = PlanOnlyDispatcher(state_dir=tmp_path)

        for i, status in enumerate(["pending_approval", "approved", "pending_approval"]):
            plan = FullSwarmPlan(
                run_id=f"swarm-list{i}",
                topic="test",
                steps=(PlanStep(1, "research", "t", "leader_4b", (), "d", 5),),
                created_by="test",
                created_at="2026-04-09T12:00:00Z",
                approval_status=status,
            )
            dispatcher.save_plan(plan)

        pending = dispatcher.list_pending()
        assert len(pending) == 2


# ── Step tier mapping tests ──────────────────────────────────────────────


class TestStepTierMap:
    def test_all_commands_have_tiers(self):
        from leader.plan_only_dispatcher import STEP_TIER_MAP

        expected_commands = {
            "research", "literature", "perplexity", "deerflow",
            "deepresearch", "swarmresearch", "debate",
            "doe", "synthetic", "simulate", "analyze",
            "parametergolf", "autoresearch",
            "synthesize", "report-data", "report", "paper", "notebooklm",
        }
        for cmd in expected_commands:
            assert cmd in STEP_TIER_MAP, f"Missing tier for {cmd}"

    def test_leader_commands_use_leader_4b(self):
        from leader.plan_only_dispatcher import STEP_TIER_MAP

        leader_cmds = ["research", "literature", "perplexity", "deerflow",
                        "report", "report-data", "notebooklm"]
        for cmd in leader_cmds:
            assert STEP_TIER_MAP[cmd] == "leader_4b", f"{cmd} should be leader_4b"

    def test_deep_commands_use_dev_27b(self):
        from leader.plan_only_dispatcher import STEP_TIER_MAP

        deep_cmds = ["deepresearch", "swarmresearch", "debate",
                      "analyze", "synthetic", "synthesize", "paper"]
        for cmd in deep_cmds:
            assert STEP_TIER_MAP[cmd] == "dev_27b", f"{cmd} should be dev_27b"

    def test_code_commands_use_dev_coder(self):
        from leader.plan_only_dispatcher import STEP_TIER_MAP

        code_cmds = ["doe", "simulate", "parametergolf", "autoresearch"]
        for cmd in code_cmds:
            assert STEP_TIER_MAP[cmd] == "dev_coder", f"{cmd} should be dev_coder"


# ── Template plan generation tests ───────────────────────────────────────


class TestBuildStepsFromTemplate:
    def test_builds_correct_step_count(self):
        from leader.plan_only_dispatcher import _build_steps_from_template

        steps = _build_steps_from_template("quantum error correction")
        assert len(steps) == 20

    def test_steps_have_correct_phases(self):
        from leader.plan_only_dispatcher import _build_steps_from_template

        steps = _build_steps_from_template("test topic")
        phases = {s.phase for s in steps}
        assert phases == {"discovery", "deep_analysis", "experimentation",
                          "optimization", "deliverables", "extras"}

    def test_step_1_has_no_deps(self):
        from leader.plan_only_dispatcher import _build_steps_from_template

        steps = _build_steps_from_template("test")
        assert steps[0].depends_on == ()
        assert steps[0].command == "research"

    def test_deep_analysis_depends_on_discovery(self):
        from leader.plan_only_dispatcher import _build_steps_from_template

        steps = _build_steps_from_template("test")
        # deepresearch is the first deep_analysis step; it must depend on all discovery steps
        deepresearch = next(s for s in steps if s.command == "deepresearch")
        discovery_steps = [s.step for s in steps if s.phase == "discovery"]
        assert set(deepresearch.depends_on) == set(discovery_steps)

    def test_topic_substituted_in_args(self):
        from leader.plan_only_dispatcher import _build_steps_from_template

        steps = _build_steps_from_template("ionic liquids")
        assert "ionic liquids" in steps[0].args


# ── Plan markdown formatting tests ───────────────────────────────────────


class TestFormatPlanMarkdown:
    def test_markdown_contains_topic(self):
        from leader.plan_only_dispatcher import _format_plan_markdown, FullSwarmPlan, PlanStep

        plan = FullSwarmPlan(
            run_id="swarm-md",
            topic="graphene oxide",
            steps=(PlanStep(1, "research", "graphene", "leader_4b", (), "discovery", 5),),
            created_by="test",
            created_at="2026-04-09T12:00:00Z",
            approval_status="pending_approval",
            estimated_duration_minutes=5,
        )
        md = _format_plan_markdown(plan)
        assert "graphene oxide" in md
        assert "swarm-md" in md
        assert "/approve" in md

    def test_markdown_contains_tier_labels(self):
        from leader.plan_only_dispatcher import _format_plan_markdown, FullSwarmPlan, PlanStep

        plan = FullSwarmPlan(
            run_id="swarm-tiers",
            topic="test",
            steps=(
                PlanStep(1, "research", "t", "leader_4b", (), "discovery", 5),
                PlanStep(5, "deepresearch", "t", "dev_27b", (1,), "deep_analysis", 15),
            ),
            created_by="test",
            created_at="2026-04-09T12:00:00Z",
            approval_status="pending_approval",
            estimated_duration_minutes=20,
        )
        md = _format_plan_markdown(plan)
        assert "Leader" in md
        assert "DEV-27B" in md


# ── Generate plan via Claude tests ───────────────────────────────────────


class TestGeneratePlanViaClaude:
    @pytest.mark.asyncio
    async def test_fallback_to_template(self):
        """When Claude API is unavailable, falls back to template."""
        from leader.plan_only_dispatcher import generate_plan_via_claude

        # No Claude API available — should use template
        with patch.dict(os.environ, {"DARKLAB_FULLSWARM_MODE": "plan_only"}):
            plan = await generate_plan_via_claude("test topic")

        assert plan.run_id.startswith("swarm-")
        assert plan.topic == "test topic"
        assert len(plan.steps) == 20
        assert plan.created_by == "template"
        assert plan.approval_status == "pending_approval"
        assert plan.estimated_duration_minutes > 0
        assert len(plan.plan_markdown) > 0


# ── Telegram notification tests ──────────────────────────────────────────


class TestTelegramNotify:
    def test_html_escape(self):
        from leader.telegram_notify import _html_escape

        assert _html_escape("a<b>c") == "a&lt;b&gt;c"
        assert _html_escape("a&b") == "a&amp;b"

    @pytest.mark.asyncio
    async def test_send_plan_approval_request(self):
        from leader.telegram_notify import send_plan_approval_request
        from leader.plan_only_dispatcher import FullSwarmPlan, PlanStep

        plan = FullSwarmPlan(
            run_id="swarm-tg",
            topic="test <topic>",
            steps=(
                PlanStep(1, "research", "test", "leader_4b", (), "discovery", 5),
                PlanStep(5, "deepresearch", "test", "dev_27b", (1,), "deep_analysis", 15),
            ),
            created_by="test",
            created_at="2026-04-09T12:00:00Z",
            approval_status="pending_approval",
            estimated_duration_minutes=20,
        )

        # No BOT_TOKEN → returns False but doesn't crash
        with patch("leader.telegram_notify.BOT_TOKEN", ""):
            result = await send_plan_approval_request(plan)
            assert result is False


# ── LocalPlanExecutor tests ──────────────────────────────────────────────


class TestLocalPlanExecutor:
    def test_tier_model_map(self):
        from leader.local_plan_executor import TIER_MODEL_MAP

        assert TIER_MODEL_MAP["leader_4b"] == "gemma3:4b"
        assert TIER_MODEL_MAP["dev_27b"] == "gemma3:27b-it-qat"
        assert TIER_MODEL_MAP["dev_coder"] == "qwen2.5-coder:7b"

    def test_execution_state(self, tmp_path: Path):
        from leader.local_plan_executor import ExecutionState

        state = ExecutionState("test-run", tmp_path)
        state.update(status="running", completed_steps=[1, 2])

        assert state.completed_steps == [1, 2]

        # Reload from disk
        state2 = ExecutionState("test-run", tmp_path)
        assert state2.completed_steps == [1, 2]

    def test_execution_state_persistence(self, tmp_path: Path):
        from leader.local_plan_executor import ExecutionState

        state = ExecutionState("persist-test", tmp_path)
        state.update(topic="test", failed_steps=[3])
        assert state.failed_steps == [3]

        # File exists
        assert (tmp_path / "persist-test.json").exists()


# ── fullswarm_cmd handle() integration tests ─────────────────────────────


class TestFullswarmCmdHandle:
    @pytest.mark.asyncio
    async def test_help_output(self):
        from leader.fullswarm_cmd import handle

        task = Task(
            task_id="test-help",
            task_type=TaskType.FULL_SWARM,
            user_id=0,
            payload={"text": "help"},
        )
        result = await handle(task)
        assert result.status == "ok"
        assert "plan-only" in result.result["output"].lower() or "legacy" in result.result["output"].lower()

    @pytest.mark.asyncio
    async def test_discover_empty(self, tmp_path: Path):
        from leader.fullswarm_cmd import _handle_discover

        task = Task(
            task_id="test-discover",
            task_type=TaskType.FULL_SWARM,
            user_id=0,
            payload={},
        )
        with patch("leader.fullswarm_cmd.settings") as mock_settings:
            mock_settings.darklab_home = str(tmp_path)
            result = await _handle_discover(task)
        assert result.status == "ok"
        assert "total_runs" in result.result.get("index", {})

    @pytest.mark.asyncio
    async def test_approve_nonexistent(self):
        from leader.fullswarm_cmd import _handle_approve

        task = Task(
            task_id="test-approve-bad",
            task_type=TaskType.FULL_SWARM,
            user_id=0,
            payload={},
        )
        result = await _handle_approve(task, "nonexistent-id")
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_reject_nonexistent(self):
        from leader.fullswarm_cmd import _handle_reject

        task = Task(
            task_id="test-reject-bad",
            task_type=TaskType.FULL_SWARM,
            user_id=0,
            payload={},
        )
        result = await _handle_reject(task, "nonexistent-id")
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_handle_status(self):
        from leader.fullswarm_cmd import _handle_status

        task = Task(
            task_id="test-status",
            task_type=TaskType.FULL_SWARM,
            user_id=0,
            payload={},
        )
        result = await _handle_status(task)
        assert result.status == "ok"
