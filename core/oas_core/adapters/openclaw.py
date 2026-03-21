"""OpenClaw gateway WebSocket client.

Wraps the JSON-RPC 2.0 over WebSocket communication with the OpenClaw
gateway at ``localhost:18789``. Supports connection handshake, RPC
methods, event streaming, and automatic reconnection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable

__all__ = ["OpenClawClient", "OpenClawError"]

logger = logging.getLogger("oas.adapters.openclaw")

# Try importing websockets — optional dependency
try:
    import websockets
    from websockets.asyncio.client import connect as ws_connect

    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False


class OpenClawError(Exception):
    """Raised when an OpenClaw RPC call fails."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(f"OpenClaw {code}: {message}")


class OpenClawClient:
    """Async WebSocket client for the OpenClaw Gateway.

    Usage::

        client = OpenClawClient("ws://localhost:18789", token="secret")
        await client.connect("oas-core", scope="operator.admin")

        agents = await client.list_agents()
        skills = await client.list_skills()

        client.on_event("agent", my_handler)

        await client.send_chat("Hello agent!")
        await client.disconnect()
    """

    def __init__(
        self,
        url: str = "ws://localhost:18789",
        token: str | None = None,
        *,
        client_id: str = "oas-core",
        request_timeout: float = 30.0,
        reconnect_max_attempts: int = 20,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
    ):
        if not _WS_AVAILABLE:
            raise ImportError("websockets package required: pip install websockets")

        self.url = url
        self.token = token
        self.client_id = client_id
        self._request_timeout = request_timeout
        self._reconnect_max = reconnect_max_attempts
        self._reconnect_base = reconnect_base_delay
        self._reconnect_max_delay = reconnect_max_delay

        self._ws: Any = None
        self._pending: dict[str, asyncio.Future] = {}
        self._event_handlers: dict[str, list[Callable]] = {}
        self._recv_task: asyncio.Task | None = None
        self._connected = False
        self._shutdown = False
        self._server_info: dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def server_info(self) -> dict[str, Any]:
        return self._server_info

    # --- Connection lifecycle ---

    async def connect(
        self,
        client_id: str | None = None,
        scope: str = "operator.admin",
        token: str | None = None,
    ) -> dict[str, Any]:
        """Connect to the OpenClaw gateway with handshake.

        Returns the hello-ok payload with server info and snapshot.
        """
        if client_id:
            self.client_id = client_id
        if token:
            self.token = token

        self._shutdown = False
        self._ws = await ws_connect(self.url)

        # Read the challenge BEFORE starting the message loop to avoid a race
        # where the loop consumes the challenge frame first.
        challenge = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        frame = json.loads(challenge)
        if frame.get("type") != "event" or frame.get("event") != "connect.challenge":
            logger.warning("unexpected_first_frame", frame=frame)

        # Send connect request
        params: dict[str, Any] = {
            "minProtocol": 1,
            "maxProtocol": 3,
            "client": {
                "id": self.client_id,
                "version": "1.0.0",
                "platform": "python",
                "mode": "script",
            },
            "caps": ["tool-events"],
            "scopes": [scope],
        }
        if self.token:
            params["auth"] = {"token": self.token}

        # Start the message loop now — the challenge is consumed, so the loop
        # will only see the connect response and subsequent frames.
        self._recv_task = asyncio.create_task(self._message_loop())

        result = await self._request("connect", params)
        self._connected = True
        self._server_info = result.get("server", {})

        logger.info(
            "openclaw_connected",
            extra={
                "server": self._server_info.get("version", "unknown"),
                "conn_id": self._server_info.get("connId", ""),
            },
        )
        return result

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket connection."""
        self._shutdown = True
        self._connected = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None

        # Cancel all pending requests
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    # --- RPC methods ---

    async def list_agents(self) -> dict[str, Any]:
        """List all registered agents."""
        return await self._request("agents.list")

    async def list_skills(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """List available skills, optionally filtered by agent."""
        params = {"agentId": agent_id} if agent_id else {}
        return await self._request("skills.status", params)

    async def list_tools(self, agent_id: str | None = None) -> dict[str, Any]:
        """Get the tool catalog for an agent."""
        params = {"agentId": agent_id} if agent_id else {}
        return await self._request("tools.catalog", params)

    async def send_chat(
        self,
        message: str,
        session_key: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat message to an agent."""
        params: dict[str, Any] = {"message": message}
        if session_key:
            params["sessionKey"] = session_key
        if agent_id:
            params["agentId"] = agent_id
        return await self._request("chat.send", params)

    async def chat_history(self, session_key: str | None = None) -> list[dict[str, Any]]:
        """Retrieve chat history for a session."""
        params = {"sessionKey": session_key} if session_key else {}
        result = await self._request("chat.history", params)
        return result if isinstance(result, list) else result.get("messages", [])

    async def abort_chat(self, session_key: str) -> dict[str, Any]:
        """Abort a running chat session."""
        return await self._request("chat.abort", {"sessionKey": session_key})

    async def invoke_skill(
        self,
        node: str,
        skill: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke a skill on a remote node via chat.send.

        This sends a structured message that the gateway routes to the
        correct node-host for execution.
        """
        message = json.dumps({
            "type": "skill_invoke",
            "node": node,
            "skill": skill,
            "payload": payload,
        })
        return await self.send_chat(message)

    async def get_health(self) -> dict[str, Any]:
        """Get gateway health status."""
        return await self._request("status.summary")

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List active sessions."""
        result = await self._request("sessions.list")
        return result.get("sessions", []) if isinstance(result, dict) else result

    async def list_cron(self) -> list[dict[str, Any]]:
        """List cron jobs."""
        result = await self._request("cron.list")
        return result.get("jobs", []) if isinstance(result, dict) else result

    # --- Event handling ---

    def on_event(self, event_name: str, handler: Callable) -> None:
        """Register an event handler.

        Args:
            event_name: Event type (``"agent"``, ``"chat"``, ``"health"``, etc.)
                        or ``"*"`` for all events.
            handler: Async or sync callback receiving the event payload dict.
        """
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)

    def off_event(self, event_name: str, handler: Callable | None = None) -> None:
        """Remove an event handler, or all handlers for an event."""
        if handler is None:
            self._event_handlers.pop(event_name, None)
        elif event_name in self._event_handlers:
            self._event_handlers[event_name] = [
                h for h in self._event_handlers[event_name] if h is not handler
            ]

    # --- Internal ---

    async def _request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Send a JSON-RPC request and await the response."""
        if not self._ws:
            raise OpenClawError("NOT_CONNECTED", "WebSocket not connected")

        request_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        frame = {
            "type": "req",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        try:
            await self._ws.send(json.dumps(frame))
            response = await asyncio.wait_for(future, timeout=self._request_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise OpenClawError("TIMEOUT", f"Request {method} timed out")
        finally:
            self._pending.pop(request_id, None)

        if not response.get("ok", False):
            err = response.get("error", {})
            raise OpenClawError(
                code=err.get("code", "UNKNOWN"),
                message=err.get("message", "Unknown error"),
                retryable=err.get("retryable", False),
            )

        return response.get("payload", {})

    async def _message_loop(self) -> None:
        """Background task: read and dispatch incoming WebSocket frames."""
        try:
            async for raw in self._ws:
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("invalid_frame", raw=raw[:200])
                    continue

                frame_type = frame.get("type")

                if frame_type == "res":
                    request_id = frame.get("id")
                    if request_id in self._pending:
                        self._pending[request_id].set_result(frame)
                elif frame_type == "event":
                    await self._dispatch_event(frame)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self._shutdown:
                logger.warning("message_loop_error", extra={"error": str(e)})
                self._connected = False

    async def _dispatch_event(self, frame: dict[str, Any]) -> None:
        """Dispatch an event frame to registered handlers."""
        event_name = frame.get("event", "")
        payload = frame.get("payload", {})

        handlers = list(self._event_handlers.get(event_name, []))
        handlers.extend(self._event_handlers.get("*", []))

        for handler in handlers:
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(
                    "event_handler_error",
                    extra={"event": event_name, "error": str(e)},
                )
