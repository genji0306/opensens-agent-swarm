"""Tests for oas_core.campaign — CampaignEngine."""
import asyncio

import pytest

from oas_core.campaign import (
    CampaignEngine,
    CampaignStep,
    CampaignResult,
    StepStatus,
)
from oas_core.protocols.drvp import configure


@pytest.fixture(autouse=True)
def disable_drvp():
    configure(company_id="test", redis_client=None, paperclip_client=None)


def _simple_plan():
    return [
        {"step": 1, "command": "research", "args": "quantum dots", "depends_on": []},
        {"step": 2, "command": "simulate", "args": "QD model", "depends_on": [1]},
        {"step": 3, "command": "synthesize", "args": "findings", "depends_on": [2]},
    ]


def _parallel_plan():
    return [
        {"step": 1, "command": "research", "args": "topic A", "depends_on": []},
        {"step": 2, "command": "literature", "args": "topic B", "depends_on": []},
        {"step": 3, "command": "synthesize", "args": "combine", "depends_on": [1, 2]},
    ]


class TestCampaignStep:
    def test_from_dict(self):
        step = CampaignStep.from_dict({
            "step": 1,
            "command": "research",
            "args": "quantum sensors",
            "depends_on": [],
        })
        assert step.step == 1
        assert step.command == "research"
        assert step.status == StepStatus.PENDING

    def test_duration_none_when_not_started(self):
        step = CampaignStep(step=1, command="test", args="")
        assert step.duration_seconds is None


class TestCampaignResult:
    def test_to_dict(self):
        steps = [
            CampaignStep(step=1, command="research", args="", status=StepStatus.COMPLETED),
            CampaignStep(step=2, command="simulate", args="", status=StepStatus.FAILED, error="timeout"),
        ]
        result = CampaignResult(request_id="req_1", steps=steps, status="partial")

        d = result.to_dict()
        assert d["status"] == "partial"
        assert d["total_steps"] == 2
        assert d["completed"] == 1
        assert d["failed"] == 1

    def test_completed_and_failed_steps(self):
        steps = [
            CampaignStep(step=1, command="a", args="", status=StepStatus.COMPLETED),
            CampaignStep(step=2, command="b", args="", status=StepStatus.FAILED),
            CampaignStep(step=3, command="c", args="", status=StepStatus.SKIPPED),
        ]
        result = CampaignResult(request_id="req_1", steps=steps, status="partial")
        assert len(result.completed_steps) == 1
        assert len(result.failed_steps) == 1


class TestCampaignEngine:
    @pytest.mark.asyncio
    async def test_sequential_execution(self):
        """Steps with dependencies execute in order."""
        execution_order = []

        async def executor(command, args, payload):
            execution_order.append(command)
            return {"result": f"{command} done"}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_1",
            plan=_simple_plan(),
            agent_name="leader",
            device="leader",
        )

        assert result.status == "completed"
        assert len(result.completed_steps) == 3
        assert execution_order == ["research", "simulate", "synthesize"]
        assert result.total_duration_seconds is not None

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Independent steps run in parallel."""
        running = {"count": 0, "max": 0}

        async def executor(command, args, payload):
            running["count"] += 1
            running["max"] = max(running["max"], running["count"])
            await asyncio.sleep(0.01)
            running["count"] -= 1
            return {"result": f"{command} done"}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_2",
            plan=_parallel_plan(),
            agent_name="leader",
            device="leader",
        )

        assert result.status == "completed"
        assert running["max"] == 2  # steps 1 and 2 ran in parallel

    @pytest.mark.asyncio
    async def test_failed_step_skips_dependents(self):
        """Failed steps cause dependent steps to be skipped."""
        async def executor(command, args, payload):
            if command == "simulate":
                raise RuntimeError("Simulation crashed")
            return {"result": f"{command} done"}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_3",
            plan=_simple_plan(),
            agent_name="leader",
            device="leader",
        )

        assert result.status == "partial"
        assert result.steps[0].status == StepStatus.COMPLETED  # research
        assert result.steps[1].status == StepStatus.FAILED     # simulate
        assert result.steps[2].status == StepStatus.SKIPPED    # synthesize (depends on 2)

    @pytest.mark.asyncio
    async def test_timeout_step(self):
        """Step that exceeds timeout is marked as failed."""
        async def executor(command, args, payload):
            if command == "research":
                await asyncio.sleep(10)
            return {"result": "done"}

        engine = CampaignEngine(step_executor=executor, step_timeout=0.05)
        result = await engine.execute(
            request_id="req_4",
            plan=[{"step": 1, "command": "research", "args": "slow", "depends_on": []}],
            agent_name="leader",
            device="leader",
        )

        assert result.steps[0].status == StepStatus.FAILED
        assert "timed out" in result.steps[0].error

    @pytest.mark.asyncio
    async def test_single_step_plan(self):
        async def executor(command, args, payload):
            return {"answer": 42}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_5",
            plan=[{"step": 1, "command": "research", "args": "simple", "depends_on": []}],
            agent_name="leader",
            device="leader",
        )

        assert result.status == "completed"
        assert result.steps[0].result == {"answer": 42}

    @pytest.mark.asyncio
    async def test_dependency_results_passed(self):
        """Step receives results from its dependencies."""
        received_payload = {}

        async def executor(command, args, payload):
            if command == "synthesize":
                received_payload.update(payload)
            return {"data": f"from_{command}"}

        engine = CampaignEngine(step_executor=executor)
        await engine.execute(
            request_id="req_6",
            plan=[
                {"step": 1, "command": "research", "args": "A", "depends_on": []},
                {"step": 2, "command": "synthesize", "args": "B", "depends_on": [1]},
            ],
            agent_name="leader",
            device="leader",
        )

        assert "dependency_results" in received_payload
        assert "step_1" in received_payload["dependency_results"]
        assert received_payload["dependency_results"]["step_1"]["data"] == "from_research"

    @pytest.mark.asyncio
    async def test_all_steps_fail(self):
        async def executor(command, args, payload):
            raise RuntimeError("everything broke")

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_7",
            plan=_simple_plan(),
            agent_name="leader",
            device="leader",
        )

        assert result.status == "failed" or result.status == "partial"
        assert result.steps[0].status == StepStatus.FAILED

    @pytest.mark.asyncio
    async def test_max_parallel_respected(self):
        """Concurrency is limited by max_parallel."""
        running = {"count": 0, "max": 0}

        async def executor(command, args, payload):
            running["count"] += 1
            running["max"] = max(running["max"], running["count"])
            await asyncio.sleep(0.02)
            running["count"] -= 1
            return {"ok": True}

        plan = [
            {"step": i, "command": f"task_{i}", "args": "", "depends_on": []}
            for i in range(1, 6)
        ]

        engine = CampaignEngine(step_executor=executor, max_parallel=2)
        result = await engine.execute(
            request_id="req_8",
            plan=plan,
            agent_name="leader",
            device="leader",
        )

        assert result.status == "completed"
        assert running["max"] <= 2
