"""Tests for leader.dispatch swarm integration — smart dispatch path."""
import sys
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models import Task, TaskType, TaskResult


class TestSlashCommandFastPath:
    """Slash commands should always use ROUTING_TABLE, never the swarm."""

    def test_parse_command_extracts_slash(self):
        from leader.dispatch import parse_command
        cmd, args = parse_command("/research quantum computing")
        assert cmd == "research"
        assert args == "quantum computing"

    def test_parse_command_returns_none_for_freeform(self):
        from leader.dispatch import parse_command
        cmd, args = parse_command("What is quantum computing?")
        assert cmd is None
        assert args == "What is quantum computing?"

    async def test_slash_command_bypasses_swarm(self):
        """A /research command should route via ROUTING_TABLE, not swarm."""
        from leader.dispatch import handle

        task = Task(
            task_id="t_slash",
            task_type=TaskType.PLAN,
            payload={"text": "/research quantum sensors"},
        )

        with patch("leader.dispatch.get_swarm_app", new_callable=AsyncMock) as mock_get:
            with patch("leader.dispatch._node_url", return_value=None):
                result = await handle(task)

            # Swarm should never be called for slash commands
            mock_get.assert_not_called()

        assert result.status == "ok"
        assert result.result["action"] == "dispatch"
        assert result.result["route"]["skill"] == "darklab-research"

    async def test_status_command_returns_status(self):
        from leader.dispatch import handle

        task = Task(
            task_id="t_status",
            task_type=TaskType.PLAN,
            payload={"text": "/status"},
        )
        result = await handle(task)
        assert result.result["action"] == "status"


class TestSwarmDispatch:
    """Free-form text should try the swarm before plan_campaign."""

    async def test_freeform_uses_swarm_when_available(self):
        """When swarm is available, free-form text goes through _dispatch_via_swarm."""
        from leader.dispatch import handle

        expected_result = TaskResult(
            task_id="t_free",
            agent_name="research",
            status="ok",
            result={"action": "swarm", "agent": "research", "data": {"status": "ok"}},
        )

        mock_swarm = MagicMock()

        with patch("leader.dispatch.get_swarm_app", new_callable=AsyncMock, return_value=mock_swarm):
            with patch("leader.dispatch._dispatch_via_swarm", new_callable=AsyncMock, return_value=expected_result):
                task = Task(
                    task_id="t_free",
                    task_type=TaskType.PLAN,
                    payload={"text": "Investigate polymer membrane degradation"},
                )
                result = await handle(task)

        assert result.status == "ok"
        assert result.result["action"] == "swarm"
        assert result.result["agent"] == "research"

    async def test_freeform_falls_back_to_campaign_when_no_swarm(self):
        from leader.dispatch import handle

        task = Task(
            task_id="t_nocampaign",
            task_type=TaskType.PLAN,
            payload={"text": "Investigate polymer degradation"},
        )

        mock_plan = [{"step": 1, "command": "research", "args": "polymers", "depends_on": []}]

        with patch("leader.dispatch.get_swarm_app", new_callable=AsyncMock, return_value=None):
            with patch("leader.dispatch.plan_campaign", new_callable=AsyncMock, return_value=mock_plan):
                result = await handle(task)

        assert result.result["action"] == "campaign"
        assert result.result["plan"] == mock_plan

    async def test_swarm_error_falls_back_to_campaign(self):
        """If _dispatch_via_swarm raises, handle() falls back to plan_campaign."""
        from leader.dispatch import handle

        mock_swarm = MagicMock()

        task = Task(
            task_id="t_err",
            task_type=TaskType.PLAN,
            payload={"text": "Something complex"},
        )

        mock_plan = [{"step": 1, "command": "research", "args": "complex", "depends_on": []}]

        with patch("leader.dispatch.get_swarm_app", new_callable=AsyncMock, return_value=mock_swarm):
            with patch("leader.dispatch._dispatch_via_swarm", new_callable=AsyncMock, side_effect=RuntimeError("LLM timeout")):
                with patch("leader.dispatch.plan_campaign", new_callable=AsyncMock, return_value=mock_plan):
                    result = await handle(task)

        assert result.result["action"] == "campaign"


