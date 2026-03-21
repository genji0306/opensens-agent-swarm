"""Tests for oas_core.adapters.openclaw — OpenClawClient."""
import pytest

try:
    from oas_core.adapters.openclaw import OpenClawClient, OpenClawError, _WS_AVAILABLE
except ImportError:
    _WS_AVAILABLE = False


@pytest.mark.skipif(not _WS_AVAILABLE, reason="websockets not installed")
class TestOpenClawClientInit:
    def test_default_url(self):
        client = OpenClawClient()
        assert client.url == "ws://localhost:18789"
        assert client.client_id == "oas-core"

    def test_custom_url(self):
        client = OpenClawClient("ws://192.168.23.25:18789", token="abc")
        assert client.url == "ws://192.168.23.25:18789"
        assert client.token == "abc"

    def test_not_connected_initially(self):
        client = OpenClawClient()
        assert not client.connected


@pytest.mark.skipif(not _WS_AVAILABLE, reason="websockets not installed")
class TestOpenClawClientEvents:
    def test_register_handler(self):
        client = OpenClawClient()
        called = []
        client.on_event("agent", lambda p: called.append(p))
        assert "agent" in client._event_handlers
        assert len(client._event_handlers["agent"]) == 1

    def test_unregister_all_handlers(self):
        client = OpenClawClient()
        client.on_event("agent", lambda p: None)
        client.on_event("agent", lambda p: None)
        client.off_event("agent")
        assert "agent" not in client._event_handlers

    def test_unregister_specific_handler(self):
        client = OpenClawClient()
        handler1 = lambda p: None
        handler2 = lambda p: None
        client.on_event("agent", handler1)
        client.on_event("agent", handler2)
        client.off_event("agent", handler1)
        assert len(client._event_handlers["agent"]) == 1

    @pytest.mark.asyncio
    async def test_dispatch_event_calls_handler(self):
        client = OpenClawClient()
        received = []
        client.on_event("agent", lambda p: received.append(p))

        await client._dispatch_event({
            "type": "event",
            "event": "agent",
            "payload": {"runId": "run_1", "stream": "lifecycle"},
        })

        assert len(received) == 1
        assert received[0]["runId"] == "run_1"

    @pytest.mark.asyncio
    async def test_wildcard_handler(self):
        client = OpenClawClient()
        received = []
        client.on_event("*", lambda p: received.append(p))

        await client._dispatch_event({
            "type": "event",
            "event": "health",
            "payload": {"ok": True},
        })

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_async_handler(self):
        client = OpenClawClient()
        received = []

        async def async_handler(p):
            received.append(p)

        client.on_event("agent", async_handler)

        await client._dispatch_event({
            "type": "event",
            "event": "agent",
            "payload": {"test": True},
        })

        assert len(received) == 1


class TestOpenClawError:
    def test_error_attributes(self):
        err = OpenClawError("TIMEOUT", "Request timed out", retryable=True)
        assert err.code == "TIMEOUT"
        assert err.retryable is True
        assert "TIMEOUT" in str(err)
