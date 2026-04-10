"""Tests for the plan-file orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from leader.orchestrator import OrchestratorAgent, is_plan_file_task, handle
from shared.models import Task, TaskResult, TaskType


SAMPLE_PLAN = """---
id: 2026-04-05-polymer-degradation
title: Polymer membrane degradation triage
author: claude-sonnet-4-6
intent: research
mode: hybrid
budget_usd: 3.0
tier: local_only
approvals_required: false
readiness_threshold: 0.65
research_backends: [deerflow, internagent]
synthesis: uniscientist
allow_kairos_followup: true
tags: [polymer, membranes]
---

# Objective
Understand degradation mechanisms and propose next experiments.

# Steps
1. Literature sweep -- polymer membrane degradation mechanisms in electrochemical systems.
2. Parameter extraction -- identify stressors, temperatures, and electrolyte conditions.
3. Simulation plan -- design DOE around the top three variables.
4. Synthesis -- produce a concise technical report.

# Constraints
- Keep cloud spend under three dollars.

# Success criteria
- Deliver a validated experiment shortlist.
"""


class _FakeCampaignResult:
    def __init__(self, *, status: str = "completed") -> None:
        self.status = status

    def to_dict(self) -> dict:
        return {"status": self.status, "completed": 4, "failed": 0}


class _FakeEngine:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeCampaignResult()


class _FakeGovernance:
    def __init__(self, *, approved: bool = True) -> None:
        self.approved = approved
        self.issue_calls: list[dict] = []
        self.approval_calls: list[dict] = []

    async def open_issue(self, **kwargs):
        self.issue_calls.append(kwargs)
        return {"id": "iss-1", "key": "DL-101"}

    async def request_campaign_approval(self, **kwargs):
        self.approval_calls.append(kwargs)
        return {"approved": self.approved, "approval_id": "apr-1", "reason": "test"}


def _make_task(tmp_path: Path, *, approved: bool = False) -> Task:
    plan_path = tmp_path / "2026-04-05T0930_polymer-degradation.md"
    plan_path.write_text(SAMPLE_PLAN.replace("approvals_required: false", f"approvals_required: {'true' if approved else 'false'}"), encoding="utf-8")
    return Task(
        task_id="task-plan-1",
        task_type=TaskType.PLAN,
        payload={
            "source": "plan_file",
            "plan_path": str(plan_path),
        },
    )


class TestPlanFileDetection:
    def test_detects_plan_path(self, tmp_path):
        task = _make_task(tmp_path)
        assert is_plan_file_task(task) is True

    def test_detects_plan_markdown(self):
        task = Task(task_type=TaskType.PLAN, payload={"plan_markdown": SAMPLE_PLAN})
        assert is_plan_file_task(task) is True


class TestOrchestratorAgent:
    def test_plan_to_campaign_adds_metadata_and_dependencies(self, tmp_path):
        task = _make_task(tmp_path)
        orchestrator = OrchestratorAgent(campaign_engine=None, governance=None)
        prepared = orchestrator.plan_to_campaign(
            orchestrator.load_plan_file(task),
            request_id=task.task_id,
        )

        # Check engine_plan (dict-based steps)
        plan = prepared.engine_plan
        assert len(plan) == 4
        assert plan[0]["depends_on"] == []
        assert plan[1]["depends_on"] == [1]
        assert plan[2]["depends_on"] == [2]
        assert plan[3]["depends_on"] == [3]
        assert plan[0]["metadata"]["model_tier"] == "planning_local"
        assert plan[0]["metadata"]["research_mode"] == "hybrid"
        assert plan[3]["metadata"]["synthesis_backend"] == "uniscientist"
        # Check metadata
        assert prepared.metadata["plan_id"] == "2026-04-05-polymer-degradation"
        assert prepared.metadata["request_id"] == "task-plan-1"

    @pytest.mark.asyncio
    async def test_handle_task_executes_when_ready(self, tmp_path):
        task = _make_task(tmp_path)
        engine = _FakeEngine()
        gov = _FakeGovernance()
        orchestrator = OrchestratorAgent(campaign_engine=engine, governance=gov)

        result = await orchestrator.handle_task(task)

        assert result.status == "ok"
        assert result.result["action"] == "campaign_executed"
        assert result.result["plan_file"]["id"] == "2026-04-05-polymer-degradation"
        assert result.result["issue_id"] == "iss-1"
        assert len(engine.calls) == 1
        assert engine.calls[0]["agent_name"] == "OrchestratorAgent"

    @pytest.mark.asyncio
    async def test_handle_task_returns_staged_campaign_when_approval_pending(self, tmp_path):
        task = _make_task(tmp_path, approved=True)
        engine = _FakeEngine()
        gov = _FakeGovernance(approved=False)
        orchestrator = OrchestratorAgent(campaign_engine=engine, governance=gov)

        result = await orchestrator.handle_task(task)

        assert result.status == "ok"
        assert result.result["action"] == "campaign"
        assert result.result["requires_approval"] is True
        assert len(engine.calls) == 0
        assert len(gov.approval_calls) == 1

    @pytest.mark.asyncio
    async def test_sequential_mode_produces_linear_deps(self, tmp_path):
        task = _make_task(tmp_path)
        orchestrator = OrchestratorAgent(campaign_engine=None, governance=None)
        prepared = orchestrator.plan_to_campaign(
            orchestrator.load_plan_file(task),
            request_id=task.task_id,
        )
        deps = [s["depends_on"] for s in prepared.engine_plan]
        # Each step depends on the prior one (sequential by default in plan)
        assert deps[0] == []
        for i in range(1, len(deps)):
            assert deps[i] == [i]

    @pytest.mark.asyncio
    async def test_handle_task_returns_correct_status(self, tmp_path):
        task = _make_task(tmp_path)
        engine = _FakeEngine()
        orchestrator = OrchestratorAgent(campaign_engine=engine, governance=None)

        result = await orchestrator.handle_task(task)

        assert isinstance(result, TaskResult)
        assert result.status == "ok"
        assert result.agent_name == "OrchestratorAgent"

    @pytest.mark.asyncio
    async def test_handle_task_empty_steps_raises(self):
        """Plan with no parseable steps should fail during plan_to_campaign."""
        bad_plan = """---
