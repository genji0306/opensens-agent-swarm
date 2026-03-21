"""Tests for the /health endpoint in leader.serve."""
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from leader.serve import _check_service, ServiceHealth


class TestCheckService:
    @pytest.fixture
    def mock_response_ok(self):
        resp = MagicMock()
        resp.status_code = 200
        return resp

    @pytest.fixture
    def mock_response_error(self):
        resp = MagicMock()
        resp.status_code = 500
        return resp

    async def test_ok_response(self, mock_response_ok):
        with patch("leader.serve.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response_ok
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await _check_service("test", "http://localhost:9999/health")
            assert result.name == "test"
            assert result.status == "ok"
            assert result.latency_ms is not None

    async def test_error_response(self, mock_response_error):
        with patch("leader.serve.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response_error
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await _check_service("test", "http://localhost:9999/health")
            assert result.status == "error"
            assert "500" in result.error

    async def test_timeout(self):
        import httpx
        with patch("leader.serve.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = httpx.TimeoutException("timed out")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await _check_service("test", "http://localhost:9999/health")
            assert result.status == "timeout"

    async def test_connection_error(self):
        with patch("leader.serve.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = ConnectionError("refused")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await _check_service("test", "http://localhost:9999/health")
            assert result.status == "error"
            assert "refused" in result.error


class TestServiceHealth:
    def test_model_fields(self):
        sh = ServiceHealth(name="api", status="ok", latency_ms=42.5)
        assert sh.name == "api"
        assert sh.status == "ok"
        assert sh.latency_ms == 42.5
        assert sh.error is None

    def test_error_model(self):
        sh = ServiceHealth(name="db", status="error", error="Connection refused")
        assert sh.error == "Connection refused"
