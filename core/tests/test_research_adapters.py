"""Tests for LabClaw, InternAgent, UniScientist adapters."""

from __future__ import annotations

import pytest

from oas_core.adapters.labclaw import LabClawAdapter, LABCLAW_AVAILABLE
from oas_core.adapters.internagent import InternAgentAdapter, INTERNAGENT_AVAILABLE
from oas_core.adapters.uniscientist import UniScientistAdapter, UNISCIENTIST_AVAILABLE


class TestLabClawAdapter:
    @pytest.mark.asyncio
    async def test_stub_returns_placeholder(self):
        adapter = LabClawAdapter()
        result = await adapter.run("Test objective")
        assert result.available is False
        assert result.backend == "labclaw"
        assert result.output == ""

    @pytest.mark.asyncio
    async def test_custom_params(self):
        adapter = LabClawAdapter()
        result = await adapter.run(
            "Test",
            max_iterations=10,
            context="prior context",
        )
        from oas_core.adapters.research_result import ResearchResult
        assert isinstance(result, ResearchResult)

    def test_import_guard(self):
        assert isinstance(LABCLAW_AVAILABLE, bool)


class TestInternAgentAdapter:
    @pytest.mark.asyncio
    async def test_stub_returns_placeholder(self):
        adapter = InternAgentAdapter()
        result = await adapter.run("Quantum computing")
        assert result.available is False
        assert result.backend == "internagent"
        assert result.output == ""

    @pytest.mark.asyncio
    async def test_custom_depth(self):
        adapter = InternAgentAdapter()
        result = await adapter.run("Test", max_depth=5)
        from oas_core.adapters.research_result import ResearchResult
        assert isinstance(result, ResearchResult)

    def test_import_guard(self):
        assert isinstance(INTERNAGENT_AVAILABLE, bool)


class TestUniScientistAdapter:
    @pytest.mark.asyncio
    async def test_stub_returns_combined(self):
        adapter = UniScientistAdapter()
        findings = [
            {"output": "Finding 1 about graphene"},
            {"output": "Finding 2 about DFT"},
        ]
        result = await adapter.synthesize(
            "r1", findings, objective="Graphene research"
        )
        assert result["stub"] is True
        assert result["source_count"] == 2
        assert "Finding 1" in result["output"]
        assert "Finding 2" in result["output"]

    @pytest.mark.asyncio
    async def test_empty_findings(self):
        adapter = UniScientistAdapter()
        result = await adapter.synthesize("r1", [], objective="Test")
        assert result["source_count"] == 0

    @pytest.mark.asyncio
    async def test_output_format(self):
        adapter = UniScientistAdapter()
        result = await adapter.synthesize(
            "r1",
            [{"output": "data"}],
            output_format="summary",
        )
        assert isinstance(result, dict)

    def test_import_guard(self):
        assert isinstance(UNISCIENTIST_AVAILABLE, bool)
