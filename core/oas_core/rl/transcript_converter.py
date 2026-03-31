"""Convert MiroShark debate transcripts to OpenClaw-RL rollout format.

MiroShark produces multi-agent debate transcripts with per-agent actions
and belief states. This module converts them into single-agent-with-environment
format suitable for OpenClaw-RL training.

Mapping:
  - The OAS agent being trained plays "assistant"
  - All other debate agents (combined) play "user/environment"
  - Belief state changes serve as next-state signals for PRM scoring
"""
from __future__ import annotations

import logging
from typing import Any

from oas_core.rl import RolloutSession, RolloutTurn

__all__ = ["TranscriptConverter", "DebateTranscript"]

logger = logging.getLogger("oas.rl.transcript_converter")


class DebateAction(dict):
    """A single agent action in a debate round (dict subclass for flexibility)."""
    pass


class DebateTranscript:
    """Parsed MiroShark debate transcript.

    Attributes:
        debate_id: Unique identifier for this debate session.
        topic: The debate topic/hypothesis.
        rounds: List of round data, each containing agent actions.
        agents: Agent metadata (name, persona, platform).
        belief_states: Per-agent belief tracking over rounds.
    """

    def __init__(
        self,
        debate_id: str,
        topic: str,
        rounds: list[dict[str, Any]],
        agents: list[dict[str, Any]] | None = None,
        belief_states: list[dict[str, Any]] | None = None,
    ):
        self.debate_id = debate_id
        self.topic = topic
        self.rounds = rounds
        self.agents = agents or []
        self.belief_states = belief_states or []


class TranscriptConverter:
    """Converts MiroShark debate transcripts to OpenClaw-RL rollout format."""

    def __init__(self, target_agent_type: str = "research"):
        self.target_agent_type = target_agent_type

    def convert(self, transcript: DebateTranscript) -> RolloutSession:
        """Convert a debate transcript into a single rollout session.

        The target agent's contributions become "assistant" turns,
        and all other agents' contributions become "user" turns
        (representing the environment/opponents).
        """
        session = RolloutSession(
            session_id=f"debate-{transcript.debate_id}",
            agent_type=self.target_agent_type,
            source="synthetic",
        )

        # System prompt establishing the debate context
        session.add_turn(
            "system",
            f"You are participating in a structured scientific debate on: {transcript.topic}. "
            f"Evaluate claims critically, defend your positions with evidence, and adjust "
            f"your stance when presented with compelling counter-arguments.",
            turn_type="side",
        )

        # Opening challenge
        session.add_turn(
            "user",
            f"Debate topic: {transcript.topic}\n\nPresent your initial analysis.",
            turn_type="main",
        )

        for round_data in transcript.rounds:
            round_num = round_data.get("round", 0)
            actions = round_data.get("actions", [])

            # Separate target agent responses from environment
            env_messages: list[str] = []
            target_response: str | None = None

            for action in actions:
                agent_name = action.get("agent_name", "")
                content = action.get("content", "")
                if not content:
                    continue

                # Simple heuristic: first agent matching target type is "assistant"
                # All others are "user/environment"
                agent_type = action.get("agent_type", "").lower()
                if agent_type == self.target_agent_type and target_response is None:
                    target_response = content
                else:
                    platform = action.get("platform", "twitter")
                    env_messages.append(
                        f"[{agent_name} on {platform}] {content}"
                    )

            # Add environment responses as a combined "user" turn
            if env_messages and round_num > 0:
                session.add_turn(
                    "user",
                    "\n\n".join(env_messages),
                    turn_type="main",
                )

            # Add target agent response
            if target_response:
                session.add_turn(
                    "assistant",
                    target_response,
                    turn_type="main",
                )

        session.finalize()
        return session

    def convert_batch(
        self, transcripts: list[DebateTranscript]
    ) -> list[RolloutSession]:
        """Convert multiple debate transcripts to rollout sessions."""
        sessions = []
        for transcript in transcripts:
            try:
                session = self.convert(transcript)
                if len(session.turns) >= 3:  # At least system + user + assistant
                    sessions.append(session)
            except Exception as exc:
                logger.warning(
                    "transcript_convert_error",
                    debate_id=transcript.debate_id,
                    error=str(exc),
                )
        return sessions

    @staticmethod
    def from_miroshark_json(data: dict[str, Any]) -> DebateTranscript:
        """Parse a MiroShark simulation result JSON into a DebateTranscript."""
        return DebateTranscript(
            debate_id=data.get("simulation_id", data.get("id", "unknown")),
            topic=data.get("topic", data.get("config", {}).get("topic", "")),
            rounds=data.get("rounds", []),
            agents=data.get("agents", []),
            belief_states=data.get("belief_states", []),
        )
