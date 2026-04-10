"""Tests for ResearchRouter -- parallel/sequential/hybrid modes with DRVP events."""
from __future__ import annotations

import pytest

from oas_core.adapters.research_result import ResearchResult
from oas_core.deep_research.router import (
    ResearchMode,
    ResearchRouter,
    ResearchRouterConfig,
    ResearchRouterResult,
)


# ---------------------------------------------------------------------------
# Fake backends returning ResearchResult
# ---------------------------------------------------------------------------

class _EchoBackend:
    """Returns query + context as output."""

    def __init__(self, name: str = "echo") -> None:
        self._name = name

    async def run(self, query: str, *, context: str = "") -> ResearchResult:
        prefix = f"context={context[:20]}... " if context else ""
        return ResearchResult(
            query=query,
            output=f"{prefix}echo: {query}",
            sources=[{"title": f"src-{self._name}"}],
            available=True,
            backend=self._name,
        )

    async def health(self) -> dict:
        return {"available": True}


class _FailingBackend:
    async def run(self, query: str, *, context: str = "") -> ResearchResult:
        raise RuntimeError("backend exploded")


class _SlowBackend:
    async def run(self, query: str, *, context: str = "") -> ResearchResult:
        import asyncio
        await asyncio.sleep(0.01)
        return ResearchResult(
            query=query,
            output=f"slow: {query}",
            sources=[],
            available=True,
            backend="slow",
        )


class _UnavailableBackend:
    available = False

    async def run(self, query: str, *, context: str = "") -> ResearchResult:
        return ResearchResult(
            query=query,
            output="",
            available=False,
            backend="unavailable",
        )


# ---------------------------------------------------------------------------
# Parallel mode
# ---------------------------------------------------------------------------

class TestParallelMode:
    @pytest.mark.asyncio
    async def test_parallel_runs_all_backends_concurrently(self):
        router = ResearchRouter(
            backends={
                "deerflow": _SlowBackend(),
                "labclaw": _SlowBackend(),
                "internagent": _SlowBackend(),
            },
        )
        result = await router.run(
            "graphene DFT", mode="parallel",
            backends=["deerflow", "labclaw", "internagent"],
        )
        assert isinstance(result, ResearchRouterResult)
        assert result.mode == ResearchMode.PARALLEL
        assert len(result.backend_results) == 3
        assert result.succeeded


# ---------------------------------------------------------------------------
# Sequential mode
# ---------------------------------------------------------------------------

class TestSequentialMode:
    @pytest.mark.asyncio
    async def test_sequential_chains_context(self):
        router = ResearchRouter(
            config=ResearchRouterConfig(default_mode="sequential"),
            backends={
                "internagent": _EchoBackend("internagent"),
                "labclaw": _EchoBackend("labclaw"),
            },
        )
        result = await router.run(
            "graphene DFT",
            backends=["internagent", "labclaw"],
        )
        assert result.mode == ResearchMode.SEQUENTIAL
        assert len(result.backend_results) == 2
        # Second backend should have received first backend's output as context
        second = result.backend_results[1]
        assert "context=" in second.output
        assert result.succeeded


# ---------------------------------------------------------------------------
# Hybrid mode
# ---------------------------------------------------------------------------

class TestHybridMode:
    @pytest.mark.asyncio
    async def test_hybrid_parallel_then_sequential(self):
        router = ResearchRouter(
            backends={
                "deerflow": _EchoBackend("deerflow"),
                "internagent": _EchoBackend("internagent"),
                "labclaw": _EchoBackend("labclaw"),
            },
        )
        result = await router.run(
            "graphene DFT", mode="hybrid",
            backends=["deerflow", "internagent", "labclaw"],
        )
        assert result.mode == ResearchMode.HYBRID
        assert len(result.backend_results) == 3
        # Labclaw (deepening) should have received discovery context
        labclaw_result = [r for r in result.backend_results if r.backend == "labclaw"]
        assert len(labclaw_result) == 1
        assert "context=" in labclaw_result[0].output


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_reports_available_backends(self):
        router = ResearchRouter(
            backends={
                "deerflow": _EchoBackend("deerflow"),
                "labclaw": _EchoBackend("labclaw"),
            },
        )
        h = await router.health()
        assert "deerflow" in h["registered_backends"]
        assert "labclaw" in h["registered_backends"]
        assert h["backend_health"]["deerflow"]["available"] is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_unavailable_backends_skipped_gracefully(self):
        """Unavailable backends return stub results without crashing."""
        router = ResearchRouter(
            backends={
                "deerflow": _EchoBackend("deerflow"),
                "labclaw": _UnavailableBackend(),
            },
        )
        result = await router.run(
            "test", mode="parallel",
            backends=["deerflow", "labclaw"],
        )
        # Both should produce results -- one available, one not
        assert len(result.backend_results) == 2
        available_results = [r for r in result.backend_results if r.available]
        unavailable_results = [r for r in result.backend_results if not r.available]
        assert len(available_results) == 1
        assert len(unavailable_results) == 1

    @pytest.mark.asyncio
    async def test_synthesis_merges_all_results(self):
        router = ResearchRouter(
            backends={
                "deerflow": _EchoBackend("deerflow"),
                "labclaw": _EchoBackend("labclaw"),
            },
        )
        result = await router.run(
            "test query", mode="parallel",
            backends=["deerflow", "labclaw"],
        )
        # Default synthesis merges outputs with separators
        assert "deerflow" in result.synthesis
        assert "labclaw" in result.synthesis
        assert result.total_sources == 2  # one source per echo backend

    @pytest.mark.asyncio
    async def test_no_backends_returns_error(self):
        router = ResearchRouter(backends={})
        result = await router.run("test", backends=["nonexistent"])
        assert not result.succeeded
        assert "No active" in result.errors[0]

    @pytest.mark.asyncio
    async def test_config_defaults(self):
        cfg = ResearchRouterConfig()
        assert cfg.default_mode == "hybrid"
        assert cfg.default_backends == ["deerflow"]
        assert cfg.synthesis_backend == "default"
        assert cfg.timeout_per_backend == 300.0

    @pytest.mark.asyncio
    async def test_result_dataclass(self):
        result = ResearchRouterResult(
            query="test",
            mode="parallel",
            backend_results=[
                ResearchResult(query="test", output="a", backend="x"),
                ResearchResult(query="test", output="b", backend="y"),
            ],
            synthesis="merged",
            total_sources=4,
            duration_seconds=1.5,
        )
        assert result.succeeded
        assert result.total_sources == 4

    def test_available_backends_property(self):
        router = ResearchRouter(
            backends={"b": _EchoBackend("b"), "a": _EchoBackend("a")},
        )
        assert router.available_backends == ["a", "b"]

    @pytest.mark.asyncio
    async def test_backend_failure_collected_as_error(self):
        router = ResearchRouter(
            backends={
                "deerflow": _EchoBackend("deerflow"),
                "labclaw": _FailingBackend(),
            },
        )
        result = await router.run(
            "test", mode="parallel",
            backends=["deerflow", "labclaw"],
        )
        assert len(result.errors) == 1
        assert "labclaw" in result.errors[0]
        assert len(result.backend_results) == 1
