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

    def test_from_dict_with_retry_config(self):
        step = CampaignStep.from_dict({
            "step": 1,
            "command": "research",
            "args": "",
            "max_retries": 3,
            "retry_delay": 2.0,
            "retry_backoff": 1.5,
        })
        assert step.max_retries == 3
        assert step.retry_delay == 2.0
        assert step.retry_backoff == 1.5

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
        assert "retry_count" in d["steps"][0]
        assert "failure_reason_chain" in d["steps"][0]

    def test_completed_and_failed_steps(self):
        steps = [
            CampaignStep(step=1, command="a", args="", status=StepStatus.COMPLETED),
            CampaignStep(step=2, command="b", args="", status=StepStatus.FAILED),
            CampaignStep(step=3, command="c", args="", status=StepStatus.SKIPPED),
        ]
        result = CampaignResult(request_id="req_1", steps=steps, status="partial")
        assert len(result.completed_steps) == 1
        assert len(result.failed_steps) == 1

    def test_shared_memory_in_result(self):
        result = CampaignResult(
            request_id="req_1",
            steps=[],
            status="completed",
            shared_memory={"step_1_research": {"result": "data"}},
        )
        d = result.to_dict()
        assert "shared_memory_keys" in d
        assert "step_1_research" in d["shared_memory_keys"]


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
    async def test_failed_step_cascades_to_dependents(self):
        """Failed steps cause dependent steps to cascade-fail."""
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
        assert result.steps[2].status == StepStatus.FAILED     # synthesize (cascade)
        assert "Cascaded" in result.steps[2].error
        assert len(result.steps[2].failure_reason_chain) > 0

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

        # Step 1 fails directly, steps 2-3 cascade-fail
        assert result.status == "failed"
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


class TestSharedMemoryIntegration:
    """Test SharedMemory injection into campaign steps."""

    @pytest.mark.asyncio
    async def test_shared_memory_visible_to_all_steps(self):
        """Step 2 sees step 1's results via shared memory."""
        step2_payload = {}

        async def executor(command, args, payload):
            if command == "synthesize":
                step2_payload.update(payload)
            return {"data": f"from_{command}"}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_sm1",
            plan=[
                {"step": 1, "command": "research", "args": "A", "depends_on": []},
                {"step": 2, "command": "synthesize", "args": "B", "depends_on": [1]},
            ],
            agent_name="leader",
            device="leader",
        )

        assert "shared_memory" in step2_payload
        assert "step_1_research" in step2_payload["shared_memory"]
        assert step2_payload["shared_memory"]["step_1_research"]["result"]["data"] == "from_research"

    @pytest.mark.asyncio
    async def test_shared_memory_summary_injected(self):
        """Step receives shared_memory_summary string."""
        step2_payload = {}

        async def executor(command, args, payload):
            if command == "synthesize":
                step2_payload.update(payload)
            return {"data": "ok"}

        engine = CampaignEngine(step_executor=executor)
        await engine.execute(
            request_id="req_sm2",
            plan=[
                {"step": 1, "command": "research", "args": "A", "depends_on": []},
                {"step": 2, "command": "synthesize", "args": "B", "depends_on": [1]},
            ],
            agent_name="leader",
            device="leader",
        )

        assert "shared_memory_summary" in step2_payload
        assert "step_1_research" in step2_payload["shared_memory_summary"]

    @pytest.mark.asyncio
    async def test_shared_memory_isolated_per_campaign(self):
        """Memory resets between campaign runs on same engine."""
        async def executor(command, args, payload):
            return {"run": "data"}

        engine = CampaignEngine(step_executor=executor)

        # First run
        r1 = await engine.execute(
            request_id="run1",
            plan=[{"step": 1, "command": "research", "args": "", "depends_on": []}],
            agent_name="leader", device="leader",
        )
        assert len(r1.shared_memory) > 0

        # Second run should not see first run's data
        step2_payload = {}

        async def executor2(command, args, payload):
            step2_payload.update(payload)
            return {"run2": "data"}

        engine._execute_step = executor2
        await engine.execute(
            request_id="run2",
            plan=[{"step": 1, "command": "analyze", "args": "", "depends_on": []}],
            agent_name="leader", device="leader",
        )

        # shared_memory should be empty (no prior step in this run)
        assert step2_payload["shared_memory"] == {}

    @pytest.mark.asyncio
    async def test_shared_memory_in_result(self):
        """CampaignResult includes shared memory snapshot."""
        async def executor(command, args, payload):
            return {"value": 42}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_smr",
            plan=[{"step": 1, "command": "research", "args": "", "depends_on": []}],
            agent_name="leader", device="leader",
        )

        assert "step_1_research" in result.shared_memory
        assert result.shared_memory["step_1_research"]["result"]["value"] == 42


