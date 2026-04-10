"""Shared research result type for all research backend adapters.

This module has zero optional dependencies so it can be imported safely
by any adapter, the router, and the deep research orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["ResearchResult"]


@dataclass
class ResearchResult:
    """Unified result from any research backend (LabClaw, InternAgent, DeerFlow, etc.).

    When a backend is unavailable, it returns a stub with ``available=False``
    so the router can skip gracefully without crashing.
    """

    query: str
    output: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    available: bool = True
    backend: str = ""  # "labclaw" | "internagent" | "deerflow" | "uniscientist" | etc.
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
