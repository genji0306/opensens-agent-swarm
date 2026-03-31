"""Tests for the DeerFlow research handler (cluster/agents/experiment/deerflow_research.py)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from shared.models import Task, TaskType


@dataclass
class FakeStreamEvent:
    type: str
    data: dict


def _make_task(query: str = "test query", **extra_payload) -> Task:
    payload = {"query": query, **extra_payload}
    return Task(task_type=TaskType.DEERFLOW, payload=payload)


def _make_mock_client(output: str = "Research output") -> MagicMock:
    client = MagicMock()
    client.stream.return_value = iter([
        FakeStreamEvent("messages-tuple", {"type": "ai", "content": output}),
        FakeStreamEvent("end", {}),
    ])
    client.list_uploads.return_value = {"files": [], "count": 0}
    client.upload_files.return_value = {"success": True}
    return client


def _build_mock_adapter_module(*, available: bool = True, client: MagicMock | None = None):
    """Build a mock oas_core.adapters.deerflow module for sys.modules injection."""
    mod = ModuleType("oas_core.adapters.deerflow")
    mod.DEERFLOW_AVAILABLE = available  # type: ignore[attr-defined]

    if available and client is not None:
        class MockDeerFlowAdapter:
            def __init__(self, *, model_name=None, thinking_enabled=True, subagent_enabled=True, **kw):
                self.model_name = model_name

            async def run_research(self, request_id, query, *, agent_name="deerflow",
                                   device="leader", thread_id=None, files=None):
                import asyncio
                output_parts = []
                for event in client.stream(query, thread_id=thread_id or request_id):
                    if event.type == "messages-tuple":
                        data = event.data
                        if isinstance(data, dict) and data.get("type") == "ai":
                            content = data.get("content", "")
                            if content:
                                output_parts.append(str(content))

                if files:
                    client.upload_files(thread_id or request_id, files)

                return {
                    "output": "\n".join(output_parts),
                    "thread_id": thread_id or request_id,
                    "artifacts": [],
                }

        mod.DeerFlowAdapter = MockDeerFlowAdapter  # type: ignore[attr-defined]
    elif available:
        class RaisingAdapter:
            def __init__(self, **kw):
                pass

            async def run_research(self, *a, **kw):
                raise RuntimeError("mock error")

        mod.DeerFlowAdapter = RaisingAdapter  # type: ignore[attr-defined]

    return mod


def _inject_oas_modules(adapter_mod):
    """Inject mock oas_core modules into sys.modules for cluster test isolation."""
    mods = {
        "oas_core": ModuleType("oas_core"),
        "oas_core.adapters": ModuleType("oas_core.adapters"),
        "oas_core.adapters.deerflow": adapter_mod,
        "oas_core.model_router": ModuleType("oas_core.model_router"),
    }
    return mods


# ---------------------------------------------------------------------------
# TaskType registration
# ---------------------------------------------------------------------------

class TestTaskTypeRegistration:
    """DEERFLOW TaskType is properly registered."""

    def test_deerflow_task_type_exists(self):
        assert TaskType.DEERFLOW == "deerflow"
        assert TaskType.DEERFLOW.value == "deerflow"

    def test_deerflow_in_task_types(self):
        all_types = [t.value for t in TaskType]
        assert "deerflow" in all_types


# ---------------------------------------------------------------------------
# Handler: happy path
# ---------------------------------------------------------------------------

class TestDeerFlowHandler:
    """Tests for experiment.deerflow_research.handle()."""

    @pytest.mark.asyncio
    async def test_basic_handle(self):
        client = _make_mock_client("quantum result")
        adapter_mod = _build_mock_adapter_module(available=True, client=client)
        mods = _inject_oas_modules(adapter_mod)

        with patch.dict(sys.modules, mods):
            # Force reimport to pick up mocked modules
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)
            result = await dfr.handle(_make_task("quantum computing survey"))

        assert result.status == "ok"
        assert result.agent_name == "DeerFlowResearch"
        assert "quantum result" in result.result.get("output", "")

    @pytest.mark.asyncio
    async def test_missing_query_returns_error(self):
        adapter_mod = _build_mock_adapter_module(available=True, client=_make_mock_client())
        mods = _inject_oas_modules(adapter_mod)

        with patch.dict(sys.modules, mods):
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)
            task = Task(task_type=TaskType.DEERFLOW, payload={})
            result = await dfr.handle(task)

        assert result.status == "error"
        assert "No query" in result.result.get("error", "")

    @pytest.mark.asyncio
    async def test_deerflow_not_installed_returns_error(self):
        adapter_mod = _build_mock_adapter_module(available=False)
        mods = _inject_oas_modules(adapter_mod)

        with patch.dict(sys.modules, mods):
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)
            result = await dfr.handle(_make_task("test"))

        assert result.status == "error"
        assert "not available" in result.result.get("error", "") or \
               "not installed" in result.result.get("error", "")

    @pytest.mark.asyncio
    async def test_adapter_exception_returns_error(self):
        """When DeerFlow streaming raises, handler catches and returns error."""
        client = MagicMock()
        client.stream.side_effect = RuntimeError("connection failed")
        adapter_mod = _build_mock_adapter_module(available=True, client=client)

        # Override the adapter class to raise during run_research
        class FailingAdapter:
            def __init__(self, **kw):
                pass

            async def run_research(self, *a, **kw):
                raise RuntimeError("connection failed")

        adapter_mod.DeerFlowAdapter = FailingAdapter  # type: ignore[attr-defined]
        mods = _inject_oas_modules(adapter_mod)

        with patch.dict(sys.modules, mods):
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)
            result = await dfr.handle(_make_task("failing"))

        assert result.status == "error"
        assert "connection failed" in result.result.get("error", "")


# ---------------------------------------------------------------------------
# Handler: payload variants
# ---------------------------------------------------------------------------

class TestPayloadVariants:
    """Tests for different payload key combinations."""

    @pytest.mark.asyncio
    async def test_args_fallback(self):
        """When 'query' is absent, 'args' is used."""
        client = _make_mock_client("args result")
        adapter_mod = _build_mock_adapter_module(available=True, client=client)
        mods = _inject_oas_modules(adapter_mod)

        with patch.dict(sys.modules, mods):
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)
            task = Task(task_type=TaskType.DEERFLOW, payload={"args": "from args key"})
            result = await dfr.handle(task)

        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_custom_thread_id(self):
        """Custom thread_id is passed through to result."""
        client = _make_mock_client()
        adapter_mod = _build_mock_adapter_module(available=True, client=client)
        mods = _inject_oas_modules(adapter_mod)

        with patch.dict(sys.modules, mods):
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)
            task = _make_task("test", thread_id="custom-123")
            result = await dfr.handle(task)

        assert result.status == "ok"
        assert result.result.get("thread_id") == "custom-123"

    @pytest.mark.asyncio
    async def test_files_forwarded(self):
        """Files list is forwarded to adapter."""
        client = _make_mock_client()
        adapter_mod = _build_mock_adapter_module(available=True, client=client)
        mods = _inject_oas_modules(adapter_mod)

        with patch.dict(sys.modules, mods):
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)
            task = _make_task("analyze data", files=["/tmp/data.csv"])
            result = await dfr.handle(task)

        assert result.status == "ok"
        client.upload_files.assert_called_once()


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------

class TestModelSelection:
    """_select_model() returns tier-appropriate model names."""

    def test_select_model_fallback_no_router(self):
        """When model router is unavailable, returns None."""
        adapter_mod = _build_mock_adapter_module(available=True, client=_make_mock_client())
        mods = _inject_oas_modules(adapter_mod)

        with patch.dict(sys.modules, mods):
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)

            with patch("shared.llm_client.get_model_router", return_value=None):
                assert dfr._select_model("test query") is None

    def test_select_model_import_error_returns_none(self):
        """On import errors, returns None gracefully."""
        # Don't inject oas_core.model_router — let it fail naturally
        mods = {
            "oas_core": None,  # Make import fail
        }

        with patch.dict(sys.modules, mods):
            import importlib
            import experiment.deerflow_research as dfr
            importlib.reload(dfr)
            result = dfr._select_model("test query")
            assert result is None
