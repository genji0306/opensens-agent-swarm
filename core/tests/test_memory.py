"""Tests for oas_core.memory — MemoryClient."""
import pytest

from oas_core.memory import MemoryClient, MemoryError, SCOPE_AGENT


class TestMemoryClientInit:
    def test_default_url(self):
        client = MemoryClient()
        assert client.base_url == "http://localhost:1933"

    def test_custom_url(self):
        client = MemoryClient("http://viking:1933/")
        assert client.base_url == "http://viking:1933"

    def test_api_key_stored(self):
        client = MemoryClient(api_key="test-key")
        assert client.api_key == "test-key"


class TestMemoryClientRead:
    @pytest.mark.asyncio
    async def test_read_level_0_calls_abstract(self, monkeypatch):
        client = MemoryClient()
        called_with = {}

        async def mock_request(method, path, **kwargs):
            called_with.update({"method": method, "path": path, **kwargs})
            return {"abstract": "Brief summary"}

        monkeypatch.setattr(client, "_request", mock_request)
        result = await client.read("viking://agent/test", level=0)

        assert result["level"] == 0
        assert result["content"] == "Brief summary"
        assert called_with["path"] == "/api/abstract"

    @pytest.mark.asyncio
    async def test_read_level_1_calls_overview(self, monkeypatch):
        client = MemoryClient()

        async def mock_request(method, path, **kwargs):
            return {"overview": "Medium detail"}

        monkeypatch.setattr(client, "_request", mock_request)
        result = await client.read("viking://agent/test", level=1)

        assert result["level"] == 1
        assert result["content"] == "Medium detail"

    @pytest.mark.asyncio
    async def test_read_level_2_calls_read(self, monkeypatch):
        client = MemoryClient()

        async def mock_request(method, path, **kwargs):
            return {"content": "Full detailed content"}

        monkeypatch.setattr(client, "_request", mock_request)
        result = await client.read("viking://agent/test", level=2)

        assert result["level"] == 2
        assert result["content"] == "Full detailed content"


class TestMemoryClientWrite:
    @pytest.mark.asyncio
    async def test_write_string_content(self, monkeypatch):
        client = MemoryClient()
        posted = {}

        async def mock_request(method, path, **kwargs):
            posted.update({"method": method, "path": path, **kwargs})
            return {}

        monkeypatch.setattr(client, "_request", mock_request)
        await client.write("viking://agent/test", "hello world")

        assert posted["method"] == "POST"
        assert posted["path"] == "/api/write"
        assert posted["json"]["content"] == "hello world"

    @pytest.mark.asyncio
    async def test_write_dict_content(self, monkeypatch):
        client = MemoryClient()

        async def mock_request(method, path, **kwargs):
            return {}

        monkeypatch.setattr(client, "_request", mock_request)
        await client.write("viking://agent/test", {"key": "value"})


class TestMemoryClientSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, monkeypatch):
        client = MemoryClient()

        async def mock_request(method, path, **kwargs):
            return {"results": [{"uri": "viking://agent/foo", "score": 0.9}]}

        monkeypatch.setattr(client, "_request", mock_request)
        results = await client.search("quantum dot electrode")

        assert len(results) == 1
        assert results[0]["score"] == 0.9

    @pytest.mark.asyncio
    async def test_search_custom_params(self, monkeypatch):
        client = MemoryClient()
        posted = {}

        async def mock_request(method, path, **kwargs):
            posted.update(kwargs)
            return {"results": []}

        monkeypatch.setattr(client, "_request", mock_request)
        await client.search("test", limit=3, score_threshold=0.7)

        assert posted["json"]["limit"] == 3
        assert posted["json"]["score_threshold"] == 0.7


class TestMemoryError:
    def test_error_attributes(self):
        err = MemoryError("Not found", status_code=404)
        assert err.detail == "Not found"
        assert err.status_code == 404
        assert "Not found" in str(err)
