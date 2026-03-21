"""Handoff tool factory with Paperclip governance awareness.

Creates LangChain tools that transfer control between agents while
recording the handoff as a Paperclip activity event and emitting a
DRVP ``HANDOFF_STARTED`` event.

DRVP emission happens at the node level (in ``wrap_agent_as_node`` and
``leader_node`` in swarm.py), not in the tool itself — because the
handoff tool returns a synchronous ``Command``, not an awaitable.

Requires ``oas-core[swarm]`` optional dependencies.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("oas.handoff")

__all__ = ["create_governed_handoff"]

try:
    from langgraph_swarm import create_handoff_tool as _base_handoff
    _SWARM_AVAILABLE = True
except ImportError:
    _SWARM_AVAILABLE = False


def create_governed_handoff(
    agent_name: str,
    description: str,
    *,
    paperclip_client: Any | None = None,
    company_id: str | None = None,
    from_agent: str = "leader",
    device: str = "leader",
) -> Any:
    """Create a handoff tool that wraps the base ``create_handoff_tool``.

    The tool itself delegates to ``langgraph_swarm.create_handoff_tool``
    and attaches governance metadata. DRVP events are emitted at the
    graph node level (see ``swarm.py`` leader_node and wrap_agent_as_node).

    Parameters
    ----------
    agent_name : str
        Target agent name (must match a node in the swarm graph).
    description : str
        Natural-language description of when to transfer to this agent.
    paperclip_client : Any | None
        PaperclipClient instance for activity logging (stored as metadata).
    company_id : str | None
        Paperclip company identifier.
    from_agent : str
        Name of the originating agent (default "leader").
    device : str
        Device identifier (default "leader").
    """
    if not _SWARM_AVAILABLE:
        raise ImportError(
            "langgraph-swarm not installed. Run: uv pip install 'oas-core[swarm]'"
        )

    base_tool = _base_handoff(agent_name=agent_name, description=description)

    # Attach governance metadata for the swarm builder to read
    if not hasattr(base_tool, "metadata") or base_tool.metadata is None:
        base_tool.metadata = {}
    base_tool.metadata["governed"] = True
    base_tool.metadata["from_agent"] = from_agent
    base_tool.metadata["device"] = device
    if paperclip_client is not None:
        base_tool.metadata["paperclip_client"] = paperclip_client
    if company_id is not None:
        base_tool.metadata["company_id"] = company_id

    return base_tool
