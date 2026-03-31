"""Tiered Model Router — multi-model strategy with specialist routing.

Protocol:
  Tier 1 (PLANNING)    — Anthropic Claude via LiteLLM (expensive, high quality)
                          Used for: campaign planning, CLAUDE.md, plan.md, architecture
  Tier 2 (EXECUTION)   — Qwen3:8b via Ollama/LiteLLM (free, local)
                          General: research, synthesis, media, etc.
                          Coding specialist: qwen2.5-coder:7b for SIMULATE/ANALYZE/SYNTHETIC
                          Reasoning specialist: glm4:9b for DOE/DEEP_RESEARCH/DEBATE
  Tier 3 (BOOST)       — Claude/Gemini via AIClient-2-API (free client accounts)
                          Used for: quality-sensitive execution when boost is enabled
  Tier 4 (RL_EVOLVED)  — Qwen3:8b + LoRA via OpenClaw-RL proxy
                          TurboQuant 4-bit KV: ~12k tokens/agent with 10 active
  AUTO-FALLBACK        — PLANNING → BOOST (if enabled) → EXECUTION

The router classifies each LLM call by inspecting the prompt/system message for
planning indicators, then selects the appropriate model tier. Credit exhaustion
is detected from API errors and triggers automatic tier demotion.
"""
from __future__ import annotations

import logging
import re
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ModelTier",
    "ModelRouter",
    "TierConfig",
    "RoutingDecision",
    "BOOST_ELIGIBLE_TASKS",
    "CODING_TASKS",
    "REASONING_TASKS",
]

logger = logging.getLogger("oas.model_router")

# ── Planning detection patterns ──────────────────────────────────────────────

_PLANNING_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bplan\s*(\.md|ning|_campaign)\b", re.IGNORECASE),
    re.compile(r"\bclaude\.md\b", re.IGNORECASE),
    re.compile(r"\bdecompos(e|ition)\b", re.IGNORECASE),
    re.compile(r"\barchitect(ure)?\b", re.IGNORECASE),
    re.compile(r"\bstrateg(y|ic|ize)\b", re.IGNORECASE),
    re.compile(r"\bdesign\s+(of\s+experiments?|system|approach)\b", re.IGNORECASE),
    re.compile(r"\broadmap\b", re.IGNORECASE),
    re.compile(r"\bcampaign\s+planner\b", re.IGNORECASE),
    re.compile(r"\bDecompose\s+into\s+steps\b", re.IGNORECASE),
]

_PLANNING_SYSTEM_HINTS: list[str] = [
    "campaign planner",
    "decompose",
    "plan.md",
    "claude.md",
    "design of experiments",
    "research plan",
    "implementation plan",
]

# Task types eligible for boost tier (quality-sensitive execution tasks)
BOOST_ELIGIBLE_TASKS: set[str] = {
    "RESEARCH",
    "LITERATURE",
    "PAPER",
    "DOE",
    "SYNTHESIZE",
    "AUTORESEARCH",
    "DEERFLOW",
    "DEEP_RESEARCH",
    "SWARM_RESEARCH",
    "FULL_SWARM",
}

# Task types routed to the specialist coding model (qwen2.5-coder)
CODING_TASKS: set[str] = {
    "SIMULATE",
    "ANALYZE",
    "SYNTHETIC",
    "PARAMETER_GOLF",
}

# Task types routed to the specialist reasoning model (glm4)
REASONING_TASKS: set[str] = {
    "DOE",
    "DEEP_RESEARCH",
    "SWARM_RESEARCH",
    "DEBATE",
}


class ModelTier(str, Enum):
    """Which quality tier a request should use."""
    PLANNING = "planning"
    EXECUTION = "execution"
    BOOST = "boost"
    RL_EVOLVED = "rl_evolved"


@dataclass
class TierConfig:
    """Model configuration for each tier."""
    planning_model: str = "claude-sonnet-4-6"
    planning_max_tokens: int = 8192
    execution_model: str = "qwen3:8b"
    execution_max_tokens: int = 8192
    # Specialist models for task-specific routing
    coding_model: str = "qwen2.5-coder:7b"
    coding_max_tokens: int = 8192
    reasoning_model: str = "glm4:9b"
    reasoning_max_tokens: int = 8192
    # Boost tier — AIClient-2-API (free client accounts)
    boost_model: str = "gemini-2.5-flash"
    boost_max_tokens: int = 8192
    boost_enabled: bool = False
    boost_daily_limit: int = 100
    # RL-evolved tier — OpenClaw-RL trained LoRA adapters via proxy
    # TurboQuant 4-bit KV compression: ~12k tokens/agent with 10 active agents
    rl_proxy_url: str = ""  # e.g. "http://localhost:30000/v1"
    rl_model: str = "qwen3:8b"
    rl_max_tokens: int = 12288  # TurboQuant extended context
    rl_enabled: bool = False
    rl_enabled_agents: set[str] = field(default_factory=set)
    rl_min_promotion_score: float = 0.7
    # Anthropic credit exhaustion triggers auto-fallback
    credits_exhausted: bool = False
    credits_exhausted_at: float = 0.0
    # Retry Anthropic after this many seconds (1 hour)
    credit_retry_interval: float = 3600.0


