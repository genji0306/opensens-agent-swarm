"""E2E campaign test harness.

Tests the full campaign lifecycle: plan → approve → execute → visualize.
Uses mocked service backends so the test can run without a live cluster.

When the cluster is running, set E2E_LIVE=1 to hit real services.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Skip entire module if running against live cluster without services
LIVE_MODE = os.getenv("E2E_LIVE", "").lower() in ("1", "true", "yes")


# --- Mocked campaign plan ---

SAMPLE_PLAN = [
    {"step": 1, "command": "research", "args": "quantum dot electrodes", "depends_on": []},
    {"step": 2, "command": "doe", "args": "electrode coating factors", "depends_on": [1]},
    {"step": 3, "command": "simulate", "args": "impedance response model", "depends_on": [1]},
    {"step": 4, "command": "analyze", "args": "simulation results", "depends_on": [2, 3]},
    {"step": 5, "command": "synthesize", "args": "findings and recommendations", "depends_on": [4]},
]


class TestCampaignPlanValidation:
    """Validate campaign plan structure and DAG resolution."""

    def test_plan_has_required_fields(self):
        for step in SAMPLE_PLAN:
            assert "step" in step
            assert "command" in step
            assert "args" in step
            assert "depends_on" in step

    def test_plan_dependencies_are_valid(self):
        step_nums = {s["step"] for s in SAMPLE_PLAN}
        for step in SAMPLE_PLAN:
            for dep in step["depends_on"]:
                assert dep in step_nums, f"Step {step['step']} depends on non-existent step {dep}"
                assert dep < step["step"], f"Step {step['step']} depends on later step {dep}"

    def test_plan_commands_are_routable(self):
        from oas_core.campaign import CampaignEngine
        # All commands in the plan must be in the routing table
        valid_commands = {
            "research", "literature", "doe", "paper", "perplexity",
            "simulate", "analyze", "synthetic", "report-data", "autoresearch",
            "synthesize", "report", "notebooklm",
        }
        for step in SAMPLE_PLAN:
            assert step["command"] in valid_commands, f"Unknown command: {step['command']}"

    def test_plan_dag_is_acyclic(self):
        """Verify the plan has no circular dependencies."""
        graph: dict[int, list[int]] = {}
        for step in SAMPLE_PLAN:
            graph[step["step"]] = step["depends_on"]

        visited: set[int] = set()
        path: set[int] = set()

        def has_cycle(node: int) -> bool:
            if node in path:
                return True
            if node in visited:
                return False
            visited.add(node)
            path.add(node)
            for dep in graph.get(node, []):
                if has_cycle(dep):
                    return True
            path.discard(node)
            return False

        for step_num in graph:
            assert not has_cycle(step_num), f"Cycle detected involving step {step_num}"


class TestCampaignExecution:
    """Test campaign execution engine with mocked step executor."""

    @pytest.mark.asyncio
    async def test_campaign_executes_all_steps(self):
        from oas_core.campaign import CampaignEngine

        executed: list[str] = []

        async def mock_executor(command, args, payload):
            executed.append(command)
            return {"status": "ok", "result": f"Completed {command}"}

        engine = CampaignEngine(step_executor=mock_executor)
        result = await engine.execute(
            request_id="e2e-test-001",
            plan=SAMPLE_PLAN,
            agent_name="E2ETest",
            device="leader",
        )

        assert result.status == "completed"
        assert len(result.completed_steps) == 5
        assert len(result.failed_steps) == 0
        # All commands from plan should have executed
        for step in SAMPLE_PLAN:
            assert step["command"] in executed

    @pytest.mark.asyncio
    async def test_campaign_handles_step_failure(self):
        from oas_core.campaign import CampaignEngine

        async def failing_executor(command, args, payload):
            if command == "simulate":
                raise RuntimeError("Simulation crashed")
            return {"status": "ok"}

        engine = CampaignEngine(step_executor=failing_executor)
        result = await engine.execute(
            request_id="e2e-test-002",
            plan=SAMPLE_PLAN,
            agent_name="E2ETest",
            device="leader",
        )

        # Step 3 (simulate) fails, step 4 (analyze depends on 3) should skip
        assert len(result.failed_steps) >= 1
        assert "simulate" in [s.command for s in result.failed_steps]

    @pytest.mark.asyncio
    async def test_campaign_respects_parallel_limit(self):
        from oas_core.campaign import CampaignEngine
        import time

        concurrent = {"max": 0, "current": 0}

        async def tracking_executor(command, args, payload):
            import asyncio
            concurrent["current"] += 1
            concurrent["max"] = max(concurrent["max"], concurrent["current"])
            await asyncio.sleep(0.05)
            concurrent["current"] -= 1
            return {"status": "ok"}

        engine = CampaignEngine(
            step_executor=tracking_executor,
            max_parallel=2,
        )
        # Use a plan with 3 independent steps
        parallel_plan = [
            {"step": 1, "command": "research", "args": "a", "depends_on": []},
            {"step": 2, "command": "literature", "args": "b", "depends_on": []},
            {"step": 3, "command": "doe", "args": "c", "depends_on": []},
        ]
        result = await engine.execute(
            request_id="e2e-test-003",
            plan=parallel_plan,
            agent_name="E2ETest",
            device="leader",
        )

        assert result.status == "completed"
        assert concurrent["max"] <= 2  # Should respect max_parallel


class TestDRVPEventEmission:
    """Verify DRVP events are emitted during campaign execution."""

    @pytest.mark.asyncio
    async def test_campaign_emits_step_events(self):
        from oas_core.campaign import CampaignEngine
        from oas_core.protocols.drvp import DRVPEvent

        emitted_events: list[DRVPEvent] = []

        async def capture_emit(event: DRVPEvent):
            emitted_events.append(event)

        async def ok_executor(command, args, payload):
            return {"status": "ok"}

        with patch("oas_core.campaign.emit", side_effect=capture_emit):
            engine = CampaignEngine(step_executor=ok_executor)
            await engine.execute(
                request_id="e2e-drvp-001",
                plan=SAMPLE_PLAN[:2],  # Just first 2 steps
                agent_name="E2ETest",
                device="leader",
            )

        # Should have emitted step.started and step.completed for each step
        event_types = [e.event_type.value for e in emitted_events]
        assert "campaign.step.started" in event_types
        assert "campaign.step.completed" in event_types


class TestKnowledgeGraphIntegration:
    """Test research knowledge graph schema and operations."""

    @pytest.mark.asyncio
    async def test_slugify(self):
        from oas_core.memory import _slugify
        assert _slugify("Quantum Dot Electrodes") == "quantum-dot-electrodes"
        assert _slugify("MnO2/Carbon Nano!tubes") == "mno2carbon-nanotubes"
        assert _slugify("  spaces  ") == "spaces"

    @pytest.mark.asyncio
    async def test_store_research_builds_uri(self):
        from oas_core.memory import MemoryClient, SCOPE_RESEARCH

        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock) as mock_write, \
             patch.object(client, "link", new_callable=AsyncMock):
            uri = await client.store_research(
                topic="Quantum Dots",
                findings={"summary": "QD are useful"},
                subtopic="electrode coatings",
                agent_name="Academic",
                request_id="req-001",
            )

        assert uri == f"{SCOPE_RESEARCH}/quantum-dots/electrode-coatings"
        mock_write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_build_knowledge_context(self):
        from oas_core.memory import MemoryClient

        client = MemoryClient("http://mock:1933")
        mock_results = [{"uri": "viking://research/test", "score": 0.9}]
        with patch.object(client, "search", new_callable=AsyncMock, return_value=mock_results), \
             patch.object(client, "find_related_sessions", new_callable=AsyncMock, return_value=[]):
            ctx = await client.build_knowledge_context("quantum dots")

        assert ctx["query"] == "quantum dots"
        assert ctx["total_sources"] >= 1
        assert "research" in ctx
        assert "experiments" in ctx
        assert "related_sessions" in ctx


class TestSandboxManager:
    """Test NemoClaw sandbox manager interface."""

    @pytest.mark.asyncio
    async def test_create_and_destroy(self):
        from oas_core.sandbox import SandboxManager

        manager = SandboxManager()
        sandbox_id = await manager.create("test-sandbox")
        assert sandbox_id == "test-sandbox"
        assert "test-sandbox" in manager.active_sandboxes

        await manager.destroy("test-sandbox")
        assert "test-sandbox" not in manager.active_sandboxes

    @pytest.mark.asyncio
    async def test_run_code_python(self):
        from oas_core.sandbox import SandboxManager

        manager = SandboxManager()
        await manager.create("code-test")
        result = await manager.run_code("code-test", "print('hello world')", timeout=10)

        assert result.status == "ok"
        assert "hello world" in result.stdout
        assert result.exit_code == 0

        await manager.destroy("code-test")

    @pytest.mark.asyncio
    async def test_run_code_timeout(self):
        from oas_core.sandbox import SandboxManager

        manager = SandboxManager()
        await manager.create("timeout-test")
        result = await manager.run_code(
            "timeout-test",
            "import time; time.sleep(60)",
            timeout=1,
        )

        assert result.status == "timeout"
        await manager.destroy("timeout-test")

    @pytest.mark.asyncio
    async def test_run_code_missing_sandbox(self):
        from oas_core.sandbox import SandboxManager

        manager = SandboxManager()
        result = await manager.run_code("nonexistent", "print('hi')")
        assert result.status == "error"


class TestDeepAgentRunner:
    """Test deepagents integration wrapper."""

    def test_result_to_dict(self):
        from oas_core.deep_agent import DeepAgentResult

        result = DeepAgentResult(
            status="ok",
            output="Analysis complete",
            artifacts=["report.pdf"],
            token_usage={"input": 1000, "output": 500},
            duration_seconds=12.5,
        )
        d = result.to_dict()
        assert d["status"] == "ok"
        assert d["artifacts"] == ["report.pdf"]
        assert d["duration_seconds"] == 12.5

    @pytest.mark.asyncio
    async def test_runner_unavailable(self):
        from oas_core.deep_agent import DeepAgentRunner

        with patch("oas_core.deep_agent._check_deep_agent_available", return_value=False):
            runner = DeepAgentRunner()
            result = await runner.run("test task")
            assert result.status == "error"
            assert "not installed" in result.output


    # NOTE: Boost command tests are in cluster/tests/test_dispatch_hooks.py
    # because they require `shared.models` which is only on the cluster pythonpath.