class TestDispatchViaSwarm:
    """Test _dispatch_via_swarm with mocked langchain imports."""

    @pytest.fixture(autouse=True)
    def mock_langchain(self):
        """Inject a mock langchain_core.messages module."""
        mock_messages = MagicMock()
        mock_messages.HumanMessage = MagicMock()

        modules = {
            "langchain_core": MagicMock(),
            "langchain_core.messages": mock_messages,
        }
        with patch.dict(sys.modules, modules):
            yield mock_messages

    async def test_extracts_last_ai_message(self, mock_langchain):
        from leader.dispatch import _dispatch_via_swarm

        mock_ai = MagicMock()
        mock_ai.type = "ai"
        mock_ai.content = '{"analysis": "done"}'
        mock_ai.name = "analyze"

        mock_swarm = MagicMock()
        mock_swarm.ainvoke = AsyncMock(return_value={"messages": [mock_ai]})
        task = Task(task_id="t_ai", task_type=TaskType.PLAN, payload={"text": "test"})

        result = await _dispatch_via_swarm(mock_swarm, task, "test query")

        assert result.agent_name == "analyze"
        assert result.result["action"] == "swarm"
        assert result.result["data"]["analysis"] == "done"

    async def test_handles_non_json_content(self, mock_langchain):
        from leader.dispatch import _dispatch_via_swarm

        mock_ai = MagicMock()
        mock_ai.type = "ai"
        mock_ai.content = "Plain text result from agent"
        mock_ai.name = "research"

        mock_swarm = MagicMock()
        mock_swarm.ainvoke = AsyncMock(return_value={"messages": [mock_ai]})
        task = Task(task_id="t_raw", task_type=TaskType.PLAN, payload={"text": "q"})

        result = await _dispatch_via_swarm(mock_swarm, task, "some query")

        assert result.result["data"]["raw"] == "Plain text result from agent"

    async def test_empty_messages_returns_empty_content(self, mock_langchain):
        from leader.dispatch import _dispatch_via_swarm

        mock_swarm = MagicMock()
        mock_swarm.ainvoke = AsyncMock(return_value={"messages": []})
        task = Task(task_id="t_empty", task_type=TaskType.PLAN, payload={"text": "q"})

        result = await _dispatch_via_swarm(mock_swarm, task, "query")

        assert result.agent_name == "swarm"
        assert result.result["data"]["raw"] == ""

    async def test_passes_thread_id(self, mock_langchain):
        from leader.dispatch import _dispatch_via_swarm

        mock_ai = MagicMock()
        mock_ai.type = "ai"
        mock_ai.content = "{}"
        mock_ai.name = "test"

        mock_swarm = MagicMock()
        mock_swarm.ainvoke = AsyncMock(return_value={"messages": [mock_ai]})
        task = Task(task_id="t_thread", task_type=TaskType.PLAN, payload={"text": "q"})

        await _dispatch_via_swarm(mock_swarm, task, "query")

        call_kwargs = mock_swarm.ainvoke.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config["configurable"]["thread_id"] == "t_thread"