@dataclass
class RoutingDecision:
    """Result of the router's classification."""
    tier: ModelTier
    model: str
    max_tokens: int
    reason: str
    forced_fallback: bool = False


class ModelRouter:
    """Routes LLM calls to the appropriate model tier.

    Usage::

        router = ModelRouter()
        decision = router.route(prompt, system)
        # decision.model → "claude-sonnet-4-6" or "llama3.1" or "gemini-2.5-flash"
        # decision.tier  → PLANNING or EXECUTION or BOOST

        # After an API credit error:
        router.mark_credits_exhausted()
        # Now planning calls route to BOOST (if enabled) or EXECUTION

        # Enable boost for quality-sensitive tasks:
        router.config.boost_enabled = True
    """

    def __init__(self, config: TierConfig | None = None):
        self.config = config or TierConfig()
        self._call_counts: dict[str, int] = {
            "planning": 0, "execution": 0, "boost": 0, "rl_evolved": 0,
        }
        self._boost_today_count: int = 0
        self._boost_today_date: str = ""

    def classify(self, prompt: str, system: str = "") -> ModelTier:
        """Classify a request as PLANNING or EXECUTION based on content."""
        combined = f"{system}\n{prompt}"

        # Check system message hints first (strongest signal)
        system_lower = system.lower()
        for hint in _PLANNING_SYSTEM_HINTS:
            if hint in system_lower:
                return ModelTier.PLANNING

        # Check prompt patterns
        for pattern in _PLANNING_PATTERNS:
            if pattern.search(combined):
                return ModelTier.PLANNING

        return ModelTier.EXECUTION

    def _check_boost_daily_limit(self) -> bool:
        """Check if boost daily limit allows another call."""
        today = time.strftime("%Y-%m-%d")
        if self._boost_today_date != today:
            self._boost_today_date = today
            self._boost_today_count = 0
        return self._boost_today_count < self.config.boost_daily_limit

    def _record_boost_call(self) -> None:
        """Record a boost call against the daily limit."""
        today = time.strftime("%Y-%m-%d")
        if self._boost_today_date != today:
            self._boost_today_date = today
            self._boost_today_count = 0
        self._boost_today_count += 1

    def is_rl_available(self, agent_name: str | None = None) -> bool:
        """Check if RL-evolved model is available for the given agent."""
        cfg = self.config
        if not cfg.rl_enabled or not cfg.rl_proxy_url:
            return False
        if agent_name and cfg.rl_enabled_agents:
            return agent_name.lower() in {a.lower() for a in cfg.rl_enabled_agents}
        # If rl_enabled_agents is empty and rl_enabled is True, RL is disabled
        # (empty set means no agents opted in yet)
        return bool(cfg.rl_enabled_agents)

    def route(
        self,
        prompt: str,
        system: str = "",
        *,
        force_tier: ModelTier | None = None,
        task_type: str | None = None,
        agent_name: str | None = None,
    ) -> RoutingDecision:
        """Determine which model to use for this request.

        Args:
            prompt: The user prompt text.
            system: The system message (if any).
            force_tier: Override automatic classification.
            task_type: DarkLab TaskType (e.g. "RESEARCH") for boost eligibility.
            agent_name: Agent name for RL-evolved routing.

        Returns:
            RoutingDecision with model name, tier, and reasoning.
        """
        cfg = self.config

        # Check if credits are exhausted but retry interval has passed
        if cfg.credits_exhausted and cfg.credits_exhausted_at > 0:
            elapsed = time.time() - cfg.credits_exhausted_at
            if elapsed >= cfg.credit_retry_interval:
                logger.info(
                    "Retrying Anthropic after cooldown (elapsed=%ds)", round(elapsed),
                )
                cfg.credits_exhausted = False
                cfg.credits_exhausted_at = 0.0

        # Handle forced tiers
        if force_tier == ModelTier.BOOST:
            return self._route_boost("Forced boost tier")
        if force_tier == ModelTier.RL_EVOLVED:
            return self._route_rl(agent_name, "Forced RL_EVOLVED tier")

        tier = force_tier or self.classify(prompt, system)

        # If credits exhausted, try BOOST before falling back to EXECUTION
        if cfg.credits_exhausted and tier == ModelTier.PLANNING:
            if cfg.boost_enabled and self._check_boost_daily_limit():
                return self._route_boost(
                    "Credits exhausted — boost fallback for planning task"
                )
            self._call_counts["execution"] = self._call_counts.get("execution", 0) + 1
            return RoutingDecision(
                tier=ModelTier.EXECUTION,
                model=cfg.execution_model,
                max_tokens=cfg.execution_max_tokens,
                reason="Credits exhausted — forced fallback to Ollama",
                forced_fallback=True,
            )

        if tier == ModelTier.PLANNING:
            self._call_counts["planning"] = self._call_counts.get("planning", 0) + 1
            return RoutingDecision(
                tier=ModelTier.PLANNING,
                model=cfg.planning_model,
                max_tokens=cfg.planning_max_tokens,
                reason="Planning task detected — using Anthropic",
            )

        # EXECUTION tier — check RL_EVOLVED first (highest priority for eligible agents)
        if self.is_rl_available(agent_name):
            return self._route_rl(
                agent_name,
                f"RL-evolved model available for {agent_name}",
            )

        # Check if boost is eligible and enabled
        if (
            cfg.boost_enabled
            and task_type
            and task_type.upper() in BOOST_ELIGIBLE_TASKS
            and self._check_boost_daily_limit()
        ):
            return self._route_boost(
                f"Boost eligible task ({task_type}) — using AIClient",
            )

        # EXECUTION tier — route to specialist model if task type matches
        task_upper = task_type.upper() if task_type else ""

        if task_upper in CODING_TASKS and cfg.coding_model:
            self._call_counts["execution"] = self._call_counts.get("execution", 0) + 1
            return RoutingDecision(
                tier=ModelTier.EXECUTION,
                model=cfg.coding_model,
                max_tokens=cfg.coding_max_tokens,
                reason=f"Coding task ({task_type}) — using {cfg.coding_model}",
            )

        if task_upper in REASONING_TASKS and cfg.reasoning_model:
            self._call_counts["execution"] = self._call_counts.get("execution", 0) + 1
            return RoutingDecision(
                tier=ModelTier.EXECUTION,
                model=cfg.reasoning_model,
                max_tokens=cfg.reasoning_max_tokens,
                reason=f"Reasoning task ({task_type}) — using {cfg.reasoning_model}",
            )

        # Default EXECUTION — general-purpose model (Qwen3:8b)
        self._call_counts["execution"] = self._call_counts.get("execution", 0) + 1
        return RoutingDecision(
            tier=ModelTier.EXECUTION,
            model=cfg.execution_model,
            max_tokens=cfg.execution_max_tokens,
            reason=f"Execution task — using {cfg.execution_model}",
        )

    def _route_rl(self, agent_name: str | None, reason: str) -> RoutingDecision:
        """Create an RL_EVOLVED routing decision."""
        self._call_counts["rl_evolved"] = self._call_counts.get("rl_evolved", 0) + 1
        model = self.config.rl_model
        if agent_name:
            model = f"{model}:{agent_name}-lora"
        return RoutingDecision(
            tier=ModelTier.RL_EVOLVED,
            model=model,
            max_tokens=self.config.rl_max_tokens,
            reason=reason,
        )

    def _route_boost(self, reason: str) -> RoutingDecision:
        """Create a BOOST routing decision and record the call."""
        self._record_boost_call()
        self._call_counts["boost"] = self._call_counts.get("boost", 0) + 1
        return RoutingDecision(
            tier=ModelTier.BOOST,
            model=self.config.boost_model,
            max_tokens=self.config.boost_max_tokens,
            reason=reason,
        )

    def mark_credits_exhausted(self) -> None:
        """Mark Anthropic credits as exhausted. All calls route to Qwen3."""
        self.config.credits_exhausted = True
        self.config.credits_exhausted_at = time.time()
        logger.warning(
            "Anthropic credits exhausted — all calls routed to %s",
            self.config.execution_model,
        )

    def mark_credits_available(self) -> None:
        """Mark Anthropic credits as available again."""
        self.config.credits_exhausted = False
        self.config.credits_exhausted_at = 0.0
        logger.info("Anthropic credits restored")

    @property
    def stats(self) -> dict[str, Any]:
        """Return routing statistics."""
        return {
            "models": {
                "planning": self.config.planning_model,
                "execution": self.config.execution_model,
                "coding": self.config.coding_model,
                "reasoning": self.config.reasoning_model,
                "boost": self.config.boost_model,
                "rl": self.config.rl_model,
            },
            "planning_calls": self._call_counts.get("planning", 0),
            "execution_calls": self._call_counts.get("execution", 0),
            "boost_calls": self._call_counts.get("boost", 0),
            "rl_evolved_calls": self._call_counts.get("rl_evolved", 0),
            "boost_today": self._boost_today_count,
            "boost_daily_limit": self.config.boost_daily_limit,
            "boost_enabled": self.config.boost_enabled,
            "rl_enabled": self.config.rl_enabled,
            "rl_enabled_agents": sorted(self.config.rl_enabled_agents),
            "credits_exhausted": self.config.credits_exhausted,
        }
