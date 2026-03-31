"""OAS decision engine — campaign intelligence and uncertainty-aware routing.

Upgrades OAS from a reactive router to a proactive decision engine that
evaluates (confidence, cost, risk, readiness) to choose the next campaign
action. Integrates with the module registry for capability-aware decisions
and emits DRVP events for full observability.
"""

from oas_core.decision.policy_engine import (
    DecisionAction,
    DecisionPolicyEngine,
    DecisionRecommendation,
    PolicyRule,
)
from oas_core.decision.readiness import (
    ReadinessDimension,
    ReadinessScore,
    ReadinessScorer,
)
from oas_core.decision.reflection import (
    ReflectionResult,
    CampaignReflector,
)
from oas_core.decision.uncertainty_router import (
    UncertaintyRouter,
    RoutingDecision,
)

__all__ = [
    "DecisionAction",
    "DecisionPolicyEngine",
    "DecisionRecommendation",
    "PolicyRule",
    "ReadinessDimension",
    "ReadinessScore",
    "ReadinessScorer",
    "ReflectionResult",
    "CampaignReflector",
    "UncertaintyRouter",
    "RoutingDecision",
]
