"""Tests for oas_core.protocols.drvp — DRVP event emission."""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oas_core.protocols.drvp import (
    DRVPEvent, DRVPEventType, configure, emit,
    _last_stream_emit, _STREAM_TOKEN_INTERVAL,
)
import oas_core.protocols.drvp as drvp_mod


@pytest.fixture(autouse=True)
def reset_drvp():
    """Reset module-level state between tests."""
    drvp_mod._redis_client = None
    drvp_mod._paperclip_client = None
    drvp_mod._company_id = ""
    drvp_mod._last_stream_emit.clear()
    yield
    drvp_mod._redis_client = None
    drvp_mod._paperclip_client = None
    drvp_mod._company_id = ""
    drvp_mod._last_stream_emit.clear()


def _make_event(event_type=DRVPEventType.AGENT_ACTIVATED, agent_name="test_agent"):
    return DRVPEvent(
        event_type=event_type,
        request_id="req_123",
        agent_name=agent_name,
        device="leader",
    )


class TestConfigure:
    def test_sets_redis_client(self):
        mock_redis = MagicMock()
        configure(redis_client=mock_redis, company_id="comp_1")
        assert drvp_mod._redis_client is mock_redis
        assert drvp_mod._company_id == "comp_1"

    def test_sets_paperclip_client(self):
        mock_pc = MagicMock()
        configure(paperclip_client=mock_pc)
        assert drvp_mod._paperclip_client is mock_pc


class TestEmit:
    async def test_publishes_to_redis(self):
        mock_redis = AsyncMock()
        configure(redis_client=mock_redis, company_id="comp_1")

        event = _make_event()
        await emit(event)

        mock_redis.publish.assert_called_once()
        channel, data = mock_redis.publish.call_args[0]
        assert channel == "drvp:comp_1"

    async def test_persists_to_paperclip(self):
        mock_pc = AsyncMock()
        configure(paperclip_client=mock_pc, company_id="comp_1")

        event = _make_event()
        await emit(event)

        mock_pc.log_activity.assert_called_once()
        kwargs = mock_pc.log_activity.call_args[1]
        assert "drvp.agent.activated" in kwargs["action"]

    async def test_no_transports_configured(self):
        """emit() should not raise when no transports are configured."""
        event = _make_event()
        await emit(event)  # Should not raise

    async def test_redis_error_swallowed(self):
        mock_redis = AsyncMock()
        mock_redis.publish.side_effect = ConnectionError("Redis down")
        configure(redis_client=mock_redis, company_id="comp_1")

        event = _make_event()
        await emit(event)  # Should not raise

    async def test_paperclip_error_swallowed(self):
        mock_pc = AsyncMock()
        mock_pc.log_activity.side_effect = Exception("API error")
        configure(paperclip_client=mock_pc)

        event = _make_event()
        await emit(event)  # Should not raise


class TestStreamTokenRateLimit:
    async def test_first_event_passes(self):
        mock_redis = AsyncMock()
        configure(redis_client=mock_redis, company_id="comp_1")

        event = _make_event(DRVPEventType.LLM_STREAM_TOKEN)
        await emit(event)

        assert mock_redis.publish.call_count == 1

    async def test_rapid_events_throttled(self):
        mock_redis = AsyncMock()
        configure(redis_client=mock_redis, company_id="comp_1")

        for _ in range(5):
            event = _make_event(DRVPEventType.LLM_STREAM_TOKEN)
            await emit(event)

        # Only first should get through (rest within 500ms window)
        assert mock_redis.publish.call_count == 1

    async def test_different_agents_not_throttled(self):
        mock_redis = AsyncMock()
        configure(redis_client=mock_redis, company_id="comp_1")

        event1 = _make_event(DRVPEventType.LLM_STREAM_TOKEN, agent_name="agent_a")
        event2 = _make_event(DRVPEventType.LLM_STREAM_TOKEN, agent_name="agent_b")
        await emit(event1)
        await emit(event2)

        assert mock_redis.publish.call_count == 2

    async def test_non_stream_events_not_throttled(self):
        mock_redis = AsyncMock()
        configure(redis_client=mock_redis, company_id="comp_1")

        for _ in range(5):
            event = _make_event(DRVPEventType.AGENT_THINKING)
            await emit(event)

        assert mock_redis.publish.call_count == 5
