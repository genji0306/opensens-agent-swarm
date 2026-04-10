"""Role-aware knowledge retrieval router.

Leader: index-first (reads index.md, navigates to specific pages)
DEV: embedding-first (semantic search over wiki pages)
Boss: summary-first (L0 abstracts only)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from oas_core.knowledge.types import KnowledgeArtifact

__all__ = ["RetrievalRouter"]

logger = logging.getLogger("oas.knowledge.retrieval")


class RetrievalRouter:
    """Role-aware knowledge retrieval.

    Different roles get different retrieval strategies optimised for
    their information needs and context window budgets.
    """

    def __init__(
        self,
        *,
        wiki_dir: str | Path,
        entity_store: Any | None = None,  # EntityStore
        embedding_index: Any | None = None,  # EmbeddingIndex
        memory_client: Any | None = None,  # MemoryClient
    ) -> None:
        self._wiki_dir = Path(wiki_dir)
        self._entity_store = entity_store
        self._embedding_index = embedding_index
        self._memory_client = memory_client

    async def retrieve(
        self,
        query: str,
        role: str,
        task_type: str = "",
        top_k: int = 5,
    ) -> list[KnowledgeArtifact]:
        """Retrieve knowledge artifacts for the given query and role.

        Supported roles: ``leader``, ``dev``, ``boss``.
        Falls back to the leader strategy for unknown roles.
        """
        if role == "leader":
            return await self._leader_retrieve(query, task_type, top_k)
        if role == "dev":
            return await self._dev_retrieve(query, top_k)
        if role == "boss":
            return await self._boss_retrieve(query, top_k)
        return await self._leader_retrieve(query, task_type, top_k)

    # ---- Leader strategy ----

    async def _leader_retrieve(
        self, query: str, task_type: str, top_k: int,
    ) -> list[KnowledgeArtifact]:
        """Index-first: entity store lookup, then wiki page search."""
        results: list[KnowledgeArtifact] = []

        # Check entity store first
        if self._entity_store:
            entities = self._entity_store.search_entities(query, limit=top_k)
            for ent in entities:
                claims = self._entity_store.get_claims(
                    ent["name"], status="active",
                )
                content = f"Entity: {ent['name']} ({ent['entity_type']})\n"
                if claims:
                    content += "Claims:\n" + "\n".join(
                        f"- {c['statement'][:200]}" for c in claims[:3]
                    )
                results.append(KnowledgeArtifact(
                    content=content,
                    source=f"entity:{ent['name']}",
                    relevance=0.8,
                    provenance={"entity_type": ent["entity_type"]},
                ))

        # Search wiki pages by filename match
        wiki_dir = self._wiki_dir / "wiki"
        if wiki_dir.exists():
            query_lower = query.lower()
            for md_file in wiki_dir.rglob("*.md"):
                if md_file.name == "index.md":
                    continue
                if query_lower in md_file.stem.lower():
                    text = md_file.read_text(encoding="utf-8")[:1000]
                    results.append(KnowledgeArtifact(
                        content=text,
                        source=str(md_file.relative_to(self._wiki_dir)),
                        relevance=0.7,
                    ))

        # Also try OpenViking
        results.extend(await self._openviking_search(query, top_k))

        return sorted(
            results, key=lambda a: a.relevance, reverse=True,
        )[:top_k]

    # ---- DEV strategy ----

    async def _dev_retrieve(
        self, query: str, top_k: int,
    ) -> list[KnowledgeArtifact]:
        """Embedding-first: semantic search over wiki pages.

        Falls back to entity store if embedding index is unavailable
        or query embedding is not provided.
        """
        results: list[KnowledgeArtifact] = []

        if self._entity_store:
            entities = self._entity_store.search_entities(query, limit=top_k)
            for ent in entities:
                results.append(KnowledgeArtifact(
                    content=(
                        f"{ent['name']}: "
                        f"{json.dumps(ent.get('properties', {}))}"
                    ),
                    source=f"entity:{ent['name']}",
                    relevance=0.7,
                ))

        return results[:top_k]

    # ---- Boss strategy ----

    async def _boss_retrieve(
        self, query: str, top_k: int,
    ) -> list[KnowledgeArtifact]:
        """Summary-first: L0 abstracts only from OpenViking."""
        results: list[KnowledgeArtifact] = []
        if self._memory_client:
            try:
                research = await self._memory_client.find_research(
                    query, limit=top_k,
                )
                for item in (research if isinstance(research, list) else []):
                    # L0 only -- short summaries
                    content = str(item.get("content", ""))[:300]
                    results.append(KnowledgeArtifact(
                        content=content,
                        source=f"openviking:{item.get('uri', 'unknown')}",
                        relevance=float(item.get("score", 0.5)),
                    ))
            except Exception:
                logger.debug("openviking_boss_search_failed", exc_info=True)
        return results[:top_k]

    # ---- OpenViking helper ----

    async def _openviking_search(
        self, query: str, top_k: int,
    ) -> list[KnowledgeArtifact]:
        """Search OpenViking for research items (shared helper)."""
        results: list[KnowledgeArtifact] = []
        if self._memory_client:
            try:
                research = await self._memory_client.find_research(
                    query, limit=top_k,
                )
                for item in (research if isinstance(research, list) else []):
                    results.append(KnowledgeArtifact(
                        content=str(
                            item.get("content", item.get("text", "")),
                        )[:1000],
                        source=f"openviking:{item.get('uri', 'unknown')}",
                        relevance=float(item.get("score", 0.5)),
                    ))
            except Exception:
                logger.debug("openviking_search_failed", exc_info=True)
        return results
