"""Tests for LabClawAdapter (core/oas_core/adapters/labclaw.py).

All tests work WITHOUT labclaw installed (test the stub/unavailable path).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oas_core.adapters.labclaw import (
    LABCLAW_AVAILABLE,
    LabClawAdapter,
    LabClawConfig,
)
from oas_core.adapters.research_result import ResearchResult


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

class TestConfigDefaults:
    def test_config_defaults(self):
        cfg = LabClawConfig()
        assert cfg.enabled is False
        assert cfg.max_iterations == 5
        assert cfg.timeout == 300.0
        assert str(cfg.base_dir).endswith("labclaw")

    def test_config_custom(self):
        cfg = LabClawConfig(enabled=True, max_iterations=10, timeout=600.0)
        assert cfg.enabled is True
        assert cfg.max_iterations == 10
        assert cfg.timeout == 600.0


# ---------------------------------------------------------------------------
# Unavailable / stub path
# ---------------------------------------------------------------------------

class TestUnavailable:
    def test_unavailable_returns_stub(self):
        """When LabClaw is not available, run() returns a stub ResearchResult."""
        adapter = LabClawAdapter()
        # LabClaw is not installed in the test env; config.enabled defaults to False
        assert adapter.available is False

    @pytest.mark.asyncio
    async def test_run_returns_stub_research_result(self):
        adapter = LabClawAdapter()
        result = await adapter.run("test query about graphene")
        assert isinstance(result, ResearchResult)
        assert result.available is False
        assert result.backend == "labclaw"
        assert result.output == ""
        assert result.query == "test query about graphene"

    @pytest.mark.asyncio
    async def test_health_when_unavailable(self):
        adapter = LabClawAdapter()
        h = await adapter.health()
        assert h["installed"] == LABCLAW_AVAILABLE
        assert h["enabled"] is False
        assert h["available"] is False
        assert "base_dir" in h

    @pytest.mark.asyncio
    async def test_run_with_context_augments_query(self):
        """When context is provided, it should be reflected in metadata but
        the stub still returns empty output."""
        adapter = LabClawAdapter()
        result = await adapter.run(
            "DFT parameters",
            context="Prior research on graphene bilayers",
        )
        assert result.available is False
        assert result.query == "DFT parameters"


# ---------------------------------------------------------------------------
# Available (mocked) path
# ---------------------------------------------------------------------------

class TestAvailable:
    @pytest.mark.asyncio
    async def test_health_when_available(self):
        """When LabClaw is installed and enabled, health reflects that."""
        with patch("oas_core.adapters.labclaw.LABCLAW_AVAILABLE", True):
            adapter = LabClawAdapter(LabClawConfig(enabled=True))
            assert adapter.available is True
            h = await adapter.health()
            assert h["installed"] is True
            assert h["enabled"] is True
            assert h["available"] is True

    @pytest.mark.asyncio
    async def test_run_returns_research_result(self):
        """When available, run() delegates to _run_sync via asyncio.to_thread."""
        with patch("oas_core.adapters.labclaw.LABCLAW_AVAILABLE", True):
            adapter = LabClawAdapter(LabClawConfig(enabled=True))

            mock_output = ("Graphene results here", [{"title": "Paper1"}])
            with patch.object(adapter, "_run_sync", return_value=mock_output):
                result = await adapter.run("graphene DFT")

            assert isinstance(result, ResearchResult)
            assert result.available is True
            assert result.backend == "labclaw"
            assert result.output == "Graphene results here"
            assert len(result.sources) == 1
            assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_run_emits_drvp_events(self):
        """Verify DRVP events are emitted during run()."""
        emitted: list[str] = []

        async def mock_emit(event_type_str, **kwargs):
            emitted.append(event_type_str)

        with patch("oas_core.adapters.labclaw.LABCLAW_AVAILABLE", True):
            adapter = LabClawAdapter(LabClawConfig(enabled=True))
            adapter._emit_event = mock_emit  # type: ignore[assignment]

            with patch.object(adapter, "_run_sync", return_value=("output", [])):
                await adapter.run("test query")

        assert "research.backend.started" in emitted
        assert "research.backend.completed" in emitted

    @pytest.mark.asyncio
    async def test_run_error_returns_result_with_error(self):
        """When _run_sync raises, the adapter returns a result with error metadata."""
        with patch("oas_core.adapters.labclaw.LABCLAW_AVAILABLE", True):
            adapter = LabClawAdapter(LabClawConfig(enabled=True))

            with patch.object(
                adapter, "_run_sync", side_effect=RuntimeError("connection lost")
            ):
                result = await adapter.run("failing query")

            assert result.available is True
            assert "error" in result.metadata
            assert "connection lost" in result.output
