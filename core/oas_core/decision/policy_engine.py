"""Decision policy engine — evaluates campaign state to recommend next actions.

Replaces naive routing with structured decision-making based on confidence,
cost, risk, and readiness signals. Policies are composable rules that score
candidate actions and pick the best one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from oas_core.schemas.campaign import CampaignSchema, CampaignStepSchema
from oas_core.schemas.intents import KnowledgeArtifact, EvidenceType

__all__ = [
    "DecisionAction",
    "DecisionPolicyEngine",
    "DecisionRecommendation",
    "PolicyRule",
    "PolicyViolation",
    "IdleBudgetRule",
    "OpusGateRule",
    "SonnetBudgetRule",
]

logger = logging.getLogger("oas.decision.policy")


class DecisionAction(str, Enum):
    """Possible next actions for a campaign."""

    STAY_IN_MODULE = "stay_in_module"
    HANDOFF_TO = "handoff_to"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    STOP_INSUFFICIENT_EVIDENCE = "stop_insufficient_evidence"
    RETRY_WITH_REFINEMENT = "retry_with_refinement"
    PROCEED_TO_NEXT_STEP = "proceed_to_next_step"
    # v2 Phase 24 — cloud escalation actions
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    BLOCK_BUDGET_EXHAUSTED = "block_budget_exhausted"


@dataclass
class DecisionRecommendation:
    """Output of the decision policy engine."""

    action: DecisionAction
    target_module: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "target_module": self.target_module,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "alternatives": self.alternatives,
            "metadata": self.metadata,
        }


@dataclass
class PolicyViolation:
    """A policy rule that was violated."""

    rule_name: str
    severity: str  # "block", "warn"
    message: str


class PolicyRule:
    """A composable policy rule that scores a campaign decision.

    Subclass and override ``evaluate`` to implement custom rules.
    Built-in rules cover cost ceiling, confidence floor, max retries,
    and human escalation thresholds.
    """

    def __init__(self, name: str, *, severity: str = "warn"):
        self.name = name
        self.severity = severity

    def evaluate(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> PolicyViolation | None:
        """Evaluate the rule. Return a violation or None if rule passes."""
        return None


class CostCeilingRule(PolicyRule):
    """Blocks if campaign cost exceeds a ceiling."""

    def __init__(self, max_cost_usd: float = 10.0):
        super().__init__("cost_ceiling", severity="block")
        self._max_cost = max_cost_usd

    def evaluate(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> PolicyViolation | None:
        total = 0.0
        if campaign.total_cost:
            total = campaign.total_cost.cost_usd
        for step in campaign.steps:
            if step.cost:
                total += step.cost.cost_usd
        if total > self._max_cost:
            return PolicyViolation(
                rule_name=self.name,
                severity=self.severity,
                message=f"Campaign cost ${total:.2f} exceeds ceiling ${self._max_cost:.2f}",
            )
        return None


class ConfidenceFloorRule(PolicyRule):
    """Warns if average artifact confidence is too low to proceed."""

    def __init__(self, min_confidence: float = 0.4):
        super().__init__("confidence_floor", severity="warn")
        self._min_confidence = min_confidence

    def evaluate(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> PolicyViolation | None:
        if not artifacts:
            return None
        avg = sum(a.confidence for a in artifacts) / len(artifacts)
        if avg < self._min_confidence:
            return PolicyViolation(
                rule_name=self.name,
                severity=self.severity,
                message=f"Average confidence {avg:.2f} below floor {self._min_confidence:.2f}",
            )
        return None


class MaxRetriesRule(PolicyRule):
    """Blocks if a step has been retried too many times."""

    def __init__(self, max_retries: int = 3):
        super().__init__("max_retries", severity="block")
        self._max_retries = max_retries

    def evaluate(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> PolicyViolation | None:
        retry_count = context.get("retry_count", 0)
        if retry_count >= self._max_retries:
            return PolicyViolation(
                rule_name=self.name,
                severity=self.severity,
                message=f"Step retried {retry_count} times (max {self._max_retries})",
            )
        return None


class HumanEscalationRule(PolicyRule):
    """Escalates to human if failure rate or cost is too high."""

    def __init__(
        self,
        failure_rate_threshold: float = 0.5,
        cost_escalation_usd: float = 5.0,
    ):
        super().__init__("human_escalation", severity="warn")
        self._failure_threshold = failure_rate_threshold
        self._cost_escalation = cost_escalation_usd

    def evaluate(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> PolicyViolation | None:
        total_steps = len(campaign.steps)
        if total_steps == 0:
            return None
        failed = len(campaign.failed_steps)
        failure_rate = failed / total_steps
        if failure_rate >= self._failure_threshold:
            return PolicyViolation(
                rule_name=self.name,
                severity=self.severity,
                message=f"Failure rate {failure_rate:.0%} exceeds threshold {self._failure_threshold:.0%}",
            )

        total_cost = sum(
            s.cost.cost_usd for s in campaign.steps if s.cost
        )
        if total_cost >= self._cost_escalation:
            return PolicyViolation(
                rule_name=self.name,
                severity=self.severity,
                message=f"Campaign cost ${total_cost:.2f} approaching escalation threshold",
            )
        return None


class IdleBudgetRule(PolicyRule):
    """Blocks background work when the idle budget cap has been exceeded."""

    def __init__(self, max_idle_spend_ratio: float = 0.2):
        super().__init__("idle_budget", severity="block")
        self._max_ratio = max_idle_spend_ratio

    def evaluate(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> PolicyViolation | None:
        scope = str(context.get("action_scope", "")).strip().lower()
        if scope not in {"idle", "kairos", "background", "proactive"}:
            return None

        ratio = context.get("daily_spend_ratio")
        if ratio is None:
            spent = context.get("daily_spend_usd")
            budget = context.get("daily_budget_usd")
            if budget:
                try:
                    ratio = float(spent or 0.0) / float(budget)
                except (TypeError, ValueError, ZeroDivisionError):
                    ratio = None

        if ratio is None:
            return None

        try:
            ratio_value = float(ratio)
        except (TypeError, ValueError):
            return None

        if ratio_value > self._max_ratio:
            return PolicyViolation(
                rule_name=self.name,
                severity=self.severity,
                message=(
                    f"Idle work blocked: daily spend {ratio_value:.0%} "
                    f"exceeds idle cap {self._max_ratio:.0%}"
                ),
            )
        return None


class OpusGateRule(PolicyRule):
    """Per-call Boss approval for every CLAUDE_OPUS request (§4.1).

    Any request that would use ``CLAUDE_OPUS`` must pass through the OAS
    approval queue. This rule blocks unconditionally — there is no
    timeout-grant, no bypass.

    Disabling this rule itself requires Boss approval plus a 24-hour
    cooldown (enforced by the ``OpusGate.disable()`` admin flow, not by
    this rule object).
    """

    def __init__(self) -> None:
        super().__init__("opus_gate", severity="block")

    def evaluate(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> PolicyViolation | None:
        tier = context.get("requested_tier", "")
        if tier not in ("claude_opus", "CLAUDE_OPUS"):
            return None

        # Check if Boss already approved this specific call
        approved_request_ids: set[str] = set(
            context.get("approved_opus_request_ids", [])
        )
        current_request_id = context.get("request_id", "")
        if current_request_id and current_request_id in approved_request_ids:
            return None

        return PolicyViolation(
            rule_name=self.name,
            severity=self.severity,
            message=(
                "CLAUDE_OPUS requires per-call Boss approval. "
                f"Request '{current_request_id}' must be approved via "
                "OAS approval queue before execution."
            ),
        )


class SonnetBudgetRule(PolicyRule):
    """Per-mission Sonnet spend cap (§4.1).

    Enforces ``plan_file.sonnet_cap_usd`` as a hard ceiling for
    automatic Sonnet escalation. When the cap is reached the mission
    must either degrade to local or request Opus (which requires Boss
    approval via ``OpusGateRule``).

    Budget tracking is cumulative per mission, not per call.
    """

    def __init__(self) -> None:
        super().__init__("sonnet_budget", severity="block")

    def evaluate(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> PolicyViolation | None:
        tier = context.get("requested_tier", "")
        if tier not in ("claude_sonnet", "CLAUDE_SONNET"):
            return None

        cap = context.get("sonnet_cap_usd")
        spent = context.get("sonnet_spent_usd")
        if cap is None or spent is None:
            return None

        try:
            cap_f = float(cap)
            spent_f = float(spent)
        except (TypeError, ValueError):
            return None

        if cap_f <= 0:
            return PolicyViolation(
                rule_name=self.name,
                severity=self.severity,
                message="Sonnet cap is $0 — mission is local-only",
            )

        if spent_f >= cap_f:
            return PolicyViolation(
                rule_name=self.name,
                severity=self.severity,
                message=(
                    f"Sonnet budget exhausted: ${spent_f:.2f} spent "
                    f"of ${cap_f:.2f} cap"
                ),
            )
        return None


# --- Command → module mapping for handoff decisions ---

_COMMAND_MODULE_MAP: dict[str, str] = {
    "research": "academic",
    "literature": "academic",
    "doe": "academic",
    "paper": "academic",
    "perplexity": "academic",
    "simulate": "experiment",
    "analyze": "experiment",
    "synthetic": "experiment",
    "report-data": "experiment",
    "autoresearch": "experiment",
    "parametergolf": "experiment",
    "synthesize": "leader",
    "report": "leader",
    "deerflow": "leader",
    "deepresearch": "leader",
    "swarmresearch": "leader",
    "debate": "leader",
}


class DecisionPolicyEngine:
    """Evaluates campaign state to recommend the next best action.

    Combines composable policy rules with heuristic analysis of campaign
    progress, accumulated evidence, and module health to produce actionable
    recommendations.

    Usage::

        engine = DecisionPolicyEngine()
        rec = engine.recommend(campaign, artifacts, context)
        if rec.action == DecisionAction.ESCALATE_TO_HUMAN:
            await notify_human(rec.reasoning)
    """

    def __init__(
        self,
        rules: list[PolicyRule] | None = None,
    ):
        if rules is not None:
            self._rules = list(rules)
        else:
            self._rules = [
                CostCeilingRule(),
                ConfidenceFloorRule(),
                MaxRetriesRule(),
                HumanEscalationRule(),
            ]

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._rules)

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.append(rule)

    def evaluate_policies(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> list[PolicyViolation]:
        """Run all policy rules and collect violations."""
        violations = []
        for rule in self._rules:
            v = rule.evaluate(campaign, artifacts, context)
            if v is not None:
                violations.append(v)
        return violations

    def recommend(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any] | None = None,
    ) -> DecisionRecommendation:
        """Produce a decision recommendation based on campaign state.

        Args:
            campaign: Current campaign state.
            artifacts: Knowledge artifacts accumulated so far.
            context: Additional context (retry_count, module_health, etc.).

        Returns:
            DecisionRecommendation with the recommended action.
        """
        ctx = context or {}
        violations = self.evaluate_policies(campaign, artifacts, ctx)

        # Check for blocking violations first
        blockers = [v for v in violations if v.severity == "block"]
        warnings = [v for v in violations if v.severity == "warn"]

        # Blocking: cost ceiling or max retries exceeded
        if blockers:
            # If max retries exceeded, escalate to human
            retry_block = any(v.rule_name == "max_retries" for v in blockers)
            cost_block = any(v.rule_name == "cost_ceiling" for v in blockers)

            if cost_block:
                return DecisionRecommendation(
                    action=DecisionAction.ESCALATE_TO_HUMAN,
                    confidence=0.95,
                    reasoning="; ".join(v.message for v in blockers),
                    metadata={"violations": [v.message for v in blockers]},
                )
            if retry_block:
                return DecisionRecommendation(
                    action=DecisionAction.STOP_INSUFFICIENT_EVIDENCE,
                    confidence=0.9,
                    reasoning="; ".join(v.message for v in blockers),
                    metadata={"violations": [v.message for v in blockers]},
                )

        # Warning: human escalation threshold
        escalation_warnings = [v for v in warnings if v.rule_name == "human_escalation"]
        if escalation_warnings:
            return DecisionRecommendation(
                action=DecisionAction.ESCALATE_TO_HUMAN,
                confidence=0.8,
                reasoning=escalation_warnings[0].message,
                metadata={"violations": [v.message for v in warnings]},
            )

        # Low confidence: suggest refinement or more research
        confidence_warnings = [v for v in warnings if v.rule_name == "confidence_floor"]
        if confidence_warnings:
            return DecisionRecommendation(
                action=DecisionAction.RETRY_WITH_REFINEMENT,
                confidence=0.7,
                reasoning=confidence_warnings[0].message,
                metadata={"violations": [v.message for v in warnings]},
            )

        # No violations — determine next step based on campaign progress
        return self._recommend_next_step(campaign, artifacts, ctx)

    def _recommend_next_step(
        self,
        campaign: CampaignSchema,
        artifacts: list[KnowledgeArtifact],
        context: dict[str, Any],
    ) -> DecisionRecommendation:
        """Recommend next step when no policy violations exist."""
        pending = [s for s in campaign.steps if s.status == "pending"]
        completed = campaign.completed_steps

        # All steps done — campaign complete
        if not pending:
            return DecisionRecommendation(
                action=DecisionAction.PROCEED_TO_NEXT_STEP,
                confidence=0.95,
                reasoning="All campaign steps completed",
                metadata={"completed_steps": len(completed)},
            )

        next_step = pending[0]
        target_module = _COMMAND_MODULE_MAP.get(next_step.command, "leader")

        # Assess evidence quality for handoff decisions
        avg_confidence = (
            sum(a.confidence for a in artifacts) / len(artifacts)
            if artifacts
            else 0.0
        )

        # If confidence is high and next step is in a different module, handoff
        current_module = context.get("current_module", "leader")
        if target_module != current_module:
            return DecisionRecommendation(
                action=DecisionAction.HANDOFF_TO,
                target_module=target_module,
                confidence=min(0.95, avg_confidence + 0.3),
                reasoning=f"Next step '/{next_step.command}' requires {target_module} module",
                alternatives=[
                    {
                        "action": DecisionAction.STAY_IN_MODULE.value,
                        "confidence": 0.3,
                        "reason": "Could attempt locally but suboptimal",
                    }
                ],
                metadata={
                    "next_command": next_step.command,
                    "evidence_confidence": round(avg_confidence, 3),
                },
            )

        # Same module — proceed
        return DecisionRecommendation(
            action=DecisionAction.PROCEED_TO_NEXT_STEP,
            target_module=target_module,
            confidence=min(0.95, avg_confidence + 0.4),
            reasoning=f"Continue with step {next_step.step}: /{next_step.command}",
            metadata={
                "next_command": next_step.command,
                "step_number": next_step.step,
                "evidence_confidence": round(avg_confidence, 3),
            },
        )
