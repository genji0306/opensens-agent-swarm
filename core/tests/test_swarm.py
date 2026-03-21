"""Tests for oas_core.swarm — LangGraph swarm builder and node wrapper."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _swarm_available() -> bool:
    """Check if langgraph-swarm is installed for conditional test skipping."""
    try:
        from oas_core.swarm import SWARM_AVAILABLE
        return SWARM_AVAILABLE
    except ImportError:
        return False


_skip_no_swarm = pytest.mark.skipif(
    not _swarm_available(), reason="langgraph-swarm not installed"
)


class TestSwarmAvailable:
    def test_import_flag_exists(self):
        from oas_core.swarm import SWARM_AVAILABLE
        assert isinstance(SWARM_AVAILABLE, bool)

    def test_module_exports(self):
        import oas_core.swarm as mod
        assert hasattr(mod, "build_swarm")
        assert hasattr(mod, "wrap_agent_as_node")
        assert hasattr(mod, "SWARM_AVAILABLE")


class TestWrapAgentAsNode:
    @pytest.fixture
    def mock_handler(self):
        result = MagicMock()
        result.model_dump_json.return_value = '{"status": "ok", "data": "test"}'
        handler = AsyncMock(return_value=result)
        return handler

    @_skip_no_swarm
    async def test_wraps_handler_as_node(self, mock_handler):
        from oas_core.swarm import wrap_agent_as_node

        node_fn = wrap_agent_as_node(
            handler=mock_handler,
            agent_name="test_agent",
            task_type_value="research",
            device="academic",
        )

        assert callable(node_fn)
        assert node_fn.__name__ == "test_agent"

    @_skip_no_swarm
    async def test_node_extracts_human_message(self, mock_handler):
        from oas_core.swarm import wrap_agent_as_node
        from langchain_core.messages import HumanMessage

        node_fn = wrap_agent_as_node(
            handler=mock_handler,
            agent_name="test_agent",
            task_type_value="research",
            device="academic",
        )

        with patch("oas_core.swarm._is_cluster_context", return_value=False):
            state = {
                "messages": [HumanMessage(content="test query")],
                "request_id": "req_123",
            }

            with patch("oas_core.protocols.drvp.emit", new_callable=AsyncMock):
                result = await node_fn(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert msg.name == "test_agent"
        assert "ok" in msg.content

        mock_handler.assert_called_once()
        task_arg = mock_handler.call_args[0][0]
        assert task_arg.payload["text"] == "test query"

    @_skip_no_swarm
    async def test_node_handles_handler_error(self):
        from oas_core.swarm import wrap_agent_as_node
        from langchain_core.messages import HumanMessage

        failing_handler = AsyncMock(side_effect=RuntimeError("boom"))
        node_fn = wrap_agent_as_node(
            handler=failing_handler,
            agent_name="broken",
            task_type_value="research",
            device="academic",
        )

        with patch("oas_core.swarm._is_cluster_context", return_value=False):
            state = {"messages": [HumanMessage(content="fail")], "request_id": "r1"}
            with patch("oas_core.protocols.drvp.emit", new_callable=AsyncMock):
                result = await node_fn(state)

        msg = result["messages"][0]
        assert "error" in msg.content
        assert "boom" in msg.content


class TestBuildSwarm:
    @_skip_no_swarm
    async def test_builds_compiled_graph(self):
        from oas_core.swarm import build_swarm

        mock_handler = AsyncMock()
        registry = {
            "test_agent": {
                "handler": mock_handler,
                "task_type": "research",
                "device": "academic",
                "description": "Test agent for unit tests.",
            },
        }

        with patch("oas_core.swarm.ChatAnthropic") as MockLLM:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm
            MockLLM.return_value = mock_llm

            graph = build_swarm(
                agent_registry=registry,
                anthropic_api_key="test-key",
            )

        assert hasattr(graph, "ainvoke")

    def test_build_swarm_raises_without_langgraph(self):
        """When SWARM_AVAILABLE is False, build_swarm raises ImportError."""
        from oas_core import swarm

        original = swarm.SWARM_AVAILABLE
        try:
            swarm.SWARM_AVAILABLE = False
            with pytest.raises(ImportError, match="langgraph-swarm"):
                swarm.build_swarm({})
        finally:
            swarm.SWARM_AVAILABLE = original


class TestDarkLabSwarmState:
    @_skip_no_swarm
    def test_state_has_request_id(self):
        from oas_core.swarm import DarkLabSwarmState
        assert "request_id" in DarkLabSwarmState.__annotations__


class TestHandoff:
    def test_import_guard(self):
        """handoff module should import without langgraph."""
        import oas_core.handoff
        assert hasattr(oas_core.handoff, "create_governed_handoff")

    @_skip_no_swarm
    def test_create_governed_handoff(self):
        from oas_core.handoff import create_governed_handoff

        tool = create_governed_handoff(
            agent_name="research",
            description="Test research agent",
            from_agent="leader",
            device="leader",
        )
        assert tool.metadata["governed"] is True
        assert tool.metadata["from_agent"] == "leader"
        assert "transfer" in tool.name.lower() or "research" in tool.name.lower()

    @_skip_no_swarm
    def test_governed_handoff_with_paperclip(self):
        from oas_core.handoff import create_governed_handoff

        mock_client = MagicMock()
        tool = create_governed_handoff(
            agent_name="analyze",
            description="Test analysis agent",
            paperclip_client=mock_client,
            company_id="comp_test",
        )
        assert tool.metadata["paperclip_client"] is mock_client
        assert tool.metadata["company_id"] == "comp_test"

    def test_governed_handoff_raises_without_langgraph(self):
        """When langgraph not available, should raise ImportError."""
        import oas_core.handoff as mod

        original = mod._SWARM_AVAILABLE
        try:
            mod._SWARM_AVAILABLE = False
            with pytest.raises(ImportError, match="langgraph-swarm"):
                mod.create_governed_handoff("test", "desc")
        finally:
            mod._SWARM_AVAILABLE = original
