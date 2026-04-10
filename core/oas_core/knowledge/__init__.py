"""LLM Wiki knowledge system -- Karpathy-pattern knowledge compounding.

Provides entity extraction, claim tracking, wiki page compilation,
embedding-based semantic search, and role-scoped retrieval.
"""

from __future__ import annotations

from oas_core.knowledge.embedding_index import EmbeddingIndex
from oas_core.knowledge.embeddings import (
    MLX_EMBEDDINGS_AVAILABLE,
    get_embedding_fn,
    hash_embedding,
)
from oas_core.knowledge.entity_store import EntityStore
from oas_core.knowledge.ingester import KnowledgeIngester
from oas_core.knowledge.retrieval import RetrievalRouter
from oas_core.knowledge.types import (
    Claim,
    Entity,
    KnowledgeArtifact,
    KnowledgeProvenance,
    WikiPage,
)

__all__ = [
    "KnowledgeIngester",
    "EntityStore",
    "RetrievalRouter",
    "EmbeddingIndex",
    "KnowledgeArtifact",
    "KnowledgeProvenance",
    "WikiPage",
    "Entity",
    "Claim",
    "get_embedding_fn",
    "hash_embedding",
    "MLX_EMBEDDINGS_AVAILABLE",
]
