"""Tests for the deep research knowledge base."""
import json
from pathlib import Path

import pytest

from oas_core.deep_research.knowledge_base import KnowledgeBase


class TestKnowledgeBase:
    def test_store_and_retrieve_research(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        kb.store_research(
            topic="quantum sensors",
            score=0.82,
            summary="Comprehensive review of quantum sensor applications.",
            sources_count=18,
            iterations=3,
            converged=True,
        )
        assert kb.knowledge_path.exists()
        lines = kb.knowledge_path.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["topic"] == "quantum sensors"
        assert entry["score"] == 0.82

    def test_store_lesson(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        kb.store_lesson(
            strategy="DuckDuckGo only",
            outcome="low source quality",
            insight="Always include bioRxiv for biology topics",
            topic="CRISPR research",
        )
        assert kb.lessons_path.exists()
        lessons = kb.get_lessons()
        assert len(lessons) == 1
        assert "bioRxiv" in lessons[0]["insight"]

    def test_find_related(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        kb.store_research("quantum sensors for environment", 0.80, "summary1", 10, 2, True)
        kb.store_research("machine learning optimization", 0.75, "summary2", 8, 3, True)
        kb.store_research("quantum computing circuits", 0.85, "summary3", 15, 1, True)

        related = kb.find_related("quantum sensor applications")
        assert len(related) >= 1
        # "quantum sensors for environment" should match best
        assert "quantum" in related[0]["topic"].lower()

    def test_find_related_empty(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        related = kb.find_related("nonexistent topic")
        assert related == []

    def test_get_lessons_order(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        for i in range(15):
            kb.store_lesson(f"strategy_{i}", f"outcome_{i}", f"insight_{i}")

        lessons = kb.get_lessons(max_results=5)
        assert len(lessons) == 5
        # Should be most recent
        assert lessons[-1]["strategy"] == "strategy_14"

    def test_get_stats(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        kb.store_research("topic1", 0.8, "summary", 10, 2, True)
        kb.store_research("topic2", 0.7, "summary", 8, 3, False)
        kb.store_lesson("s", "o", "i")

        stats = kb.get_stats()
        assert stats["knowledge_entries"] == 2
        assert stats["lessons"] == 1

    def test_empty_stats(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        stats = kb.get_stats()
        assert stats["knowledge_entries"] == 0
        assert stats["lessons"] == 0
