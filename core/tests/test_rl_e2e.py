"""End-to-end tests for the RL training cycle.

Tests the full pipeline: collect rollout → score → assemble batch →
evaluate checkpoint → promotion gate decision.
"""
import json
from pathlib import Path

import pytest

from oas_core.rl import RolloutSession, CheckpointMeta, BaselineMeta
from oas_core.middleware.rl_rollout import RolloutCollector
from oas_core.rl.training_pipeline import TrainingPipeline
from oas_core.rl.checkpoint_eval import CheckpointEvaluator
from oas_core.rl.promotion_gate import PromotionGate
from oas_core.rl.data_manager import DataManager


def _create_baseline(baselines_dir: Path, agent_type: str = "research", score: float = 0.72):
    """Create a baseline snapshot file."""
    baseline = {
        "agent_type": agent_type,
        "version": f"{agent_type}-v0",
        "base_model": "Qwen/Qwen3-4B-Instruct-2507",
        "evaluation_scores": {"aggregate": score},
    }
    (baselines_dir / f"{agent_type}-v0.json").write_text(json.dumps(baseline))


def _write_rollouts(rollouts_dir: Path, agent_type: str, n: int = 20, source: str = "live"):
    """Write N rollout sessions to JSONL."""
    source_dir = rollouts_dir / source
    source_dir.mkdir(parents=True, exist_ok=True)
    with open(source_dir / "e2e-test.jsonl", "w") as f:
        for i in range(n):
            s = RolloutSession(agent_type=agent_type, source=source)
            s.add_turn("system", "You are a researcher.", turn_type="side")
            s.add_turn("user", f"Research topic {i}: quantum sensors for environmental monitoring")
            s.add_turn("assistant", f"Based on comprehensive literature review of topic {i}, " * 20)
            s.finalize()
            f.write(s.model_dump_json() + "\n")


class TestFullRLCycle:
    """Test the complete RL training cycle end-to-end."""

    def test_collect_score_batch_eval_promote(self, tmp_path):
        """E2E: rollout collection → scoring → batch → eval → promotion."""
        rl_dir = tmp_path / "rl"
        rollouts_dir = rl_dir / "rollouts"
        baselines_dir = rl_dir / "baselines"
        evaluations_dir = rl_dir / "evaluations"
        baselines_dir.mkdir(parents=True)
        evaluations_dir.mkdir(parents=True)

        # 1. Create baseline
        _create_baseline(baselines_dir, "research", score=0.72)

        # 2. Collect rollouts
        _write_rollouts(rollouts_dir, "research", n=20)

        # 3. Load and score
        pipeline = TrainingPipeline(
            rollouts_dir=rollouts_dir,
            batch_size=16,
            min_session_score=0.0,
        )
        live = pipeline.load_rollouts("research", "live")
        assert len(live) == 20

        scored = pipeline.score_rollouts(live)
        assert len(scored) > 0

        # 4. Assemble batch
        batch = pipeline.assemble_batch("research", scored)
        assert batch is not None
        assert batch.total == 16

        # 5. Evaluate checkpoint
        evaluator = CheckpointEvaluator(
            evaluations_dir=evaluations_dir,
            baselines_dir=baselines_dir,
        )
        test_prompts = [
            {"prompt_id": f"p{i:03d}", "prompt": f"Research prompt {i}"}
            for i in range(10)
        ]
        eval_result = evaluator.evaluate(
            checkpoint_id="research-ckpt-001",
            agent_type="research",
            test_prompts=test_prompts,
        )
        assert eval_result.n_prompts == 10
        assert eval_result.aggregate_score > 0

        # 6. Promotion gate
        gate = PromotionGate(min_score=0.7)
        decision = gate.evaluate(
            checkpoint_id="research-ckpt-001",
            eval_score=eval_result.aggregate_score,
            baseline_score=0.72,
        )
        assert isinstance(decision.promoted, bool)
        assert decision.checkpoint_id == "research-ckpt-001"

    def test_rollout_collector_to_pipeline(self, tmp_path):
        """E2E: RolloutCollector writes → TrainingPipeline reads."""
        rollouts_dir = tmp_path / "rollouts"

        # Collect via middleware
        collector = RolloutCollector(rollouts_dir=rollouts_dir)
        for i in range(5):
            session = collector.start_session("research", f"req-{i:03d}")
            session.add_turn("user", f"Question {i}")
            session.add_turn("assistant", f"Detailed answer about topic {i} " * 15)
            collector.finalize_session(session)

        # Read via pipeline
        pipeline = TrainingPipeline(rollouts_dir=rollouts_dir, batch_size=3, min_session_score=0.0)
        loaded = pipeline.load_rollouts("research", "live")
        assert len(loaded) == 5

        scored = pipeline.score_rollouts(loaded)
        assert len(scored) == 5

    def test_data_manager_cleanup_after_training(self, tmp_path):
        """E2E: DataManager cleans up old data after training cycles."""
        rl_dir = tmp_path / "rl"
        _write_rollouts(rl_dir / "rollouts", "research", n=30)

        # Create excess checkpoints
        for i in range(15):
            d = rl_dir / "checkpoints" / f"research-ckpt-{i:03d}"
            d.mkdir(parents=True)
            (d / "adapter.bin").write_text("fake")

        dm = DataManager(rl_dir=rl_dir, max_checkpoints=5, max_rollout_files=10)
        results = dm.run_cleanup(agent_types=["research"])

        assert results["old_checkpoints"] == 10  # 15 - 5
        # Rollout cleanup depends on file count
        stats = dm.get_storage_stats()
        assert stats["checkpoints"]["files"] <= 5


class TestDebateToTrainingE2E:
    """Test debate transcript → rollout → training pipeline integration."""

    def test_debate_to_rollout_to_batch(self, tmp_path):
        """E2E: MiroShark transcript → converter → collector → pipeline."""
        from oas_core.rl.transcript_converter import TranscriptConverter, DebateTranscript

        rollouts_dir = tmp_path / "rollouts"
        collector = RolloutCollector(rollouts_dir=rollouts_dir)

        # 1. Create debate transcripts
        transcripts = []
        for i in range(5):
            rounds = []
            for r in range(8):
                rounds.append({
                    "round": r,
                    "actions": [
                        {"agent_name": "Expert", "agent_type": "research", "platform": "twitter",
                         "content": f"Round {r}: Evidence strongly supports the hypothesis about topic {i}. " * 5},
                        {"agent_name": "Critic", "agent_type": "contrarian", "platform": "reddit",
                         "content": f"Round {r}: The methodology has critical flaws. " * 5},
                    ],
                })
            transcripts.append(DebateTranscript(
                debate_id=f"debate-{i:03d}",
                topic=f"Hypothesis {i}: Novel sensor materials improve sensitivity",
                rounds=rounds,
            ))

        # 2. Convert to rollouts
        converter = TranscriptConverter(target_agent_type="research")
        sessions = converter.convert_batch(transcripts)
        assert len(sessions) == 5

        # 3. Write via collector
        for session in sessions:
            collector.write_synthetic(session)

        # 4. Load in pipeline
        pipeline = TrainingPipeline(
            rollouts_dir=rollouts_dir,
            batch_size=4,
            min_session_score=0.0,
        )
        synthetic = pipeline.load_rollouts("research", "synthetic")
        assert len(synthetic) == 5

        scored = pipeline.score_rollouts(synthetic)
        batch = pipeline.assemble_batch("research", [], scored)
        assert batch is not None
        assert batch.total == 4
        assert batch.synthetic_count == 4
