"""Knowledge system data types — frozen Pydantic models and dataclasses.

All types are immutable (frozen=True) to prevent accidental mutation
and enable safe sharing across async boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "KnowledgeProvenance",
    "Entity",
    "Claim",
    "WikiPage",
    "KnowledgeArtifact",
]


@dataclass(frozen=True)
class KnowledgeProvenance:
    """Tracks the origin of a knowledge entry."""

    agent_id: str
    mission_id: str
    campaign_id: str
    model_tier: str
    confidence: float
    timestamp: datetime
    sources: tuple[str, ...]  # DOIs, URLs, file paths (tuple for frozen)


class Entity(BaseModel, frozen=True):
    """A named entity extracted from research output."""

    name: str
    entity_type: str  # "material", "concept", "method", "compound", etc.
    aliases: tuple[str, ...] = ()
    properties: dict[str, str] = Field(default_factory=dict)
    first_seen: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class Claim(BaseModel, frozen=True):
    """A factual claim extracted from research output."""

    topic: str
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: tuple[str, ...] = ()
    provenance: dict[str, str] = Field(default_factory=dict)
    status: str = "active"  # active, superseded, disputed, unverified
    superseded_by: str | None = None


class WikiPage(BaseModel, frozen=True):
    """A wiki page in the knowledge system."""

    path: str  # relative to wiki root
    title: str
    page_type: str  # "entity", "concept", "campaign", "lesson"
    summary: str  # L0 abstract
    content: str  # Full page content (markdown)
    entities: tuple[str, ...] = ()
    cross_refs: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()  # claim IDs
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class KnowledgeArtifact(BaseModel, frozen=True):
    """A retrieved knowledge item with relevance score."""

    content: str
    source: str  # wiki page path or KB entry ID
    relevance: float = 0.0
    provenance: dict[str, str] = Field(default_factory=dict)
