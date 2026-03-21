"""Tests for oas_core.middleware.memory — MemoryMiddleware."""
import pytest

from oas_core.memory import MemoryClient, MemoryError
from oas_core.middleware.memory import MemoryMiddleware
from oas_core.protocols.drvp import configure


@pytest.fixture(autouse=True)
def disable_drvp():
    """Disable DRVP Redis emission for tests."""
    configure(company_id="test", redis_client=None, paperclip_client=None)


class TestMemoryMiddlewarePreLoad:
    @pytest.mark.asyncio
    async def test_pre_load_returns_results(self, monkeypatch):
        client = MemoryClient()

        async def mock_search(query, target_uri, limit, score_threshold):
            return [{"uri": "viking://agent/foo", "score": 0.8}]

        monkeypatch.setattr(client, "search", mock_search)
        mw = MemoryMiddleware(client)

        results = await mw.pre_load("req_1", "academic", "academic", "quantum sensors")
        assert len(results) == 1
        assert results[0]["score"] == 0.8

    @pytest.mark.asyncio
    async def test_pre_load_no_client(self):
        mw = MemoryMiddleware(None)
        results = await mw.pre_load("req_1", "academic", "academic", "test")
        assert results == []

    @pytest.mark.asyncio
    async def test_pre_load_handles_error(self, monkeypatch):
        client = MemoryClient()

        async def mock_search(**kwargs):
            raise MemoryError("Connection refused")

        monkeypatch.setattr(client, "search", mock_search)
        mw = MemoryMiddleware(client)

        results = await mw.pre_load("req_1", "academic", "academic", "test")
        assert results == []


class TestMemoryMiddlewarePostStore:
    @pytest.mark.asyncio
    async def test_post_store_writes_to_correct_uri(self, monkeypatch):
        client = MemoryClient()
        written = {}

        async def mock_write(uri, content, level):
            written.update({"uri": uri, "content": content, "level": level})

        monkeypatch.setattr(client, "write", mock_write)
        mw = MemoryMiddleware(client)

        await mw.post_store("req_1", "academic", "academic", "task_42", {"findings": "data"})
        assert written["uri"] == "viking://agent/memories/cases/task_42"
        assert written["content"]["findings"] == "data"
        assert written["content"]["task_id"] == "task_42"
        assert written["level"] == 2

    @pytest.mark.asyncio
    async def test_post_store_no_client(self):
        mw = MemoryMiddleware(None)
        # Should not raise
        await mw.post_store("req_1", "academic", "academic", "task_42", {})

    @pytest.mark.asyncio
    async def test_post_store_handles_error(self, monkeypatch):
        client = MemoryClient()

        async def mock_write(uri, content, level):
            raise MemoryError("Write failed")

        monkeypatch.setattr(client, "write", mock_write)
        mw = MemoryMiddleware(client)

        # Should not raise
        await mw.post_store("req_1", "academic", "academic", "task_42", {})
