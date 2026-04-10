"""Embedding-based semantic search over wiki pages.

Uses LanceDB (embedded) for vector storage and mlx-embeddings for
local embedding generation on Apple Silicon.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

__all__ = ["EmbeddingIndex", "LANCEDB_AVAILABLE"]

logger = logging.getLogger("oas.knowledge.embedding")

try:
    import lancedb

    _LANCEDB_AVAILABLE = True
except ImportError:
    _LANCEDB_AVAILABLE = False

LANCEDB_AVAILABLE: bool = _LANCEDB_AVAILABLE


class EmbeddingIndex:
    """Embedded vector index for wiki semantic search.

    Wraps LanceDB with a simple add/search/delete interface.
    Pre-computed embedding vectors are required — this class does
    not call any embedding model itself.
    """

    def __init__(
        self,
        db_path: str | Path,
        table_name: str = "wiki_pages",
    ) -> None:
        if not _LANCEDB_AVAILABLE:
            raise RuntimeError(
                "lancedb not installed. Install with: pip install lancedb"
            )
        self._db_path = Path(db_path)
        self._table_name = table_name
        self._db: Any = None
        self._table: Any = None

    def _ensure_open(self) -> None:
        """Lazily connect to the LanceDB database and open the table."""
        if self._db is None:
            self._db = lancedb.connect(str(self._db_path))  # type: ignore[union-attr]
            try:
                self._table = self._db.open_table(self._table_name)
            except Exception:
                self._table = None

    def add(
        self,
        texts: list[str],
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> int:
        """Add documents with pre-computed embeddings.

        Returns the number of records inserted.
        """
        self._ensure_open()
        records: list[dict[str, Any]] = []
        for i, (text, doc_id, vec) in enumerate(zip(texts, ids, vectors)):
            record: dict[str, Any] = {
                "id": doc_id,
                "text": text,
                "vector": vec,
            }
            if metadata and i < len(metadata):
                record["metadata"] = metadata[i]
            records.append(record)

        if self._table is None:
            self._table = self._db.create_table(self._table_name, records)
        else:
            self._table.add(records)
        logger.info(
            "embedding_index_add",
            extra={"count": len(records), "table": self._table_name},
        )
        return len(records)

    def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search by vector similarity.

        Returns a list of dicts with keys: id, text, vector, _distance.
        """
        self._ensure_open()
        if self._table is None:
            return []
        q = self._table.search(query_vector).limit(limit)
        if filter_expr:
            q = q.where(filter_expr)
        return [dict(row) for row in q.to_list()]

    def delete(self, ids: list[str]) -> int:
        """Delete documents by ID. Returns the number of IDs requested."""
        self._ensure_open()
        if self._table is None:
            return 0
        filter_expr = " OR ".join(f"id = '{doc_id}'" for doc_id in ids)
        self._table.delete(filter_expr)
        logger.info(
            "embedding_index_delete",
            extra={"count": len(ids), "table": self._table_name},
        )
        return len(ids)

    def count(self) -> int:
        """Return the number of rows in the table."""
        self._ensure_open()
        if self._table is None:
            return 0
        return self._table.count_rows()

    def close(self) -> None:
        """Release the database connection."""
        self._db = None
        self._table = None
