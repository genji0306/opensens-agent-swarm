"""Knowledge base persistence for deep research.

Stores completed research results and accumulated lessons in JSONL files,
enabling cross-run learning. Prior knowledge is loaded at the start of
each research run to provide context.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["KnowledgeBase"]

logger = logging.getLogger("oas.deep_research.knowledge_base")


class KnowledgeBase:
    """Persistent knowledge store for deep research cross-run learning.

    Files:
    - ``knowledge.jsonl`` — completed research summaries (topic, score, sources)
    - ``global_lessons.jsonl`` — what worked/didn't across research runs
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def knowledge_path(self) -> Path:
        return self.base_dir / "knowledge.jsonl"

    @property
    def lessons_path(self) -> Path:
        return self.base_dir / "global_lessons.jsonl"

    def store_research(
        self,
        topic: str,
        score: float,
        summary: str,
        sources_count: int,
        iterations: int,
        converged: bool,
    ) -> None:
        """Store a completed research result."""
        entry = {
            "topic": topic,
            "score": round(score, 3),
            "summary": summary[:500],
            "sources_count": sources_count,
            "iterations": iterations,
            "converged": converged,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.knowledge_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        logger.debug("knowledge_stored", topic=topic[:80], score=score)

    def store_lesson(
        self,
        strategy: str,
        outcome: str,
        insight: str,
        topic: str = "",
    ) -> None:
        """Store a lesson learned from a research run."""
        entry = {
            "strategy": strategy,
            "outcome": outcome,
            "insight": insight,
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.lessons_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        logger.debug("lesson_stored", insight=insight[:80])

    def find_related(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Find knowledge entries related to a query by keyword overlap."""
        if not self.knowledge_path.exists():
            return []

        query_words = set(query.lower().split())
        scored: list[tuple[float, dict]] = []

        try:
            with open(self.knowledge_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    topic_words = set(entry.get("topic", "").lower().split())
                    overlap = len(query_words & topic_words)
                    if overlap > 0:
                        scored.append((overlap, entry))
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("knowledge_search_error", error=str(exc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_results]]

    def get_lessons(self, max_results: int = 10) -> list[dict[str, Any]]:
        """Get recent lessons for prompt injection."""
        if not self.lessons_path.exists():
            return []

        lessons: list[dict[str, Any]] = []
        try:
            with open(self.lessons_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    lessons.append(json.loads(line))
        except (json.JSONDecodeError, Exception):
            pass

        # Return most recent
        return lessons[-max_results:]

    def get_stats(self) -> dict[str, Any]:
        """Return knowledge base statistics."""
        knowledge_count = 0
        lessons_count = 0

        if self.knowledge_path.exists():
            knowledge_count = sum(1 for _ in open(self.knowledge_path) if _.strip())
        if self.lessons_path.exists():
            lessons_count = sum(1 for _ in open(self.lessons_path) if _.strip())

        return {
            "knowledge_entries": knowledge_count,
            "lessons": lessons_count,
            "path": str(self.base_dir),
        }
