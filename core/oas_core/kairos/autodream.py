"""AutoDream — nightly knowledge base consolidation (§9.2).

Runs at 03:00 local inside a forked subprocess so a crash cannot
affect the main Leader process. The pipeline:

1. Snapshot current KB (knowledge.jsonl + global_lessons.jsonl)
2. Deduplicate entries by content hash
3. Merge closely related lessons
4. Prune stale entries (> retention_days)
5. Write consolidated KB atomically

All inference borrows DEV compute — KAIROS never calls cloud.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["AutoDream", "DreamResult"]

logger = logging.getLogger("oas.kairos.autodream")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1.0, 1.0]. Returns 0.0 on mismatched dims."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


@dataclass(frozen=True)
class DreamResult:
    """Result of a nightly autoDream run."""

    entries_before: int = 0
    entries_after: int = 0
    deduplicated: int = 0
    pruned: int = 0
    merged: int = 0
    duration_s: float = 0.0
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries_before": self.entries_before,
            "entries_after": self.entries_after,
            "deduplicated": self.deduplicated,
            "pruned": self.pruned,
            "merged": self.merged,
            "duration_s": round(self.duration_s, 2),
            "succeeded": self.succeeded,
            "error": self.error,
        }


class AutoDream:
    """Knowledge base consolidation engine.

    Can be run directly (``consolidate()``) or via ``ForkedWorker``
    for subprocess isolation.
    """

    def __init__(
        self,
        *,
        kb_dir: str | Path,
        retention_days: int = 90,
        similarity_threshold: float = 0.85,
        embedding_fn: Any = None,
    ) -> None:
        self._kb_dir = Path(kb_dir).expanduser().resolve()
        self._retention_days = retention_days
        self._similarity_threshold = similarity_threshold
        # Optional embedding function: str -> list[float]
        # When provided, semantic merge uses cosine similarity instead of
        # prefix matching. Must be a plain function (forked worker safe).
        self._embedding_fn = embedding_fn

    def consolidate(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run the full consolidation pipeline.

        This is the entry point for both direct and forked-worker
        invocation. ``payload`` is ignored (present for ForkedWorker
        signature compatibility).
        """
        start = time.monotonic()
        knowledge_path = self._kb_dir / "knowledge.jsonl"
        lessons_path = self._kb_dir / "global_lessons.jsonl"

        try:
            entries = self._load_entries(knowledge_path) + self._load_entries(lessons_path)
        except Exception as exc:
            return DreamResult(error=f"load failed: {exc}").to_dict()

        before = len(entries)

        # Step 1: deduplicate by content hash
        entries, dedup_count = self._deduplicate(entries)

        # Step 2: prune stale entries
        entries, prune_count = self._prune_stale(entries)

        # Step 3: merge similar (placeholder — needs inference for
        # real semantic similarity; for now uses exact-prefix matching)
        entries, merge_count = self._merge_similar(entries)

        after = len(entries)
        duration = time.monotonic() - start

        # Write back atomically
        try:
            self._write_entries(knowledge_path, [e for e in entries if e.get("type") != "lesson"])
            self._write_entries(lessons_path, [e for e in entries if e.get("type") == "lesson"])
        except Exception as exc:
            return DreamResult(
                entries_before=before,
                entries_after=after,
                error=f"write failed: {exc}",
                duration_s=duration,
            ).to_dict()

        result = DreamResult(
            entries_before=before,
            entries_after=after,
            deduplicated=dedup_count,
            pruned=prune_count,
            merged=merge_count,
            duration_s=duration,
        )
        logger.info(
            "autodream_completed",
            extra=result.to_dict(),
        )
        return result.to_dict()

    def _load_entries(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries

    def _write_entries(self, path: Path, entries: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, default=str) + "\n")
        tmp.replace(path)

    def _deduplicate(
        self, entries: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for entry in entries:
            content = entry.get("content", entry.get("text", ""))
            h = hashlib.sha256(str(content).encode()).hexdigest()[:16]
            if h not in seen:
                seen.add(h)
                unique.append(entry)
        return unique, len(entries) - len(unique)

    def _prune_stale(
        self, entries: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        cutoff = time.time() - (self._retention_days * 86400)
        kept: list[dict[str, Any]] = []
        for entry in entries:
            ts = entry.get("timestamp", entry.get("created_at"))
            if ts is not None:
                try:
                    if float(ts) < cutoff:
                        continue
                except (TypeError, ValueError):
                    pass
            kept.append(entry)
        return kept, len(entries) - len(kept)

    def _merge_similar(
        self, entries: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        """Merge entries whose content is semantically similar.

        Two strategies, chosen at construction time:

        1. ``embedding_fn`` provided → compute vectors for each entry's
           content and drop any entry whose cosine similarity to an
           already-kept entry exceeds ``similarity_threshold``. This is
           the Phase 25 path via ``mlx-embeddings`` or an equivalent
           local model.

        2. No embedding function → fall back to exact prefix dedup on
           the first 100 characters. This is the Phase 24 placeholder
           behaviour retained for environments without the embedding
           stack installed.
        """
        if self._embedding_fn is not None:
            return self._merge_semantic(entries)
        return self._merge_by_prefix(entries)

    def _merge_by_prefix(
        self, entries: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        seen_prefixes: set[str] = set()
        merged: list[dict[str, Any]] = []
        count = 0
        for entry in entries:
            content = str(entry.get("content", entry.get("text", "")))
            prefix = content[:100].lower().strip()
            if prefix and prefix in seen_prefixes:
                count += 1
                continue
            if prefix:
                seen_prefixes.add(prefix)
            merged.append(entry)
        return merged, count

    def _merge_semantic(
        self, entries: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        kept: list[dict[str, Any]] = []
        kept_vectors: list[list[float]] = []
        count = 0
        for entry in entries:
            content = str(entry.get("content", entry.get("text", ""))).strip()
            if not content:
                kept.append(entry)
                continue
            try:
                vec = self._embedding_fn(content)
            except Exception as exc:
                logger.warning(
                    "autodream_embed_failed",
                    extra={"error": str(exc)},
                )
                kept.append(entry)
                continue
            merged = False
            for existing in kept_vectors:
                if _cosine_similarity(vec, existing) >= self._similarity_threshold:
                    merged = True
                    count += 1
                    break
            if not merged:
                kept.append(entry)
                kept_vectors.append(vec)
        return kept, count
