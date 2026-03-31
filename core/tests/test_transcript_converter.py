"""Tests for the MiroShark transcript converter."""
import pytest

from oas_core.rl.transcript_converter import (
    TranscriptConverter,
    DebateTranscript,
)


def _make_transcript(n_rounds: int = 3) -> DebateTranscript:
    rounds = []
    for i in range(n_rounds):
        rounds.append({
            "round": i,
            "actions": [
                {
                    "agent_name": "Dr. Smith",
                    "agent_type": "research",
                    "platform": "twitter",
                    "content": f"Round {i}: I argue that the evidence supports the hypothesis.",
                },
                {
                    "agent_name": "Prof. Jones",
                    "agent_type": "methodologist",
                    "platform": "reddit",
                    "content": f"Round {i}: The statistical methodology is flawed because...",
                },
                {
                    "agent_name": "Dr. Lee",
                    "agent_type": "contrarian",
                    "platform": "twitter",
                    "content": f"Round {i}: An alternative explanation is...",
                },
            ],
        })
    return DebateTranscript(
        debate_id="test-debate-001",
        topic="CRISPR off-target effects are under-reported",
        rounds=rounds,
    )


class TestTranscriptConverter:
    def test_convert_basic(self):
        transcript = _make_transcript(3)
        converter = TranscriptConverter(target_agent_type="research")
        session = converter.convert(transcript)

        assert session.session_id == "debate-test-debate-001"
        assert session.agent_type == "research"
        assert session.source == "synthetic"
        assert len(session.turns) >= 3  # system + at least user + assistant

    def test_system_prompt_included(self):
        transcript = _make_transcript(1)
        converter = TranscriptConverter(target_agent_type="research")
        session = converter.convert(transcript)

        system_turns = [t for t in session.turns if t.role == "system"]
        assert len(system_turns) == 1
        assert "CRISPR" in system_turns[0].content

    def test_assistant_turns_from_target_agent(self):
        transcript = _make_transcript(3)
        converter = TranscriptConverter(target_agent_type="research")
        session = converter.convert(transcript)

        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        assert len(assistant_turns) >= 1
        for t in assistant_turns:
            assert "evidence supports" in t.content

    def test_user_turns_from_other_agents(self):
        transcript = _make_transcript(3)
        converter = TranscriptConverter(target_agent_type="research")
        session = converter.convert(transcript)

        user_turns = [t for t in session.turns if t.role == "user"]
        # At least the opening prompt + environment messages
        assert len(user_turns) >= 1

    def test_convert_batch(self):
        transcripts = [_make_transcript(2), _make_transcript(3)]
        converter = TranscriptConverter(target_agent_type="research")
        sessions = converter.convert_batch(transcripts)
        assert len(sessions) == 2

    def test_convert_batch_filters_short(self):
        # Empty transcript with no rounds
        empty = DebateTranscript(
            debate_id="empty", topic="Nothing", rounds=[],
        )
        normal = _make_transcript(3)
        converter = TranscriptConverter(target_agent_type="research")
        sessions = converter.convert_batch([empty, normal])
        assert len(sessions) == 1  # Empty one filtered out

    def test_from_miroshark_json(self):
        data = {
            "simulation_id": "sim-001",
            "topic": "AI safety",
            "rounds": [{"round": 0, "actions": []}],
            "agents": [{"name": "Agent1"}],
        }
        transcript = TranscriptConverter.from_miroshark_json(data)
        assert transcript.debate_id == "sim-001"
        assert transcript.topic == "AI safety"
        assert len(transcript.rounds) == 1
