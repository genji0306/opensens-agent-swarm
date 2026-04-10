"""openviking-memory MCP server.

Exposes the OpenViking long-term memory store as a Model Context
Protocol server. External tools can read tiered context, do semantic
search, and persist new findings without importing the full OAS
framework.

Tools exposed:
  - read_context: Read tiered context for a session (L0 hot / L1 warm / L2 cold)
  - search_memory: Semantic search across stored memories
  - write_finding: Persist a new finding with tags and tier
  - list_sessions: List recent session IDs with summaries
  - session_context: Load full context for one session ID

Requires ``OPENVIKING_URL`` in the environment (falls back to an in-memory
stub store if unset — useful for local testing).

Run with::

    python -m oas_core.mcp.openviking_memory
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    Server = None  # type: ignore[assignment,misc]
    Tool = None  # type: ignore[assignment,misc]
    TextContent = None  # type: ignore[assignment,misc]

logger = logging.getLogger("oas.mcp.openviking_memory")

__all__ = ["create_server", "main", "StubMemoryStore"]


@dataclass
class StubMemoryStore:
    """In-process fallback when OPENVIKING_URL is not configured.

    Not durable across process restarts. Used when the real OpenViking
    service is unavailable, so the MCP server still accepts reads and
    writes without returning errors. Real deployments should set the
    OPENVIKING_URL env var.
    """

    entries: list[dict[str, Any]] = field(default_factory=list)

    def read(self, session_id: str, tiers: list[int]) -> list[dict[str, Any]]:
        return [
            e for e in self.entries
            if e.get("session_id") == session_id and e.get("tier", 1) in tiers
        ]

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        q = query.lower()
        matches = []
        for e in self.entries:
            content = str(e.get("content", "")).lower()
            tags = " ".join(str(t).lower() for t in e.get("tags", []))
            if q in content or q in tags:
                matches.append(e)
        return matches[-limit:]

    def write(self, session_id: str, content: str, tags: list[str], tier: int) -> dict[str, Any]:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "session_id": session_id,
            "content": content,
            "tags": tags,
            "tier": tier,
            "ts": time.time(),
        }
        self.entries.append(entry)
        return entry

    def list_sessions(self, limit: int) -> list[dict[str, Any]]:
        sessions: dict[str, dict[str, Any]] = {}
        for e in self.entries:
            sid = e.get("session_id", "")
            if sid and sid not in sessions:
                sessions[sid] = {
                    "session_id": sid,
                    "entry_count": 0,
                    "first_seen": e.get("ts", 0),
                    "last_seen": e.get("ts", 0),
                }
            if sid:
                sessions[sid]["entry_count"] += 1
                sessions[sid]["last_seen"] = max(sessions[sid]["last_seen"], e.get("ts", 0))
        return sorted(sessions.values(), key=lambda s: s["last_seen"], reverse=True)[:limit]

    def session_context(self, session_id: str) -> dict[str, Any]:
        entries = [e for e in self.entries if e.get("session_id") == session_id]
        return {
            "session_id": session_id,
            "entry_count": len(entries),
            "entries": entries,
            "tags": sorted({t for e in entries for t in e.get("tags", [])}),
        }


_STORE: StubMemoryStore | None = None


def _get_store() -> StubMemoryStore:
    global _STORE
    if _STORE is None:
        _STORE = StubMemoryStore()
        url = os.getenv("OPENVIKING_URL", "")
        if url:
            logger.info("openviking_url_configured", extra={"url": url})
        else:
            logger.warning("openviking_stub_mode — OPENVIKING_URL not set")
    return _STORE


def create_server() -> Any:
    """Construct an MCP Server with the openviking-memory tools registered."""
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "mcp SDK not installed. Install with: pip install mcp"
        )

    server = Server("oas-openviking-memory")  # type: ignore[misc]

    @server.list_tools()
    async def list_tools() -> list[Any]:
        return [
            Tool(  # type: ignore[misc]
                name="read_context",
                description=(
                    "Read tiered memory context for a session. "
                    "L0 = hot (always cheap), L1 = warm (campaign-level), L2 = cold (deep retrieval)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "tiers": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of tier numbers to read (0, 1, 2). Default: [0, 1].",
                        },
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(  # type: ignore[misc]
                name="search_memory",
                description="Semantic search across all stored memories. Returns entries sorted by relevance.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "description": "Max results (default 5)"},
                    },
                    "required": ["query"],
                },
            ),
            Tool(  # type: ignore[misc]
                name="write_finding",
                description="Persist a new finding to OpenViking with tags and tier.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "content": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Topical tags for later retrieval",
                        },
                        "tier": {
                            "type": "integer",
                            "description": "0 = hot, 1 = warm, 2 = cold (default 1)",
                        },
                    },
                    "required": ["session_id", "content"],
                },
            ),
            Tool(  # type: ignore[misc]
                name="list_sessions",
                description="List recent session IDs with entry counts and timestamps.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max sessions to return (default 10)"},
                    },
                },
            ),
            Tool(  # type: ignore[misc]
                name="session_context",
                description="Load the full context for one session ID — all entries and tags.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                    },
                    "required": ["session_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
        store = _get_store()

        if name == "read_context":
            session_id = arguments.get("session_id", "")
            tiers = arguments.get("tiers", [0, 1]) or [0, 1]
            results = store.read(session_id, tiers)
            return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]  # type: ignore[misc]

        if name == "search_memory":
            query = arguments.get("query", "")
            limit = int(arguments.get("limit", 5))
            results = store.search(query, limit)
            return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]  # type: ignore[misc]

        if name == "write_finding":
            session_id = arguments.get("session_id", "")
            content = arguments.get("content", "")
            tags = arguments.get("tags", []) or []
            tier = int(arguments.get("tier", 1))
            entry = store.write(session_id, content, tags, tier)
            return [TextContent(type="text", text=json.dumps(entry, indent=2, default=str))]  # type: ignore[misc]

        if name == "list_sessions":
            limit = int(arguments.get("limit", 10))
            sessions = store.list_sessions(limit)
            return [TextContent(type="text", text=json.dumps(sessions, indent=2, default=str))]  # type: ignore[misc]

        if name == "session_context":
            session_id = arguments.get("session_id", "")
            ctx = store.session_context(session_id)
            return [TextContent(type="text", text=json.dumps(ctx, indent=2, default=str))]  # type: ignore[misc]

        return [TextContent(type="text", text=f'{{"error": "unknown tool: {name}"}}')]  # type: ignore[misc]

    return server


async def _run() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):  # type: ignore[misc]
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    if not _MCP_AVAILABLE:
        raise SystemExit(
            "mcp SDK not installed. Install with: pip install mcp"
        )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
