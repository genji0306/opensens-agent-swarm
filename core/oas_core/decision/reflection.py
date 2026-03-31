"""Campaign reflection layer — post-step analysis for decision feedback.

After each campaign step completes, the reflector compares the step output
against the original intent, scores what was learned, and feeds insights
back into the decision engine and knowledge base.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from oas_core.schemas.campaign import CampaignSchema, CampaignStepSchema
from oas_core.schemas.intents import KnowledgeArtifact, EvidenceType
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

__all__ = [
    "ReflectionResult",
    "CampaignReflector",
]

logger = logging.getLogger("oas.decision.reflection")


@dataclass
class ReflectionResult:
    """Result of reflecting on a completed campaign step."""

    step_number: int
    command: str
    learned: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    intent_alignment: float = 0.0  # 0-1: how well output matches intent
    evidence_gain: float = 0.0  # 0-1: how much new evidence was produced
    recommendation: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "command": self.command,
            "learned": self.learned,
            "unknowns": self.unknowns,
            "changed": self.changed,
            "intent_alignment": round(self.intent_alignment, 3),
            "evidence_gain": round(self.evidence_gain, 3),
            "recommendation": self.recommendation,
            "timestamp": self.timestamp.isoformat(),
        }

    @property
    def overall_score(self) -> float:
        return (self.intent_alignment + self.evidence_gain) / 2


class CampaignReflector:
    """Analyzes completed steps to inform decision-making.

    Usage::

        reflector = CampaignReflector()
        result = await reflector.reflect_on_step(
            campaign=campaign,
            step=completed_step,
            objective="Research quantum dot electrodes",
        )
        # Feed result into knowledge base and decision engine
    """

    def __init__(
        self,
        knowledge_store: Any | None = None,
    ):
        self._knowledge_store = knowledge_store

    async def reflect_on_step(
        self,
        campaign: CampaignSchema,
        step: CampaignStepSchema,
        objective: str = "",
        request_id: str = "",
        agent_name: str = "leader",
        device: str = "leader",
    ) -> ReflectionResult:
        """Reflect on a completed step and produce insights."""
        output = step.result or {}
        obj = objective or campaign.objective

        learned = self._extract_learnings(step.command, output)
        unknowns = self._identify_unknowns(step.command, output, obj)
        changed = self._detect_changes(step, campaign)
        intent_alignment = self._score_alignment(step.command, output, obj)
        evidence_gain = self._score_evidence(output)

        # Determine recommendation
        if intent_alignment >= 0.7 and evidence_gain >= 0.5:
            rec = "proceed_to_next_step"
        elif evidence_gain < 0.3:
            rec = "retry_with_refinement"
        elif intent_alignment < 0.4:
            rec = "adjust_objective"
        else:
            rec = "continue_gathering"

        result = ReflectionResult(
            step_number=step.step,
            command=step.command,
            learned=learned,
            unknowns=unknowns,
            changed=changed,
            intent_alignment=intent_alignment,
            evidence_gain=evidence_gain,
            recommendation=rec,
        )

        # Store reflection as a knowledge entry if store available
        if self._knowledge_store and learned:
            try:
                self._knowledge_store.store_lesson(
                    strategy=f"/{step.command} {step.args[:80]}",
                    outcome=rec,
                    insight="; ".join(learned[:3]),
                    topic=obj[:120],
                )
            except Exception as e:
                logger.warning("reflection_store_failed", extra={"error": str(e)})

        # Emit DRVP event
        rid = request_id or campaign.request_id
        if rid:
            await emit(DRVPEvent(
                event_type=DRVPEventType.CAMPAIGN_STEP_COMPLETED,
                request_id=rid,
                agent_name=agent_name,
                device=device,
                payload={
                    "reflection": True,
                    "step_number": step.step,
                    "command": step.command,
                    "intent_alignment": round(intent_alignment, 3),
                    "evidence_gain": round(evidence_gain, 3),
                    "recommendation": rec,
                    "learned_count": len(learned),
                    "unknown_count": len(unknowns),
                },
            ))

        logger.info(
            "step_reflected",
            extra={
                "step": step.step,
                "command": step.command,
                "alignment": round(intent_alignment, 3),
                "gain": round(evidence_gain, 3),
                "rec": rec,
            },
        )

        return result

    async def reflect_on_campaign(
        self,
        campaign: CampaignSchema,
        objective: str = "",
        request_id: str = "",
        agent_name: str = "leader",
        device: str = "leader",
    ) -> list[ReflectionResult]:
        """Reflect on all completed steps in a campaign."""
        results = []
        for step in campaign.completed_steps:
            r = await self.reflect_on_step(
                campaign=campaign,
                step=step,
                objective=objective,
                request_id=request_id,
                agent_name=agent_name,
                device=device,
            )
            results.append(r)
        return results

    def _extract_learnings(self, command: str, output: dict[str, Any]) -> list[str]:
        """Extract what was learned from the step output."""
        learned = []

        # Look for findings, conclusions, results
        for key in ("findings", "conclusions", "summary", "synthesis", "answer"):
            val = output.get(key)
            if isinstance(val, str) and len(val) > 20:
                learned.append(f"[{key}] {val[:150]}")
            elif isinstance(val, list):
                for item in val[:3]:
                    s = str(item)[:120]
                    if len(s) > 10:
                        learned.append(f"[{key}] {s}")

        # Sources discovered
        sources = output.get("sources", output.get("references", []))
        if isinstance(sources, list) and sources:
            learned.append(f"Found {len(sources)} sources")

        return learned

    def _identify_unknowns(
        self, command: str, output: dict[str, Any], objective: str
    ) -> list[str]:
        """Identify what remains unknown after the step."""
        unknowns = []

        # Check for gaps indicators
        if output.get("error"):
            unknowns.append(f"Step error: {str(output['error'])[:100]}")

        # Missing expected fields
        expected = _expected_keys(command)
        for key in expected:
            if key not in output:
                unknowns.append(f"Missing expected: {key}")

        # Low confidence indicators
        confidence = output.get("confidence", output.get("score"))
        if isinstance(confidence, (int, float)) and confidence < 0.5:
            unknowns.append(f"Low confidence: {confidence:.2f}")

        # Short or empty results
        text = _extract_text(output)
        if len(text) < 50:
            unknowns.append("Output too brief for comprehensive analysis")

        return unknowns

    def _detect_changes(
        self, step: CampaignStepSchema, campaign: CampaignSchema
    ) -> list[str]:
        """Detect what changed from prior state."""
        changes = []

        if step.cost and step.cost.cost_usd > 0:
            changes.append(f"Cost: ${step.cost.cost_usd:.3f}")

        if step.duration_seconds:
            changes.append(f"Duration: {step.duration_seconds:.1f}s")

        if step.result:
            sources = step.result.get("sources", step.result.get("references", []))
            if isinstance(sources, list):
                changes.append(f"Sources added: {len(sources)}")

        return changes

    def _score_alignment(
        self, command: str, output: dict[str, Any], objective: str
    ) -> float:
        """Score how well the output aligns with the campaign objective."""
        if not output:
            return 0.0

        score = 0.0

        # Has substantive content
        text = _extract_text(output)
        if len(text) > 100:
            score += 0.3
        elif len(text) > 30:
            score += 0.15

        # Has expected structure
        expected = _expected_keys(command)
        if expected:
            present = sum(1 for k in expected if k in output)
            score += 0.3 * (present / len(expected))
        else:
            score += 0.3 if output else 0.0

        # No errors
        if not output.get("error") and output.get("status") != "error":
            score += 0.2

        # Keyword overlap with objective
        if objective and text:
            obj_words = set(objective.lower().split())
            text_words = set(text.lower().split()[:200])
            if obj_words:
                overlap = len(obj_words & text_words) / len(obj_words)
                score += 0.2 * min(1.0, overlap * 2)

        return min(1.0, score)

    def _score_evidence(self, output: dict[str, Any]) -> float:
        """Score how much new evidence was produced."""
        if not output:
            return 0.0

        score = 0.0

        # Has sources/references
        sources = output.get("sources", output.get("references", []))
        if isinstance(sources, list) and sources:
            score += min(0.4, len(sources) * 0.1)

        # Has findings/results
        text = _extract_text(output)
        if len(text) > 200:
            score += 0.3
        elif len(text) > 50:
            score += 0.15

        # Has structured data
        for key in ("metrics", "parameters", "data", "design", "factors"):
            if key in output:
                score += 0.1
                break

        # Confidence reported
        conf = output.get("confidence", output.get("score"))
        if isinstance(conf, (int, float)):
            score += 0.2 * conf

        return min(1.0, score)


def _extract_text(output: dict[str, Any]) -> str:
    """Extract readable text from output."""
    for key in ("text", "content", "raw", "findings", "summary", "result", "answer"):
        val = output.get(key)
        if isinstance(val, str):
            return val
        if isinstance(val, list):
            return " ".join(str(v) for v in val)
    return str(output)


def _expected_keys(command: str) -> list[str]:
    """Expected output keys per command type."""
    mapping: dict[str, list[str]] = {
        "research": ["findings", "sources"],
        "literature": ["papers", "summary"],
        "doe": ["design", "factors"],
        "simulate": ["results", "parameters"],
        "analyze": ["analysis", "metrics"],
        "synthetic": ["data", "schema"],
        "synthesize": ["synthesis", "conclusions"],
        "report": ["report", "sections"],
        "perplexity": ["answer", "sources"],
        "deepresearch": ["findings", "sources"],
        "deerflow": ["findings", "sources"],
    }
    return mapping.get(command, [])
