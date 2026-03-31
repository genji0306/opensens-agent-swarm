"""Tests for the DeerFlow adapter (core/oas_core/adapters/deerflow.py)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeStreamEvent:
    type: str
    data: dict


def _make_mock_client(output_text: str = "Research result") -> MagicMock:
    """Create a mock DeerFlowClient with streaming support.

    The adapter processes "values" events containing a "messages" list of
    message dicts.  Each message has "type", "content", and optionally
    "tool_calls".  The adapter picks the last AI message without tool_calls.
    """
    client = MagicMock()
    client.stream.return_value = iter([
        FakeStreamEvent("values", {
            "messages": [{"type": "ai", "content": output_text}],
        }),
        FakeStreamEvent("end", {}),
    ])
    client.list_models.return_value = {"models": [{"name": "test-model"}]}
    client.list_skills.return_value = {"skills": [{"name": "research"}]}
    client.get_memory_status.return_value = {"enabled": True}
    client.list_uploads.return_value = {"files": [], "count": 0}
    client.upload_files.return_value = {"success": True, "files": []}
    return client


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------

class TestImportGuard:
    """DEERFLOW_AVAILABLE reflects whether deerflow-harness is installed."""

    def test_deerflow_available_is_bool(self):
        from oas_core.adapters.deerflow import DEERFLOW_AVAILABLE
        assert isinstance(DEERFLOW_AVAILABLE, bool)

    def test_default_config_path(self):
        from oas_core.adapters.deerflow import DEFAULT_CONFIG_PATH
        assert str(DEFAULT_CONFIG_PATH).endswith("deerflow/config.yaml")


# ---------------------------------------------------------------------------
# Adapter construction
# ---------------------------------------------------------------------------

class TestAdapterConstruction:
    """DeerFlowAdapter init and lazy client creation."""

    def test_raises_when_not_available(self):
        with patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", False):
            from oas_core.adapters.deerflow import DeerFlowAdapter
            with pytest.raises(ImportError, match="deerflow-harness"):
                DeerFlowAdapter()

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    def test_lazy_init(self, mock_cls):
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter(model_name="test-model")
        # Client not created until first use
        assert adapter._client is None
        mock_cls.return_value = _make_mock_client()
        client = adapter._get_client()
        assert client is not None
        mock_cls.assert_called_once()

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    def test_custom_config_path(self, mock_cls):
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter(config_path="/custom/config.yaml")
        assert str(adapter._config_path) == "/custom/config.yaml"


# ---------------------------------------------------------------------------
# run_research
# ---------------------------------------------------------------------------

class TestRunResearch:
    """DeerFlowAdapter.run_research() streaming and DRVP integration."""

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    @pytest.mark.asyncio
    async def test_basic_research(self, mock_cls):
        mock_cls.return_value = _make_mock_client("Finding: quantum effects observed")
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()

        result = await adapter.run_research("req-1", "quantum computing survey")

        assert result["output"] == "Finding: quantum effects observed"
        assert result["thread_id"] == "req-1"
        assert isinstance(result["artifacts"], list)

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    @pytest.mark.asyncio
    async def test_custom_thread_id(self, mock_cls):
        mock_cls.return_value = _make_mock_client()
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()

        result = await adapter.run_research("req-2", "test", thread_id="custom-thread")

        assert result["thread_id"] == "custom-thread"

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    @pytest.mark.asyncio
    async def test_file_upload(self, mock_cls):
        client = _make_mock_client()
        mock_cls.return_value = client
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()

        await adapter.run_research("req-3", "analyze", files=["/tmp/data.csv"])

        client.upload_files.assert_called_once_with("req-3", ["/tmp/data.csv"])

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    @pytest.mark.asyncio
    async def test_multi_step_output(self, mock_cls):
        """Last AI message without tool_calls wins as output."""
        client = MagicMock()
        client.stream.return_value = iter([
            FakeStreamEvent("values", {
                "messages": [{"type": "ai", "content": "Step 1"}],
            }),
            FakeStreamEvent("values", {
                "messages": [{"type": "ai", "content": "Step 2"}],
            }),
            FakeStreamEvent("values", {
                "messages": [{"type": "ai", "content": "Step 3 final"}],
            }),
            FakeStreamEvent("end", {}),
        ])
        client.list_uploads.return_value = {"files": [], "count": 0}
        mock_cls.return_value = client
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()

        result = await adapter.run_research("req-4", "multi-step")

        # Adapter picks last clean AI message — "Step 3 final"
        assert "Step 3" in result["output"]

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    @pytest.mark.asyncio
    async def test_stream_error_emits_agent_error(self, mock_cls):
        """When streaming fails, an agent.error DRVP event is emitted."""
        client = MagicMock()
        client.stream.side_effect = RuntimeError("connection lost")
        mock_cls.return_value = client
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()

        with pytest.raises(RuntimeError, match="connection lost"):
            await adapter.run_research("req-5", "failing query")

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    @pytest.mark.asyncio
    async def test_non_ai_messages_ignored(self, mock_cls):
        """Non-AI messages (system, human) are not included in output."""
        client = MagicMock()
        client.stream.return_value = iter([
            FakeStreamEvent("values", {
                "messages": [
                    {"type": "human", "content": "user input"},
                    {"type": "ai", "content": "AI response"},
                ],
            }),
            FakeStreamEvent("end", {}),
        ])
        client.list_uploads.return_value = {"files": [], "count": 0}
        mock_cls.return_value = client
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()

        result = await adapter.run_research("req-6", "test")

        assert result["output"] == "AI response"


# ---------------------------------------------------------------------------
# Convenience methods
# ---------------------------------------------------------------------------

class TestConvenienceMethods:
    """list_models, list_skills, get_memory_status, reset."""

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    def test_list_models(self, mock_cls):
        mock_cls.return_value = _make_mock_client()
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()
        models = adapter.list_models()
        assert "models" in models

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    def test_list_skills(self, mock_cls):
        mock_cls.return_value = _make_mock_client()
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()
        skills = adapter.list_skills()
        assert "skills" in skills

    @patch("oas_core.adapters.deerflow.DEERFLOW_AVAILABLE", True)
    @patch("oas_core.adapters.deerflow.DeerFlowClient", create=True)
    def test_reset(self, mock_cls):
        client = _make_mock_client()
        mock_cls.return_value = client
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()
        adapter._get_client()
        adapter.reset()
        assert adapter._client is None
        client.reset_agent.assert_called_once()


# ---------------------------------------------------------------------------
# DRVP event emission
# ---------------------------------------------------------------------------

class TestDRVPEmission:
    """_emit_event helper is best-effort and never raises."""

    @pytest.mark.asyncio
    async def test_emit_event_no_crash_without_drvp(self):
        """Even if DRVP is not configured, _emit_event doesn't raise."""
        from oas_core.adapters.deerflow import DeerFlowAdapter
        # Should silently succeed (DRVP emit is best-effort)
        await DeerFlowAdapter._emit_event(
            "agent.activated",
            request_id="test",
            agent_name="deerflow",
            device="leader",
            payload={"test": True},
        )

    @pytest.mark.asyncio
    async def test_emit_event_invalid_type_no_crash(self):
        """Invalid event type strings are silently ignored."""
        from oas_core.adapters.deerflow import DeerFlowAdapter
        await DeerFlowAdapter._emit_event(
            "invalid.event.type",
            request_id="test",
            agent_name="deerflow",
            device="leader",
            payload={},
        )
