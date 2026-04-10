"""Tiered Model Router — 7-tier v2 taxonomy with degradation chain.

v2 taxonomy (OAS-V2-MERGED-PLAN §4):

  PLANNING_LOCAL       — Leader's Gemma 4 E4B for routing/parsing ($0)
  REASONING_LOCAL      — DEV's Gemma 4 27B MoE Q4, borrowed ($0)
  CODE_LOCAL           — DEV's Qwen2.5-Coder 7B ($0)
  WORKER_LOCAL         — DEV's 3× Gemma 4 E4B pool, borrowed ($0)
  RL_EVOLVED           — DEV's Qwen3 + per-agent LoRA ($0)
  CLAUDE_SONNET        — Cloud, per-mission budget cap (auto within cap)
  CLAUDE_OPUS          — Cloud, per-call Boss approval (no bypass)

v2 degradation chain (§6.4):

  REASONING_LOCAL → PLANNING_LOCAL → CLAUDE_SONNET → CLAUDE_OPUS → blocked

Legacy tier names (PLANNING, EXECUTION, BOOST) are preserved for backwards
compatibility. The old ``route()`` method still works unchanged; the new
``route_v2()`` method implements the full degradation chain using
``CapabilityManifest`` from DEV heartbeats.
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
    "RoutingContext",
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
    "UNIPAT_SWARM",
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
    "UNIPAT_SWARM",
}


class ModelTier(str, Enum):
    """Which quality tier a request should use.

    v2 tiers (Phase 24+) — canonical 7-tier taxonomy:

    - ``PLANNING_LOCAL`` — Leader's Gemma 4 E4B
    - ``REASONING_LOCAL`` — DEV's Gemma 4 27B MoE Q4 (borrowed)
    - ``CODE_LOCAL`` — DEV's Qwen2.5-Coder 7B
    - ``WORKER_LOCAL`` — DEV's 3× Gemma 4 E4B pool (borrowed)
    - ``RL_EVOLVED`` — DEV's Qwen3 + per-agent LoRA
    - ``CLAUDE_SONNET`` — Cloud, per-mission budget cap
    - ``CLAUDE_OPUS`` — Cloud, per-call Boss approval

    Legacy names kept for backwards compat:

    - ``PLANNING`` ≈ ``CLAUDE_SONNET`` (old code that said "planning"
      meant "use Claude")
    - ``EXECUTION`` ≈ ``WORKER_LOCAL`` (old code that said "execution"
      meant "use local model")
    - ``BOOST`` — AIClient free tier (unchanged)
    """

    # ── v2 tiers ────────────────────────────────────────────────────
    PLANNING_LOCAL = "planning_local"
    REASONING_LOCAL = "reasoning_local"
    CODE_LOCAL = "code_local"
    WORKER_LOCAL = "worker_local"
    RL_EVOLVED = "rl_evolved"
    CLAUDE_SONNET = "claude_sonnet"
    CLAUDE_OPUS = "claude_opus"

    # ── Legacy compat (still used by v1 route() callers) ────────────
    PLANNING = "planning"
    EXECUTION = "execution"
    BOOST = "boost"

    @property
    def is_local(self) -> bool:
        """Whether this tier runs entirely on cluster hardware ($0)."""
        return self in _LOCAL_TIERS

    @property
    def is_cloud(self) -> bool:
        return self in (ModelTier.CLAUDE_SONNET, ModelTier.CLAUDE_OPUS)

    @property
    def is_borrowed(self) -> bool:
        """Whether this tier borrows DEV compute (Leader retains authority)."""
        return self in (ModelTier.REASONING_LOCAL, ModelTier.WORKER_LOCAL)


_LOCAL_TIERS = frozenset({
    ModelTier.PLANNING_LOCAL,
    ModelTier.REASONING_LOCAL,
    ModelTier.CODE_LOCAL,
    ModelTier.WORKER_LOCAL,
    ModelTier.RL_EVOLVED,
})


@dataclass(frozen=True)
class RoutingContext:
    """Per-call context for the v2 degradation chain.

    Leader constructs this before each route_v2 call from the current
    mission, the latest CapabilityManifest, and the live spend tracker.
    """

    # Mission identity
    mission_id: str = ""
    mission_confidential: bool = False

    # Per-mission Sonnet budget (from plan file)
    sonnet_cap_usd: float = 0.0
    sonnet_spent_usd: float = 0.0

    # Whether Opus is allowed at all for this mission
    opus_allowed: bool = False

    # Daily spend for idle-budget gating
    daily_spend_usd: float = 0.0
    daily_budget_usd: float = 50.0

    # DEV availability (from latest CapabilityManifest)
    dev_reachable: bool = False
    dev_priority_floor: int = 5  # Conservative default = reject all
    dev_reasoning_ready: bool = False
    dev_worker_pool_free: int = 0
    dev_code_ready: bool = False

    # Caller hints
    task_type: str = ""
    agent_name: str = ""
    prompt_hint: str = ""
    action_scope: str = ""  # "idle" / "kairos" / "" for normal

    @property
    def sonnet_budget_remaining(self) -> float:
        return max(0.0, self.sonnet_cap_usd - self.sonnet_spent_usd)

    @property
    def sonnet_budget_available(self) -> bool:
        return self.sonnet_budget_remaining > 0.0


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

    # ── v2 tier models (Ollama tag format) ──────────────────────────
    planning_local_model: str = "gemma4:e2b"
    reasoning_local_model: str = "gemma4:e4b"
    code_local_model: str = "qwen2.5-coder:7b"
    worker_local_model: str = "gemma4:e2b"
    sonnet_model: str = "claude-sonnet-4-6-20260301"
    opus_model: str = "claude-opus-4-6-20260301"
    # Context windows
    planning_local_max_tokens: int = 4096
    reasoning_local_max_tokens: int = 16384
    code_local_max_tokens: int = 8192
    worker_local_max_tokens: int = 4096
    sonnet_max_tokens: int = 8192
    opus_max_tokens: int = 8192


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

    # ------------------------------------------------------------------
    # v2 degradation-chain routing (Phase 24+)
    # ------------------------------------------------------------------
    def route_v2(self, ctx: RoutingContext) -> RoutingDecision:
        """Route using the 7-tier taxonomy with the §6.4 degradation chain.

        ``RoutingContext`` carries the mission budget, DEV availability,
        confidential flag, and task hints. The router walks down the
        chain until it finds a viable tier or blocks the mission.

        Returns a ``RoutingDecision`` whose ``.tier`` is one of the 7
        v2 enum values.
        """
        cfg = self.config
        task_upper = ctx.task_type.upper() if ctx.task_type else ""

        # ── 0. RL_EVOLVED has highest priority when available ─────
        if self.is_rl_available(ctx.agent_name):
            self._call_counts["rl_evolved"] = (
                self._call_counts.get("rl_evolved", 0) + 1
            )
            model = cfg.rl_model
            if ctx.agent_name:
                model = f"{model}:{ctx.agent_name}-lora"
            return RoutingDecision(
                tier=ModelTier.RL_EVOLVED,
                model=model,
                max_tokens=cfg.rl_max_tokens,
                reason=f"RL-evolved LoRA available for {ctx.agent_name}",
            )

        # ── 1. Task-type pinning (§4.1) ──────────────────────────
        if task_upper in CODING_TASKS and ctx.dev_code_ready:
            self._call_counts["code_local"] = (
                self._call_counts.get("code_local", 0) + 1
            )
            return RoutingDecision(
                tier=ModelTier.CODE_LOCAL,
                model=cfg.code_local_model,
                max_tokens=cfg.code_local_max_tokens,
                reason=f"Code task ({ctx.task_type}) → CODE_LOCAL",
            )

        # ── 2. Check if planning intent ──────────────────────────
        is_planning = self.classify(
            ctx.prompt_hint, ""
        ) == ModelTier.PLANNING

        # ── 3. Degradation chain starts here ─────────────────────
        # Step A: Try REASONING_LOCAL (borrow DEV 27B) — best $0
        if ctx.dev_reachable and ctx.dev_reasoning_ready:
            accepts = ctx.dev_priority_floor <= 3  # default borrow priority
            if accepts:
                self._call_counts["reasoning_local"] = (
                    self._call_counts.get("reasoning_local", 0) + 1
                )
                return RoutingDecision(
                    tier=ModelTier.REASONING_LOCAL,
                    model=cfg.reasoning_local_model,
                    max_tokens=cfg.reasoning_local_max_tokens,
                    reason="REASONING_LOCAL — borrowed DEV 27B",
                )

        # Step B: Fallback to PLANNING_LOCAL (Leader's own E4B) — $0
        self._call_counts["planning_local"] = (
            self._call_counts.get("planning_local", 0) + 1
        )
        # For simple tasks, PLANNING_LOCAL is sufficient — return
        if not is_planning and task_upper not in REASONING_TASKS:
            return RoutingDecision(
                tier=ModelTier.PLANNING_LOCAL,
                model=cfg.planning_local_model,
                max_tokens=cfg.planning_local_max_tokens,
                reason="PLANNING_LOCAL fallback — DEV unavailable/busy",
            )

        # For planning/reasoning tasks, local E4B may not be enough.
        # Decide whether to escalate to cloud.

        # Step C: Confidential missions block all cloud tiers
        if ctx.mission_confidential:
            return RoutingDecision(
                tier=ModelTier.PLANNING_LOCAL,
                model=cfg.planning_local_model,
                max_tokens=cfg.planning_local_max_tokens,
                reason="Confidential mission — local-only, quality may be degraded",
                forced_fallback=True,
            )

        # Step D: Try CLAUDE_SONNET (if within per-mission budget)
        if ctx.sonnet_budget_available:
            self._call_counts["claude_sonnet"] = (
                self._call_counts.get("claude_sonnet", 0) + 1
            )
            return RoutingDecision(
                tier=ModelTier.CLAUDE_SONNET,
                model=cfg.sonnet_model,
                max_tokens=cfg.sonnet_max_tokens,
                reason=(
                    f"CLAUDE_SONNET — ${ctx.sonnet_budget_remaining:.2f} "
                    f"remaining in mission budget"
                ),
            )

        # Step E: Request CLAUDE_OPUS (if allowed and not confidential)
        if ctx.opus_allowed:
            self._call_counts["claude_opus"] = (
                self._call_counts.get("claude_opus", 0) + 1
            )
            return RoutingDecision(
                tier=ModelTier.CLAUDE_OPUS,
                model=cfg.opus_model,
                max_tokens=cfg.opus_max_tokens,
                reason=(
                    "CLAUDE_OPUS requested — Sonnet budget exhausted, "
                    "awaiting Boss approval"
                ),
            )

        # Step F: All options exhausted — stay on local, degraded
        return RoutingDecision(
            tier=ModelTier.PLANNING_LOCAL,
            model=cfg.planning_local_model,
            max_tokens=cfg.planning_local_max_tokens,
            reason="All escalation paths exhausted — local-only, degraded quality",
            forced_fallback=True,
        )

    # ------------------------------------------------------------------
    # Worker routing for fan-out sub-tasks
    # ------------------------------------------------------------------
    def route_worker(self, ctx: RoutingContext) -> RoutingDecision:
        """Route a worker sub-task to the DEV pool or local fallback.

        Used for research fan-out, literature scans, DOE parsing, etc.
        """
        if ctx.dev_reachable and ctx.dev_worker_pool_free > 0:
            self._call_counts["worker_local"] = (
                self._call_counts.get("worker_local", 0) + 1
            )
            return RoutingDecision(
                tier=ModelTier.WORKER_LOCAL,
                model=self.config.worker_local_model,
                max_tokens=self.config.worker_local_max_tokens,
                reason=f"WORKER_LOCAL — {ctx.dev_worker_pool_free} slots free",
            )
        # Fallback to Leader's own E4B
        self._call_counts["planning_local"] = (
            self._call_counts.get("planning_local", 0) + 1
        )
        return RoutingDecision(
            tier=ModelTier.PLANNING_LOCAL,
            model=self.config.planning_local_model,
            max_tokens=self.config.planning_local_max_tokens,
            reason="Worker fallback — DEV pool unavailable, using Leader E4B",
            forced_fallback=True,
        )

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
                # v2
                "planning_local": self.config.planning_local_model,
                "reasoning_local": self.config.reasoning_local_model,
                "code_local": self.config.code_local_model,
                "worker_local": self.config.worker_local_model,
                "sonnet": self.config.sonnet_model,
                "opus": self.config.opus_model,
            },
            "planning_calls": self._call_counts.get("planning", 0),
            "execution_calls": self._call_counts.get("execution", 0),
            "boost_calls": self._call_counts.get("boost", 0),
            "rl_evolved_calls": self._call_counts.get("rl_evolved", 0),
            # v2
            "planning_local_calls": self._call_counts.get("planning_local", 0),
            "reasoning_local_calls": self._call_counts.get("reasoning_local", 0),
            "code_local_calls": self._call_counts.get("code_local", 0),
            "worker_local_calls": self._call_counts.get("worker_local", 0),
            "claude_sonnet_calls": self._call_counts.get("claude_sonnet", 0),
            "claude_opus_calls": self._call_counts.get("claude_opus", 0),
            "boost_today": self._boost_today_count,
            "boost_daily_limit": self.config.boost_daily_limit,
            "boost_enabled": self.config.boost_enabled,
            "rl_enabled": self.config.rl_enabled,
            "rl_enabled_agents": sorted(self.config.rl_enabled_agents),
            "credits_exhausted": self.config.credits_exhausted,
        }
