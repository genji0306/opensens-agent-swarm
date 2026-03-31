"""Tests for the OAS Python SDK."""

import sys
import pytest
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).parent.parent.parent / "sdk"
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

from opensens_oas import OASClient, AsyncOASClient
from opensens_oas.client import OASError


class TestOASClient:
    def test_create_client(self):
        client = OASClient("http://localhost:8100", api_key="test_key")
        assert client._base_url == "http://localhost:8100"
        assert client._api_key == "test_key"

    def test_headers_include_auth(self):
        client = OASClient("http://localhost:8100", api_key="secret")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer secret"

    def test_create_campaign_stub(self):
        client = OASClient("http://localhost:8100")
        result = client.create_campaign("quantum dots")
        assert result["status"] == "ok"
        assert result["method"] == "POST"

    def test_get_campaign_stub(self):
        client = OASClient("http://localhost:8100")
        result = client.get_campaign("camp_123")
        assert result["path"] == "/campaign/camp_123"

    def test_dispatch_stub(self):
        client = OASClient("http://localhost:8100")
        result = client.dispatch("/research quantum dots")
        assert result["method"] == "POST"

    def test_health_stub(self):
        client = OASClient("http://localhost:8100")
        result = client.health()
        assert result["path"] == "/health"

    def test_webhook_operations_stub(self):
        client = OASClient("http://localhost:8100")
        result = client.subscribe_webhook("https://example.com/hook", ["request.completed"])
        assert result["method"] == "POST"

        result = client.list_webhooks()
        assert result["method"] == "GET"

    def test_url_trailing_slash_stripped(self):
        client = OASClient("http://localhost:8100/")
        assert client._base_url == "http://localhost:8100"


class TestAsyncOASClient:
    @pytest.mark.asyncio
    async def test_create_campaign_stub(self):
        async with AsyncOASClient("http://localhost:8100") as client:
            result = await client.create_campaign("test")
            assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_dispatch_stub(self):
        async with AsyncOASClient("http://localhost:8100") as client:
            result = await client.dispatch("/research test")
            assert result["method"] == "POST"

    @pytest.mark.asyncio
    async def test_health_stub(self):
        client = AsyncOASClient("http://localhost:8100")
        result = await client.health()
        assert result["path"] == "/health"