class TestGetSwarmApp:
    @pytest.fixture(autouse=True)
    def reset_swarm_state(self):
        """Reset the swarm singleton between tests."""
        import leader.dispatch as mod
        orig_app = mod._swarm_app
        orig_failed = mod._swarm_init_failed
        orig_lock = mod._swarm_lock
        mod._swarm_app = None
        mod._swarm_init_failed = False
        mod._swarm_lock = None
        yield mod
        mod._swarm_app = orig_app
        mod._swarm_init_failed = orig_failed
        mod._swarm_lock = orig_lock

    async def test_returns_none_when_swarm_unavailable(self, reset_swarm_state):
        mod = reset_swarm_state

        mock_swarm_module = MagicMock()
        mock_swarm_module.SWARM_AVAILABLE = False

        with patch.dict(sys.modules, {"oas_core.swarm": mock_swarm_module}):
            result = await mod.get_swarm_app()

        assert result is None
        assert mod._swarm_init_failed is True

    async def test_caches_swarm_after_init(self, reset_swarm_state):
        mod = reset_swarm_state
        mock_graph = MagicMock()

        mock_swarm_module = MagicMock()
        mock_swarm_module.SWARM_AVAILABLE = True
        mock_swarm_module.build_swarm = MagicMock(return_value=mock_graph)

        mock_registry_module = MagicMock()
        mock_registry_module.get_agent_registry = MagicMock(return_value={"test": {}})

        modules = {
            "oas_core.swarm": mock_swarm_module,
            "leader.swarm_registry": mock_registry_module,
        }

        with patch.dict(sys.modules, modules):
            result = await mod.get_swarm_app()

        assert result is mock_graph

        # Second call returns cached value (no sys.modules patch needed)
        result2 = await mod.get_swarm_app()
        assert result2 is mock_graph

    async def test_init_error_sets_failed_flag(self, reset_swarm_state):
        mod = reset_swarm_state

        mock_swarm_module = MagicMock()
        mock_swarm_module.SWARM_AVAILABLE = True
        mock_swarm_module.build_swarm = MagicMock(side_effect=RuntimeError("init boom"))

        mock_registry_module = MagicMock()
        mock_registry_module.get_agent_registry = MagicMock(return_value={})

        modules = {
            "oas_core.swarm": mock_swarm_module,
            "leader.swarm_registry": mock_registry_module,
        }

        with patch.dict(sys.modules, modules):
            result = await mod.get_swarm_app()

        assert result is None
        assert mod._swarm_init_failed is True

        # Subsequent call should skip init entirely
        result2 = await mod.get_swarm_app()
        assert result2 is None


def _mock_handler_modules():
    """Create mock modules for all agent handlers to avoid heavy imports (numpy etc)."""
    mock_modules = {}
    agent_modules = [
        "academic.research", "academic.literature", "academic.doe",
        "academic.paper", "academic.perplexity",
        "experiment.simulation", "experiment.analysis", "experiment.synthetic",
        "experiment.report_data", "experiment.autoresearch",
        "leader.synthesis", "leader.media_gen", "leader.notebooklm",
    ]
    for mod_name in agent_modules:
        m = MagicMock()
        m.handle = AsyncMock()
        mock_modules[mod_name] = m
    # Also mock numpy/scipy/etc that handlers import
    for dep in ["numpy", "scipy", "scipy.stats", "matplotlib", "matplotlib.pyplot"]:
        if dep not in sys.modules:
            mock_modules[dep] = MagicMock()
    return mock_modules


class TestSwarmRegistry:
    @pytest.fixture(autouse=True)
    def mock_deps(self):
        """Mock heavy dependencies so handler imports succeed."""
        mocks = _mock_handler_modules()
        with patch.dict(sys.modules, mocks):
            yield

    def test_registry_returns_dict(self):
        from leader.swarm_registry import get_agent_registry
        registry = get_agent_registry()
        assert isinstance(registry, dict)
        assert len(registry) >= 12

    def test_all_entries_have_required_keys(self):
        from leader.swarm_registry import get_agent_registry
        registry = get_agent_registry()

        for name, spec in registry.items():
            assert "handler" in spec, f"{name} missing handler"
            assert "task_type" in spec, f"{name} missing task_type"
            assert "device" in spec, f"{name} missing device"
            assert "description" in spec, f"{name} missing description"
            assert callable(spec["handler"]), f"{name} handler not callable"
            assert spec["device"] in ("academic", "experiment", "leader"), (
                f"{name} has unexpected device: {spec['device']}"
            )

    def test_known_agents_present(self):
        from leader.swarm_registry import get_agent_registry
        registry = get_agent_registry()

        expected = ["research", "literature", "doe", "paper", "perplexity",
                    "simulate", "analyze", "synthetic", "report_data",
                    "autoresearch", "synthesize", "media_gen"]
        for agent in expected:
            assert agent in registry, f"Missing expected agent: {agent}"


class TestHealthSwarmField:
    def test_health_response_has_swarm_field(self):
        from leader.serve import HealthResponse
        resp = HealthResponse()
        assert hasattr(resp, "swarm_available")
        assert resp.swarm_available is False
