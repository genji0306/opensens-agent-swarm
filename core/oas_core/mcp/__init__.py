"""OAS MCP servers — model-router and openviking-memory.

These expose OAS internals as Model Context Protocol servers so that
other Claude Code sessions, research agents, or external tools can
query routing decisions and long-term memory without importing the
full OAS framework.

Entry points::

    python -m oas_core.mcp.model_router
    python -m oas_core.mcp.openviking_memory

Both are stdio MCP servers following the Anthropic MCP SDK pattern.
"""
from __future__ import annotations

__all__: list[str] = []
