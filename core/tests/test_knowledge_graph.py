"""Tests for knowledge graph methods in oas_core.memory.MemoryClient."""
import pytest
from unittest.mock import AsyncMock, patch

from oas_core.memory import (
    MemoryClient,
    SCOPE_RESEARCH,
    SCOPE_EXPERIMENTS,
    SCOPE_KNOWLEDGE,
    _slugify,
)


class TestSlugify:
    def test_basic(self):
        assert _slugify("Quantum Dots") == "quantum-dots"

    def test_special_chars(self):
        assert _slugify("MnO2/Carbon Nano!tubes@2024") == "mno2carbon-nanotubes2024"

    def test_whitespace(self):
        assert _slugify("  spaces  and  tabs  ") == "spaces-and-tabs"

    def test_truncation(self):
        long = "a" * 200
        assert len(_slugify(long)) <= 80

    def test_trailing_dash(self):
        assert not _slugify("test-").endswith("-")

    def test_empty(self):
        assert _slugify("") == "untitled"

    def test_unicode(self):
        result = _slugify("Ölüdeniz study")
        assert "l" in result  # should handle basic unicode


class TestStoreResearch:
    @pytest.mark.asyncio
    async def test_builds_correct_uri(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock) as mock_write, \
             patch.object(client, "link", new_callable=AsyncMock):
            uri = await client.store_research(
                topic="Quantum Dots",
                findings={"summary": "QD are useful for sensors"},
                subtopic="electrode coatings",
            )

        assert uri == f"{SCOPE_RESEARCH}/quantum-dots/electrode-coatings"
        mock_write.assert_awaited_once()
        call_args = mock_write.call_args
        assert call_args[0][0] == uri  # first positional = uri

    @pytest.mark.asyncio
    async def test_uri_without_subtopic(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock), \
             patch.object(client, "link", new_callable=AsyncMock):
            uri = await client.store_research(
                topic="Impedance Spectroscopy",
                findings={"data": "results"},
            )

        assert uri == f"{SCOPE_RESEARCH}/impedance-spectroscopy"

    @pytest.mark.asyncio
    async def test_links_to_session_when_request_id_provided(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock), \
             patch.object(client, "link", new_callable=AsyncMock) as mock_link:
            await client.store_research(
                topic="Test",
                findings={},
                request_id="req-42",
            )

        mock_link.assert_awaited_once()
        call_args = mock_link.call_args
        assert "req-42" in call_args[0][1][0]  # to_uris contains session URI

    @pytest.mark.asyncio
    async def test_no_link_without_request_id(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock), \
             patch.object(client, "link", new_callable=AsyncMock) as mock_link:
            await client.store_research(topic="Test", findings={})

        mock_link.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_content_includes_metadata(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock) as mock_write, \
             patch.object(client, "link", new_callable=AsyncMock):
            await client.store_research(
                topic="Test",
                findings={"summary": "found stuff"},
                agent_name="Academic",
                request_id="req-1",
            )

        content = mock_write.call_args[0][1]  # second positional
        assert content["topic"] == "Test"
        assert content["agent_name"] == "Academic"
        assert content["summary"] == "found stuff"


class TestStoreExperiment:
    @pytest.mark.asyncio
    async def test_builds_correct_uri(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock), \
             patch.object(client, "link", new_callable=AsyncMock):
            uri = await client.store_experiment(
                name="EIT Simulation Run 3",
                results={"rmse": 0.023},
            )

        assert uri == f"{SCOPE_EXPERIMENTS}/eit-simulation-run-3"

    @pytest.mark.asyncio
    async def test_links_to_research_topic(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock), \
             patch.object(client, "link", new_callable=AsyncMock) as mock_link:
            await client.store_experiment(
                name="run-1",
                results={},
                research_topic="Quantum Dots",
            )

        mock_link.assert_awaited_once()
        to_uris = mock_link.call_args[0][1]
        assert f"{SCOPE_RESEARCH}/quantum-dots" in to_uris


class TestFindResearch:
    @pytest.mark.asyncio
    async def test_searches_research_scope(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "search", new_callable=AsyncMock, return_value=[]) as mock_search:
            await client.find_research("quantum dots")

        mock_search.assert_awaited_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs[1]["target_uri"] == SCOPE_RESEARCH


class TestBuildKnowledgeContext:
    @pytest.mark.asyncio
    async def test_combines_all_sources(self):
        client = MemoryClient("http://mock:1933")
        research_results = [{"uri": "r1", "score": 0.9}]
        experiment_results = [{"uri": "e1", "score": 0.8}]
        session_results = [{"uri": "s1", "score": 0.7}]

        async def mock_search(query, target_uri=None, **kwargs):
            if target_uri == SCOPE_RESEARCH:
                return research_results
            if target_uri == SCOPE_EXPERIMENTS:
                return experiment_results
            return []

        with patch.object(client, "search", side_effect=mock_search), \
             patch.object(client, "find_related_sessions",
                          new_callable=AsyncMock, return_value=session_results):
            ctx = await client.build_knowledge_context("quantum dots")

        assert ctx["query"] == "quantum dots"
        assert ctx["research"] == research_results
        assert ctx["experiments"] == experiment_results
        assert ctx["related_sessions"] == session_results
        assert ctx["total_sources"] == 3

    @pytest.mark.asyncio
    async def test_empty_results(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "search", new_callable=AsyncMock, return_value=[]), \
             patch.object(client, "find_related_sessions",
                          new_callable=AsyncMock, return_value=[]):
            ctx = await client.build_knowledge_context("nonexistent topic")

        assert ctx["total_sources"] == 0


class TestSessionContinuity:
    @pytest.mark.asyncio
    async def test_archive_session(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "write", new_callable=AsyncMock) as mock_write:
            await client.archive_session(
                session_id="sess-42",
                messages=[{"role": "user", "content": "hello"}],
                summary="Quick test",
                agent_name="Leader",
            )

        mock_write.assert_awaited_once()
        uri = mock_write.call_args[0][0]
        assert "sess-42" in uri
        content = mock_write.call_args[0][1]
        assert content["summary"] == "Quick test"
        assert content["message_count"] == 1

    @pytest.mark.asyncio
    async def test_load_session_context(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "read", new_callable=AsyncMock, return_value={"content": "data"}) as mock_read:
            result = await client.load_session_context("sess-42", level=1)

        mock_read.assert_awaited_once()
        assert result == {"content": "data"}

    @pytest.mark.asyncio
    async def test_find_related_sessions(self):
        client = MemoryClient("http://mock:1933")
        with patch.object(client, "search", new_callable=AsyncMock, return_value=[]) as mock_search:
            await client.find_related_sessions("quantum dots")

        assert mock_search.call_args[1]["score_threshold"] == 0.4


class TestScopes:
    def test_all_scopes_defined(self):
        assert SCOPE_RESEARCH == "viking://research"
        assert SCOPE_EXPERIMENTS == "viking://experiments"
        assert SCOPE_KNOWLEDGE == "viking://knowledge"