id: empty-steps
title: Empty plan
author: test
intent: research
---

# Objective
Test objective.

# Steps
"""
        task = Task(
            task_id="task-empty",
            task_type=TaskType.PLAN,
            payload={"plan_markdown": bad_plan, "source": "plan_file"},
        )
        orchestrator = OrchestratorAgent(campaign_engine=None, governance=None)
        result = await orchestrator.handle_task(task)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_handle_task_emits_drvp_events(self, tmp_path):
        task = _make_task(tmp_path)
        engine = _FakeEngine()
        orchestrator = OrchestratorAgent(campaign_engine=engine, governance=None)

        emitted = []

        async def mock_emit(event):
            emitted.append(event.event_type.value if hasattr(event.event_type, 'value') else event.event_type)

        with patch("leader.orchestrator._emit_drvp", new_callable=AsyncMock) as mock_drvp:
            result = await orchestrator.handle_task(task)

        assert result.status == "ok"
        # _emit_drvp should have been called (started + step_dispatched * N + completed)
        assert mock_drvp.await_count >= 3  # at least started + steps + completed

    @pytest.mark.asyncio
    async def test_handle_task_invalid_plan_returns_error(self):
        task = Task(
            task_id="task-bad",
            task_type=TaskType.PLAN,
            payload={"plan_markdown": "not a valid plan", "source": "plan_file"},
        )
        orchestrator = OrchestratorAgent(campaign_engine=None, governance=None)
        result = await orchestrator.handle_task(task)
        assert result.status == "error"


class TestHandleDispatchFunction:
    """Test the handle() function used by dispatch integration."""

    @pytest.mark.asyncio
    async def test_handle_with_plan_path(self, tmp_path):
        plan_path = tmp_path / "2026-04-05T0930_dispatch-test.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")

        task = Task(
            task_id="task-dispatch-1",
            task_type=TaskType.ORCHESTRATE,
            payload={"args": str(plan_path)},
        )

        async def patched_handle_task(self, task):
            return TaskResult(
                task_id=task.task_id,
                agent_name="OrchestratorAgent",
                status="ok",
                result={"action": "campaign_executed"},
            )

        with patch("leader.dispatch._get_campaign_engine", return_value=_FakeEngine()), \
             patch("leader.dispatch._get_governance", return_value=None), \
             patch.object(OrchestratorAgent, "handle_task", patched_handle_task):
            result = await handle(task)

        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_handle_missing_plan_returns_error(self):
        task = Task(
            task_id="task-no-plan",
            task_type=TaskType.ORCHESTRATE,
            payload={"text": "/orchestrate"},
        )
        result = await handle(task)
        assert result.status == "error"
        assert "Missing plan_path" in result.result["error"]
