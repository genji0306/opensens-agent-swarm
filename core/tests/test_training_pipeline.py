"""Tests for the RL training pipeline."""
import json
from pathlib import Path

import pytest

from oas_core.rl import RolloutSession
from oas_core.rl.training_pipeline import TrainingPipeline, ScoredRollout


def _make_session(agent_type: str = "research", source: str = "live", n_turns: int = 3) -> RolloutSession:
    s = RolloutSession(agent_type=agent_type, source=source)
    s.add_turn("system", "You are a researcher.", turn_type="side")
    for i in range(n_turns):
        s.add_turn("user", f"Question {i}")
        s.add_turn("assistant", f"Answer {i} with detailed explanation about the topic " * 10)
    s.finalize()
    return s


def _write_rollouts(dir_path: Path, sessions: list[RolloutSession], source: str = "live"):
    source_dir = dir_path / source
    source_dir.mkdir(parents=True, exist_ok=True)
    with open(source_dir / "test.jsonl", "w") as f:
        for s in sessions:
            f.write(s.model_dump_json() + "\n")


class TestTrainingPipeline:
    def test_load_rollouts(self, tmp_path):
        sessions = [_make_session() for _ in range(5)]
        _write_rollouts(tmp_path, sessions)

        pipeline = TrainingPipeline(rollouts_dir=tmp_path)
        loaded = pipeline.load_rollouts("research", "live")
        assert len(loaded) == 5

    def test_load_rollouts_filters_by_agent(self, tmp_path):
        sessions = [_make_session("research"), _make_session("analyze")]
        _write_rollouts(tmp_path, sessions)

        pipeline = TrainingPipeline(rollouts_dir=tmp_path)
        loaded = pipeline.load_rollouts("research", "live")
        assert len(loaded) == 1

    def test_load_rollouts_empty_dir(self, tmp_path):
        pipeline = TrainingPipeline(rollouts_dir=tmp_path)
        loaded = pipeline.load_rollouts("research", "live")
        assert len(loaded) == 0

    def test_score_rollouts_heuristic(self, tmp_path):
        sessions = [_make_session() for _ in range(3)]
        pipeline = TrainingPipeline(rollouts_dir=tmp_path, min_session_score=0.0)
        scored = pipeline.score_rollouts(sessions)
        assert len(scored) == 3
        for s in scored:
            assert s.aggregate_score > 0
            assert len(s.turn_scores) > 0

    def test_score_rollouts_filters_low_scores(self, tmp_path):
        # Create a session with very short responses (low heuristic score)
        s = RolloutSession(agent_type="research")
        s.add_turn("user", "Hi")
        s.add_turn("assistant", "Ok")  # Very short
        s.finalize()

        pipeline = TrainingPipeline(rollouts_dir=tmp_path, min_session_score=0.5)
        scored = pipeline.score_rollouts([s])
        assert len(scored) == 0  # Filtered out

    def test_assemble_batch(self, tmp_path):
        sessions = [_make_session() for _ in range(20)]
        pipeline = TrainingPipeline(rollouts_dir=tmp_path, batch_size=16, min_session_score=0.0)
        scored = pipeline.score_rollouts(sessions)
        batch = pipeline.assemble_batch("research", scored)
        assert batch is not None
        assert batch.total == 16
        assert batch.agent_type == "research"

    def test_assemble_batch_insufficient(self, tmp_path):
        sessions = [_make_session() for _ in range(3)]
        pipeline = TrainingPipeline(rollouts_dir=tmp_path, batch_size=16, min_session_score=0.0)
        scored = pipeline.score_rollouts(sessions)
        batch = pipeline.assemble_batch("research", scored)
        assert batch is None

    def test_assemble_batch_mixed_sources(self, tmp_path):
        live = [_make_session(source="live") for _ in range(12)]
        synthetic = [_make_session(source="synthetic") for _ in range(8)]
        pipeline = TrainingPipeline(
            rollouts_dir=tmp_path,
            batch_size=16,
            synthetic_weight=0.3,
            min_session_score=0.0,
        )
        scored_live = pipeline.score_rollouts(live)
        scored_synthetic = pipeline.score_rollouts(synthetic)
        batch = pipeline.assemble_batch("research", scored_live, scored_synthetic)
        assert batch is not None
        assert batch.total == 16
        assert batch.live_count + batch.synthetic_count == 16
