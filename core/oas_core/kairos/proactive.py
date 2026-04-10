"""ProactiveSuggester — gap detection and follow-up research queueing.

Scans the knowledge base for gaps (topics with few sources, low
confidence, or missing coverage dimensions) and generates follow-up
research suggestions. These are queued for execution during idle
periods.

Also identifies high-quality RL training traces from recent rollouts
for curation into the RL training pipeline.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["ProactiveSuggester", "Suggestion"]

logger = logging.getLogger("oas.kairos.proactive")


@dataclass(frozen=True)
class Suggestion:
    """A proactive follow-up suggestion."""

    kind: str  # "research_gap", "low_confidence", "rl_curation"
    topic: str
    rationale: str
    priority: int = 2  # 1..5
    suggested_command: str = "research"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "topic": self.topic,
            "rationale": self.rationale,
            "priority": self.priority,
            "suggested_command": self.suggested_command,
            "metadata": self.metadata,
        }


class ProactiveSuggester:
    """Scans KB for gaps and generates actionable suggestions."""

    def __init__(
        self,
        *,
        kb_dir: str | Path,
        min_sources: int = 3,
        min_confidence: float = 0.5,
        rollout_dir: str | Path | None = None,
        rl_quality_threshold: float = 0.7,
    ) -> None:
        self._kb_dir = Path(kb_dir).expanduser().resolve()
        self._min_sources = min_sources
        self._min_confidence = min_confidence
        self._rollout_dir = Path(rollout_dir) if rollout_dir else None
        self._rl_threshold = rl_quality_threshold

    def scan(self) -> list[Suggestion]:
        """Run gap detection and return prioritized suggestions."""
        suggestions: list[Suggestion] = []
        suggestions.extend(self._find_research_gaps())
        suggestions.extend(self._find_low_confidence())
        suggestions.extend(self._find_rl_candidates())
        # Sort by priority descending
        return sorted(suggestions, key=lambda s: -s.priority)

    def _find_research_gaps(self) -> list[Suggestion]:
        """Detect topics with insufficient source coverage."""
        kb_path = self._kb_dir / "knowledge.jsonl"
        if not kb_path.exists():
            return []

        topic_sources: dict[str, int] = {}
        for entry in self._load_jsonl(kb_path):
            topic = entry.get("topic", entry.get("query", ""))
            if topic:
                topic_sources[topic] = topic_sources.get(topic, 0) + 1

        suggestions: list[Suggestion] = []
        for topic, count in topic_sources.items():
            if count < self._min_sources:
                suggestions.append(Suggestion(
                    kind="research_gap",
                    topic=topic,
                    rationale=f"Only {count} source(s), need ≥{self._min_sources}",
                    priority=3,
                    suggested_command="deepresearch",
                    metadata={"current_sources": count},
                ))
        return suggestions

    def _find_low_confidence(self) -> list[Suggestion]:
        """Detect topics where average confidence is below threshold."""
        kb_path = self._kb_dir / "knowledge.jsonl"
        if not kb_path.exists():
            return []

        topic_scores: dict[str, list[float]] = {}
        for entry in self._load_jsonl(kb_path):
            topic = entry.get("topic", entry.get("query", ""))
            confidence = entry.get("confidence")
            if topic and confidence is not None:
                try:
                    topic_scores.setdefault(topic, []).append(float(confidence))
                except (TypeError, ValueError):
                    pass

        suggestions: list[Suggestion] = []
        for topic, scores in topic_scores.items():
            avg = sum(scores) / len(scores) if scores else 0.0
            if avg < self._min_confidence:
                suggestions.append(Suggestion(
                    kind="low_confidence",
                    topic=topic,
                    rationale=f"Average confidence {avg:.2f} < {self._min_confidence}",
                    priority=2,
                    suggested_command="research",
                    metadata={"avg_confidence": round(avg, 3), "sample_count": len(scores)},
                ))
        return suggestions

    def _find_rl_candidates(self) -> list[Suggestion]:
        """Identify high-quality rollouts for RL training curation."""
        if self._rollout_dir is None or not self._rollout_dir.exists():
            return []

        suggestions: list[Suggestion] = []
        for path in sorted(self._rollout_dir.glob("*.jsonl"))[:50]:
            for entry in self._load_jsonl(path):
                score = entry.get("quality_score", entry.get("reward"))
                if score is not None:
                    try:
                        if float(score) >= self._rl_threshold:
                            suggestions.append(Suggestion(
                                kind="rl_curation",
                                topic=entry.get("task_type", "unknown"),
                                rationale=f"Quality score {float(score):.2f} ≥ threshold",
                                priority=1,
                                suggested_command="rl-train",
                                metadata={
                                    "rollout_file": path.name,
                                    "score": float(score),
                                },
                            ))
                    except (TypeError, ValueError):
                        pass
        return suggestions

    @staticmethod
    def _load_jsonl(path: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except FileNotFoundError:
            pass
        return entries