class TestRetryWithBackoff:
    """Test per-step retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        """Executor fails once then succeeds."""
        call_count = {"n": 0}

        async def executor(command, args, payload):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("transient failure")
            return {"ok": True}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_r1",
            plan=[{
                "step": 1, "command": "research", "args": "",
                "depends_on": [], "max_retries": 1, "retry_delay": 0.01,
            }],
            agent_name="leader", device="leader",
        )

        assert result.status == "completed"
        assert result.steps[0].retry_count == 1
        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_marks_failed(self):
        """All retries fail — step marked as failed."""
        call_count = {"n": 0}

        async def executor(command, args, payload):
            call_count["n"] += 1
            raise RuntimeError("permanent failure")

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_r2",
            plan=[{
                "step": 1, "command": "research", "args": "",
                "depends_on": [], "max_retries": 2, "retry_delay": 0.01,
            }],
            agent_name="leader", device="leader",
        )

        assert result.status == "failed"
        assert result.steps[0].status == StepStatus.FAILED
        assert call_count["n"] == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_retry_delay_capped_at_30s(self):
        """Delay should be capped at 30 seconds."""
        delays = []
        original_sleep = asyncio.sleep

        async def mock_sleep(duration):
            delays.append(duration)
            await original_sleep(0)  # don't actually wait

        # Monkey-patch asyncio.sleep temporarily
        import oas_core.campaign as campaign_mod
        old_sleep = asyncio.sleep
        campaign_mod.asyncio.sleep = mock_sleep

        try:
            async def executor(command, args, payload):
                raise RuntimeError("fail")

            engine = CampaignEngine(step_executor=executor)
            await engine.execute(
                request_id="req_r3",
                plan=[{
                    "step": 1, "command": "research", "args": "",
                    "depends_on": [], "max_retries": 3,
                    "retry_delay": 20.0, "retry_backoff": 3.0,
                }],
                agent_name="leader", device="leader",
            )

            # Delays: 20*3^0=20, 20*3^1=60->30, 20*3^2=180->30
            assert len(delays) == 3
            assert delays[0] == 20.0
            assert delays[1] == 30.0  # capped
            assert delays[2] == 30.0  # capped
        finally:
            campaign_mod.asyncio.sleep = old_sleep

    @pytest.mark.asyncio
    async def test_no_retry_by_default(self):
        """Without max_retries, step fails immediately."""
        call_count = {"n": 0}

        async def executor(command, args, payload):
            call_count["n"] += 1
            raise RuntimeError("fail")

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_r4",
            plan=[{"step": 1, "command": "research", "args": "", "depends_on": []}],
            agent_name="leader", device="leader",
        )

        assert result.steps[0].status == StepStatus.FAILED
        assert call_count["n"] == 1  # no retry


class TestCascadeFailure:
    """Test transitive failure propagation with reason chains."""

    @pytest.mark.asyncio
    async def test_cascade_failure_transitive(self):
        """4-step chain: step 1 fails → steps 2, 3, 4 cascade-fail."""
        async def executor(command, args, payload):
            if command == "step1":
                raise RuntimeError("API timeout")
            return {"ok": True}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_cf1",
            plan=[
                {"step": 1, "command": "step1", "args": "", "depends_on": []},
                {"step": 2, "command": "step2", "args": "", "depends_on": [1]},
                {"step": 3, "command": "step3", "args": "", "depends_on": [2]},
                {"step": 4, "command": "step4", "args": "", "depends_on": [3]},
            ],
            agent_name="leader", device="leader",
        )

        assert result.steps[0].status == StepStatus.FAILED
        assert result.steps[1].status == StepStatus.FAILED
        assert result.steps[2].status == StepStatus.FAILED
        assert result.steps[3].status == StepStatus.FAILED
        assert "Cascaded" in result.steps[1].error
        assert "Cascaded" in result.steps[3].error

    @pytest.mark.asyncio
    async def test_cascade_failure_diamond(self):
        """Diamond: 1→2, 1→3, 2→4, 3→4. Step 1 fails → all cascade."""
        async def executor(command, args, payload):
            if command == "root":
                raise RuntimeError("root failure")
            return {"ok": True}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_cf2",
            plan=[
                {"step": 1, "command": "root", "args": "", "depends_on": []},
                {"step": 2, "command": "left", "args": "", "depends_on": [1]},
                {"step": 3, "command": "right", "args": "", "depends_on": [1]},
                {"step": 4, "command": "merge", "args": "", "depends_on": [2, 3]},
            ],
            agent_name="leader", device="leader",
        )

        assert result.steps[0].status == StepStatus.FAILED
        for s in result.steps[1:]:
            assert s.status == StepStatus.FAILED

    @pytest.mark.asyncio
    async def test_cascade_failure_reason_chain_content(self):
        """Reason chain should contain source step info."""
        async def executor(command, args, payload):
            raise RuntimeError("boom")

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_cf3",
            plan=[
                {"step": 1, "command": "research", "args": "", "depends_on": []},
                {"step": 2, "command": "analyze", "args": "", "depends_on": [1]},
            ],
            agent_name="leader", device="leader",
        )

        chain = result.steps[1].failure_reason_chain
        assert len(chain) >= 1
        assert "research" in chain[0]
        assert "boom" in chain[0]

    @pytest.mark.asyncio
    async def test_independent_steps_not_affected_by_cascade(self):
        """Steps without failed dependencies should still complete."""
        async def executor(command, args, payload):
            if command == "bad":
                raise RuntimeError("fail")
            return {"ok": True}

        engine = CampaignEngine(step_executor=executor)
        result = await engine.execute(
            request_id="req_cf4",
            plan=[
                {"step": 1, "command": "bad", "args": "", "depends_on": []},
                {"step": 2, "command": "good", "args": "", "depends_on": []},  # independent
                {"step": 3, "command": "depends_bad", "args": "", "depends_on": [1]},
            ],
            agent_name="leader", device="leader",
        )

        assert result.steps[0].status == StepStatus.FAILED
        assert result.steps[1].status == StepStatus.COMPLETED  # independent
        assert result.steps[2].status == StepStatus.FAILED     # cascaded
