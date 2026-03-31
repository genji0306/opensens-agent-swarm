"""Tests for rl_rollout middleware and RolloutSession."""
import json
from pathlib import Path

import pytest

from oas_core.rl import RolloutSession, RolloutTurn
from oas_core.middleware.rl_rollout import RolloutCollector


class TestRolloutSession:
    def test_create_session(self):
        s = RolloutSession(agent_type="research")
        assert s.agent_type == "research"
        assert s.source == "live"
        assert len(s.turns) == 0

    def test_add_turns(self):
        s = RolloutSession(agent_type="research")
        s.add_turn("system", "You are a researcher.", turn_type="side")
        s.add_turn("user", "Study CRISPR.")
        s.add_turn("assistant", "Based on literature...")
        assert len(s.turns) == 3
        assert s.turns[0].turn_type == "side"
        assert s.turns[1].turn_type == "main"

    def test_finalize(self):
        s = RolloutSession(agent_type="research")
        assert s.completed_at is None
        s.finalize()
        assert s.completed_at is not None

    def test_json_roundtrip(self):
        s = RolloutSession(agent_type="analyze", source="synthetic")
        s.add_turn("user", "Analyze this dataset.")
        s.add_turn("assistant", "The results show...")
        data = json.loads(s.model_dump_json())
        s2 = RolloutSession.model_validate(data)
        assert s2.agent_type == "analyze"
        assert s2.source == "synthetic"
        assert len(s2.turns) == 2


class TestRolloutCollector:
    def test_start_session(self, tmp_path):
        collector = RolloutCollector(rollouts_dir=tmp_path)
        session = collector.start_session("research", "req-001", "System prompt")
        assert session.agent_type == "research"
        assert session.session_id == "req-001"
        assert len(session.turns) == 1  # system prompt
        assert collector.active_session_count == 1

    def test_get_session(self, tmp_path):
        collector = RolloutCollector(rollouts_dir=tmp_path)
        collector.start_session("research", "req-001")
        assert collector.get_session("req-001") is not None
        assert collector.get_session("nonexistent") is None

    def test_finalize_writes_jsonl(self, tmp_path):
        collector = RolloutCollector(rollouts_dir=tmp_path)
        session = collector.start_session("research", "req-002")
        session.add_turn("user", "Study topic X.")
        session.add_turn("assistant", "Here are the findings on topic X...")

        path = collector.finalize_session(session)
        assert path is not None
        assert path.exists()
        assert path.suffix == ".jsonl"

        # Verify JSONL content
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent_type"] == "research"
        assert data["session_id"] == "req-002"

    def test_finalize_skips_no_assistant_turns(self, tmp_path):
        collector = RolloutCollector(rollouts_dir=tmp_path)
        session = collector.start_session("research", "req-003")
        session.add_turn("user", "Hello")
        # No assistant turn
        path = collector.finalize_session(session)
        assert path is None

    def test_disabled_collector(self, tmp_path):
        collector = RolloutCollector(rollouts_dir=tmp_path, enabled=False)
        session = collector.start_session("research", "req-004")
        session.add_turn("user", "Test")
        session.add_turn("assistant", "Response")
        path = collector.finalize_session(session)
        assert path is None

    def test_write_synthetic(self, tmp_path):
        collector = RolloutCollector(rollouts_dir=tmp_path)
        session = RolloutSession(agent_type="research", source="live")
        session.add_turn("user", "Debate topic")
        session.add_turn("assistant", "My position is...")

        path = collector.write_synthetic(session)
        assert path is not None
        assert "synthetic" in str(path)

    def test_stats(self, tmp_path):
        collector = RolloutCollector(rollouts_dir=tmp_path)
        stats = collector.stats
        assert stats["enabled"] is True
        assert stats["active_sessions"] == 0
        assert stats["live_files"] == 0
