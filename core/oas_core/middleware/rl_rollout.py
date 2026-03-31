"""Rollout collection middleware for the OAS pipeline.

Intercepts agent conversations and formats them as OpenClaw-RL-compatible
rollout sessions. Writes completed sessions to JSONL files for later
scoring and training.

This middleware is transparent — it does not modify the request or response,
only observes and records.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oas_core.rl import RolloutSession

__all__ = ["RolloutCollector"]

logger = logging.getLogger("oas.middleware.rl_rollout")


class RolloutCollector:
    """Middleware that captures agent conversations as training rollouts.

    Usage::

        collector = RolloutCollector(rollouts_dir=Path("~/.darklab/rl/rollouts"))

        # In the pipeline:
        session = collector.start_session("research", task_id, system_prompt)
        session.add_turn("user", user_message)
        result = await handler(payload)
        session.add_turn("assistant", result.get("text", ""))
        collector.finalize_session(session)
    """

    def __init__(self, rollouts_dir: Path, *, enabled: bool = True):
        self.rollouts_dir = rollouts_dir
        self.enabled = enabled
        self._active_sessions: dict[str, RolloutSession] = {}

    def start_session(
        self,
        agent_type: str,
        request_id: str,
        system_prompt: str = "",
    ) -> RolloutSession:
        """Start a new rollout session for a conversation."""
        session = RolloutSession(
            session_id=request_id,
            agent_type=agent_type,
            source="live",
        )

        if system_prompt:
            session.add_turn("system", system_prompt, turn_type="side")

        self._active_sessions[request_id] = session
        return session

    def get_session(self, request_id: str) -> RolloutSession | None:
        """Get an active session by request ID."""
        return self._active_sessions.get(request_id)

    def finalize_session(self, session: RolloutSession) -> Path | None:
        """Finalize a session and write it to disk as JSONL.

        Returns the path to the written file, or None if collection is disabled
        or the session has insufficient data.
        """
        if not self.enabled:
            return None

        session.finalize()

        # Remove from active sessions
        self._active_sessions.pop(session.session_id, None)

        # Only persist sessions with at least one assistant turn
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        if not assistant_turns:
            return None

        # Write to JSONL file
        source_dir = self.rollouts_dir / session.source
        source_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        file_path = source_dir / f"{date_str}.jsonl"

        try:
            with open(file_path, "a") as f:
                f.write(session.model_dump_json() + "\n")
            logger.debug(
                "rollout_collected",
                session_id=session.session_id,
                agent_type=session.agent_type,
                turns=len(session.turns),
            )
            return file_path
        except Exception as exc:
            logger.warning("rollout_write_failed", error=str(exc))
            return None

    def write_synthetic(self, session: RolloutSession) -> Path | None:
        """Write a synthetic (debate) rollout session to disk."""
        session.source = "synthetic"
        return self.finalize_session(session)

    @property
    def active_session_count(self) -> int:
        return len(self._active_sessions)

    @property
    def stats(self) -> dict[str, Any]:
        """Return collector statistics."""
        live_dir = self.rollouts_dir / "live"
        synthetic_dir = self.rollouts_dir / "synthetic"

        live_count = len(list(live_dir.glob("*.jsonl"))) if live_dir.exists() else 0
        synthetic_count = len(list(synthetic_dir.glob("*.jsonl"))) if synthetic_dir.exists() else 0

        return {
            "enabled": self.enabled,
            "active_sessions": self.active_session_count,
            "live_files": live_count,
            "synthetic_files": synthetic_count,
        }
