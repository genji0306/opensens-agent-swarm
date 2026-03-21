"""Tests for the DRVP SSE relay endpoint in leader.serve."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import leader.serve as serve_mod


@pytest.fixture(autouse=True)
def reset_redis():
    """Reset module-level Redis client between tests."""
    serve_mod._drvp_redis = None
    yield
    serve_mod._drvp_redis = None


def _make_mock_redis(messages: list[dict] | None = None):
    """Create mock Redis + pubsub that yields given messages then idles."""
    mock_pubsub = AsyncMock()
    call_count = 0

    async def get_message(ignore_subscribe_messages=True, timeout=1.0):
        nonlocal call_count
        if messages and call_count < len(messages):
            msg = messages[call_count]
            call_count += 1
            return msg
        return None

    mock_pubsub.get_message = get_message
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub  # sync return
    return mock_redis, mock_pubsub


def _make_request(max_iterations: int = 1):
    """Mock Request that reports disconnected after max_iterations."""
    count = 0

    async def is_disconnected():
        nonlocal count
        count += 1
        return count > max_iterations

    mock_request = AsyncMock()
    mock_request.is_disconnected = is_disconnected
    return mock_request


class TestDrvpSseEndpoint:
    """Test the /drvp/events/{company_id} SSE route registration."""

    def test_endpoint_registered(self):
        """The DRVP SSE route exists on the FastAPI app."""
        routes = [r.path for r in serve_mod.app.routes if hasattr(r, "path")]
        assert "/drvp/events/{company_id}" in routes

    async def test_get_drvp_redis_lazy_init(self):
        """_get_drvp_redis creates a Redis client on first call."""
        mock_redis = MagicMock()
        with patch.dict("sys.modules", {"redis": MagicMock(), "redis.asyncio": MagicMock()}):
            import redis.asyncio as aioredis_mod
            aioredis_mod.from_url = MagicMock(return_value=mock_redis)
            with patch("shared.config.settings") as mock_settings:
                mock_settings.redis_url = "redis://test:6379"
                result = await serve_mod._get_drvp_redis()
                assert result is mock_redis

    async def test_get_drvp_redis_returns_cached(self):
        """_get_drvp_redis returns cached client on subsequent calls."""
        mock_redis = MagicMock()
        serve_mod._drvp_redis = mock_redis
        result = await serve_mod._get_drvp_redis()
        assert result is mock_redis


class TestDrvpSseGenerator:
    """Test the SSE event_generator logic."""

    async def test_sse_response_type(self):
        """drvp_sse returns a StreamingResponse with correct headers."""
        from starlette.responses import StreamingResponse

        mock_redis, _ = _make_mock_redis()
        serve_mod._drvp_redis = mock_redis

        response = await serve_mod.drvp_sse("comp_test", _make_request(0))

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert response.headers.get("Cache-Control") == "no-cache"
        assert response.headers.get("X-Accel-Buffering") == "no"

    async def test_sse_subscribes_to_correct_channel(self):
        """The generator subscribes to drvp:{company_id}."""
        mock_redis, mock_pubsub = _make_mock_redis()
        serve_mod._drvp_redis = mock_redis

        response = await serve_mod.drvp_sse("my_company", _make_request(1))

        async for _ in response.body_iterator:
            pass

        mock_pubsub.subscribe.assert_called_once_with("drvp:my_company")

    async def test_sse_yields_data_frame_for_messages(self):
        """Redis messages are yielded as SSE data frames."""
        event_json = json.dumps({"event_type": "agent.activated", "agent_name": "test"})
        mock_redis, _ = _make_mock_redis([
            {"type": "message", "data": event_json.encode()},
        ])
        serve_mod._drvp_redis = mock_redis

        response = await serve_mod.drvp_sse("comp_test", _make_request(1))

        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)

        data_frames = [c for c in chunks if c.startswith("data:")]
        assert len(data_frames) >= 1
        payload = json.loads(data_frames[0][len("data: "):].strip())
        assert payload["event_type"] == "agent.activated"

    async def test_sse_yields_keepalive_when_idle(self):
        """Keepalive comments are emitted when no messages are available."""
        mock_redis, _ = _make_mock_redis([])
        serve_mod._drvp_redis = mock_redis

        response = await serve_mod.drvp_sse("comp_test", _make_request(1))

        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)

        assert any(": keepalive" in c for c in chunks)

    async def test_sse_cleans_up_pubsub_on_exit(self):
        """Pubsub is unsubscribed and closed when generator exits."""
        mock_redis, mock_pubsub = _make_mock_redis()
        serve_mod._drvp_redis = mock_redis

        response = await serve_mod.drvp_sse("comp_test", _make_request(0))

        async for _ in response.body_iterator:
            pass

        mock_pubsub.unsubscribe.assert_called_once_with("drvp:comp_test")
        mock_pubsub.aclose.assert_called_once()

    async def test_sse_handles_bytes_data(self):
        """Handles bytes data from Redis (default encoding)."""
        mock_redis, _ = _make_mock_redis([
            {"type": "message", "data": b'{"event_type":"request.created"}'},
        ])
        serve_mod._drvp_redis = mock_redis

        response = await serve_mod.drvp_sse("comp_test", _make_request(1))

        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)

        data_frames = [c for c in chunks if c.startswith("data:")]
        assert len(data_frames) >= 1
        payload = json.loads(data_frames[0][len("data: "):].strip())
        assert payload["event_type"] == "request.created"

    async def test_sse_handles_string_data(self):
        """Handles string data from Redis (decode_responses=True)."""
        mock_redis, _ = _make_mock_redis([
            {"type": "message", "data": '{"event_type":"budget.check"}'},
        ])
        serve_mod._drvp_redis = mock_redis

        response = await serve_mod.drvp_sse("comp_test", _make_request(1))

        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)

        data_frames = [c for c in chunks if c.startswith("data:")]
        assert len(data_frames) >= 1
        payload = json.loads(data_frames[0][len("data: "):].strip())
        assert payload["event_type"] == "budget.check"
