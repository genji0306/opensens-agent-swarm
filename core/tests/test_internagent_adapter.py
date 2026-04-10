"""Tests for InternAgentAdapter (core/oas_core/adapters/internagent.py).

All tests work WITHOUT internagent installed (test the stub/unavailable path).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from oas_core.adapters.internagent import (
    INTERNAGENT_AVAILABLE,
    InternAgentAdapter,
    InternAgentConfig,
)
from oas_core.adapters.research_result import ResearchResult


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

class TestConfigDefaults:
    def test_config_defaults(self):
        cfg = InternAgentConfig()
        assert cfg.enabled is False
        assert cfg.max_depth == 3
        assert cfg.timeout == 300.0
        assert str(cfg.base_dir).endswith("internagent")

    def test_config_custom(self):
        cfg = InternAgentConfig(enabled=True, max_depth=5, timeout=600.0)
        assert cfg.enabled is True
        assert cfg.max_depth == 5
        assert cfg.timeout == 600.0


# ---------------------------------------------------------------------------
# Unavailable / stub path
# ---------------------------------------------------------------------------

class TestUnavailable:
    def test_unavailable_returns_stub(self):
        """When InternAgent is not available, adapter.available is False."""
        adapter = InternAgentAdapter()
        assert adapter.available is False

    @pytest.mark.asyncio
    async def test_run_returns_stub_research_result(self):
        adapter = InternAgentAdapter()
        result = await adapter.run("test query about superconductors")
        assert isinstance(result, ResearchResult)
        assert result.available is False
        assert result.backend == "internagent"
        assert result.output == ""
        assert result.query == "test query about superconductors"

    @pytest.mark.asyncio
    async def test_health_when_unavailable(self):
        adapter = InternAgentAdapter()
        h = await adapter.health()
        assert h["installed"] == INTERNAGENT_AVAILABLE
        assert h["enabled"] is False
        assert h["available"] is False
        assert "base_dir" in h

    @pytest.mark.asyncio
    async def test_run_with_context_augments_query(self):
        """When context is provided, stub still returns empty output."""
        adapter = InternAgentAdapter()
        result = await adapter.run(
            "superconductor parameters",
            context="Prior research on high-Tc materials",
        )
        assert result.available is False
        assert result.query == "superconductor parameters"


# ---------------------------------------------------------------------------
# Available (mocked) path
# ---------------------------------------------------------------------------

class TestAvailable:
    @pytest.mark.asyncio
    async def test_health_when_available(self):
        """When InternAgent is installed and enabled, health reflects that."""
        with patch("oas_core.adapters.internagent.INTERNAGENT_AVAILABLE", True):
            adapter = InternAgentAdapter(InternAgentConfig(enabled=True))
            assert adapter.available is True
            h = await adapter.health()
            assert h["installed"] is True
            assert h["enabled"] is True
            assert h["available"] is True

    @pytest.mark.asyncio
    async def test_run_returns_research_result(self):
        """When available, run() delegates to _run_sync via asyncio.to_thread."""
        with patch("oas_core.adapters.internagent.INTERNAGENT_AVAILABLE", True):
            adapter = InternAgentAdapter(InternAgentConfig(enabled=True))

            mock_output = ("Superconductor findings", [{"title": "Paper1"}])
            with patch.object(adapter, "_run_sync", return_value=mock_output):
                result = await adapter.run("superconductor DFT")

            assert isinstance(result, ResearchResult)
            assert result.available is True
            assert result.backend == "internagent"
            assert result.output == "Superconductor findings"
            assert len(result.sources) == 1
            assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_run_emits_drvp_events(self):
        """Verify DRVP events are emitted during run()."""
        emitted: list[str] = []

        async def mock_emit(event_type_str, **kwargs):
            emitted.append(event_type_str)

        with patch("oas_core.adapters.internagent.INTERNAGENT_AVAILABLE", True):
            adapter = InternAgentAdapter(InternAgentConfig(enabled=True))
            adapter._emit_event = mock_emit  # type: ignore[assignment]

            with patch.object(adapter, "_run_sync", return_value=("output", [])):
                await adapter.run("test query")

        assert "research.backend.started" in emitted
        assert "research.backend.completed" in emitted

    @pytest.mark.asyncio
    async def test_run_error_returns_result_with_error(self):
        """When _run_sync raises, the adapter returns a result with error metadata."""
        with patch("oas_core.adapters.internagent.INTERNAGENT_AVAILABLE", True):
            adapter = InternAgentAdapter(InternAgentConfig(enabled=True))

            with patch.object(
                adapter, "_run_sync", side_effect=RuntimeError("timeout")
            ):
                result = await adapter.run("failing query")

            assert result.available is True
            assert "error" in result.metadata
            assert "timeout" in result.output
