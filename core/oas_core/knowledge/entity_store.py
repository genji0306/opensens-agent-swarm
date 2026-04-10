"""SQLite-backed entity-relationship graph for wiki knowledge.

Stores entities, claims, and relationships with provenance metadata.
Uses plain sqlite3 -- no ORM needed at this scale.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

__all__ = ["EntityStore"]

logger = logging.getLogger("oas.knowledge.entity_store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    name TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    properties TEXT DEFAULT '{}',
    first_seen REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    statement TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    sources TEXT DEFAULT '[]',
    provenance TEXT DEFAULT '{}',
    status TEXT DEFAULT 'active',
    superseded_by TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS relationships (
    from_entity TEXT NOT NULL,
    to_entity TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at REAL NOT NULL,
    PRIMARY KEY (from_entity, to_entity, relation_type),
    FOREIGN KEY (from_entity) REFERENCES entities(name),
    FOREIGN KEY (to_entity) REFERENCES entities(name)
);
CREATE INDEX IF NOT EXISTS idx_claims_topic ON claims(topic);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_entity);
CREATE INDEX IF NOT EXISTS idx_relationships_to ON relationships(to_entity);
"""


class EntityStore:
    """SQLite-backed store for entities, claims, and relationships."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    # ---- Entities ----

    def add_entity(
        self,
        name: str,
        entity_type: str,
        aliases: list[str] | None = None,
        properties: dict[str, str] | None = None,
    ) -> None:
        """Insert or replace an entity."""
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO entities "
            "(name, entity_type, aliases, properties, first_seen, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                name,
                entity_type,
                json.dumps(aliases or []),
                json.dumps(properties or {}),
                now,
                now,
            ),
        )
        self._conn.commit()

    def get_entity(self, name: str) -> dict[str, Any] | None:
        """Fetch a single entity by name. Returns None if not found."""
        row = self._conn.execute(
            "SELECT * FROM entities WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search entities by name substring and optional type filter."""
        sql = "SELECT * FROM entities WHERE name LIKE ?"
        params: list[Any] = [f"%{query}%"]
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        return [
            self._row_to_dict(r)
            for r in self._conn.execute(sql, params).fetchall()
        ]

    # ---- Claims ----

    def add_claim(
        self,
        claim_id: str,
        topic: str,
        statement: str,
        confidence: float = 0.5,
        sources: list[str] | None = None,
        provenance: dict[str, str] | None = None,
    ) -> None:
        """Insert or replace a claim."""
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO claims "
            "(claim_id, topic, statement, confidence, sources, provenance, "
            "status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                claim_id,
                topic,
                statement,
                confidence,
                json.dumps(sources or []),
                json.dumps(provenance or {}),
                now,
                now,
            ),
        )
        self._conn.commit()

    def get_claims(
        self,
        topic: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all claims for a topic, optionally filtered by status."""
        sql = "SELECT * FROM claims WHERE topic = ?"
        params: list[Any] = [topic]
        if status:
            sql += " AND status = ?"
            params.append(status)
        return [
            self._row_to_dict(r)
            for r in self._conn.execute(sql, params).fetchall()
        ]

    def supersede_claim(self, claim_id: str, superseded_by: str) -> None:
        """Mark a claim as superseded by another."""
        now = time.time()
        self._conn.execute(
            "UPDATE claims SET status = 'superseded', "
            "superseded_by = ?, updated_at = ? WHERE claim_id = ?",
            (superseded_by, now, claim_id),
        )
        self._conn.commit()

    # ---- Relationships ----

    def add_relationship(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or replace a relationship between two entities."""
        self._conn.execute(
            "INSERT OR REPLACE INTO relationships "
            "(from_entity, to_entity, relation_type, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                from_entity,
                to_entity,
                relation_type,
                json.dumps(metadata or {}),
                time.time(),
            ),
        )
        self._conn.commit()

    def get_relationships(self, entity_name: str) -> list[dict[str, Any]]:
        """Get all relationships involving an entity (inbound or outbound)."""
        rows = self._conn.execute(
            "SELECT * FROM relationships "
            "WHERE from_entity = ? OR to_entity = ?",
            (entity_name, entity_name),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ---- Stats ----

    def stats(self) -> dict[str, int]:
        """Return counts of entities, claims, and relationships."""
        entities = self._conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]
        claims = self._conn.execute(
            "SELECT COUNT(*) FROM claims"
        ).fetchone()[0]
        relationships = self._conn.execute(
            "SELECT COUNT(*) FROM relationships"
        ).fetchone()[0]
        return {
            "entities": entities,
            "claims": claims,
            "relationships": relationships,
        }

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    # ---- Internal ----

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict, deserialising JSON columns."""
        d = dict(row)
        for key in ("aliases", "sources", "properties", "provenance", "metadata"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except json.JSONDecodeError:
                    pass
        return d
