"""Tests for oas_core.model_router — tiered model routing protocol."""
from __future__ import annotations

import time

import pytest

from oas_core.model_router import (
    BOOST_ELIGIBLE_TASKS,
    ModelRouter,
    ModelTier,
    RoutingDecision,
    TierConfig,
)


# ── Classification tests ─────────────────────────────────────────────────────


class TestClassify:
    """ModelRouter.classify() should detect planning vs execution."""

    def setup_method(self):
        self.router = ModelRouter()

    # -- Planning triggers --

    def test_plan_md_in_prompt(self):
        assert self.router.classify("Generate a plan.md for this project") == ModelTier.PLANNING

    def test_claude_md_in_prompt(self):
        assert self.router.classify("Create a CLAUDE.md with project guide") == ModelTier.PLANNING

    def test_decompose_in_prompt(self):
        assert self.router.classify("Decompose this into steps") == ModelTier.PLANNING

    def test_architecture_in_prompt(self):
        assert self.router.classify("Design the architecture for the API") == ModelTier.PLANNING

    def test_strategy_in_prompt(self):
        assert self.router.classify("Create a strategy for data migration") == ModelTier.PLANNING

    def test_campaign_planner_system(self):
        assert self.router.classify(
            "Research request: quantum computing",
            system="You are the DarkLab campaign planner.",
        ) == ModelTier.PLANNING

    def test_decompose_system(self):
        assert self.router.classify(
            "Break this down", system="decompose the request"
        ) == ModelTier.PLANNING

    def test_roadmap_in_prompt(self):
        assert self.router.classify("Build a roadmap for Q3") == ModelTier.PLANNING

    def test_plan_campaign_in_prompt(self):
        assert self.router.classify("Create a plan_campaign for sensor fusion") == ModelTier.PLANNING

    def test_design_of_experiment(self):
        assert self.router.classify("Design of Experiments for heat treatment") == ModelTier.PLANNING

    # -- Execution (no planning signal) --

    def test_simple_research_prompt(self):
        assert self.router.classify("Search for papers on graphene") == ModelTier.EXECUTION

    def test_synthesis_prompt(self):
        assert self.router.classify("Synthesize findings from the lab data") == ModelTier.EXECUTION

    def test_generic_question(self):
        assert self.router.classify("What is the melting point of titanium?") == ModelTier.EXECUTION

    def test_empty_prompt(self):
        assert self.router.classify("") == ModelTier.EXECUTION

    def test_code_prompt(self):
        assert self.router.classify("Fix the bug in parse_csv.py") == ModelTier.EXECUTION


# ── Routing tests ────────────────────────────────────────────────────────────


class TestRoute:
    """ModelRouter.route() should return correct model and tier."""

    def setup_method(self):
        self.router = ModelRouter(TierConfig(
            planning_model="claude-sonnet-4-6",
            execution_model="llama3.1",
        ))

    def test_planning_route(self):
        d = self.router.route("Create a plan.md for the project")
        assert d.tier == ModelTier.PLANNING
        assert d.model == "claude-sonnet-4-6"
        assert d.max_tokens == 8192
        assert not d.forced_fallback

    def test_execution_route(self):
        d = self.router.route("Summarize the experiment results")
        assert d.tier == ModelTier.EXECUTION
        assert d.model == "llama3.1"  # Explicit config in setup_method

    def test_force_planning(self):
        d = self.router.route("Simple question", force_tier=ModelTier.PLANNING)
        assert d.tier == ModelTier.PLANNING
        assert d.model == "claude-sonnet-4-6"

    def test_force_execution(self):
        d = self.router.route("Create a plan.md", force_tier=ModelTier.EXECUTION)
        assert d.tier == ModelTier.EXECUTION
        assert d.model == "llama3.1"  # Explicit config in setup_method


# ── Credit exhaustion tests ──────────────────────────────────────────────────


class TestCreditExhaustion:
    """When credits are exhausted, all calls should route to Ollama."""

    def setup_method(self):
        self.router = ModelRouter(TierConfig(
            planning_model="claude-sonnet-4-6",
            execution_model="llama3.1",
            credit_retry_interval=3600.0,
        ))

    def test_credits_exhausted_forces_execution(self):
        self.router.mark_credits_exhausted()
        d = self.router.route("Create a plan.md for the project")
        assert d.tier == ModelTier.EXECUTION
        assert d.model == "llama3.1"
        assert d.forced_fallback is True

    def test_execution_unaffected_by_credit_exhaustion(self):
        self.router.mark_credits_exhausted()
        d = self.router.route("Simple research query")
        assert d.tier == ModelTier.EXECUTION
        assert d.model == "llama3.1"
        # execution was already going to Ollama, so forced_fallback=False
        assert d.forced_fallback is False

    def test_credits_restored(self):
        self.router.mark_credits_exhausted()
        self.router.mark_credits_available()
        d = self.router.route("Create a plan.md for the project")
        assert d.tier == ModelTier.PLANNING
        assert d.model == "claude-sonnet-4-6"

    def test_credit_retry_after_interval(self):
        self.router.mark_credits_exhausted()
        # Simulate time passing beyond retry interval
        self.router.config.credits_exhausted_at = time.time() - 3601
        d = self.router.route("Create a plan.md for the project")
        assert d.tier == ModelTier.PLANNING
        assert d.model == "claude-sonnet-4-6"
        assert self.router.config.credits_exhausted is False

    def test_credit_retry_before_interval(self):
        self.router.mark_credits_exhausted()
        # Still within retry interval
        d = self.router.route("Create a plan.md for the project")
        assert d.tier == ModelTier.EXECUTION
        assert d.forced_fallback is True


# ── Boost tier tests ─────────────────────────────────────────────────────────


class TestBoostTier:
    """Boost tier routes to AIClient-2-API for eligible tasks."""

    def setup_method(self):
        self.router = ModelRouter(TierConfig(
            planning_model="claude-sonnet-4-6",
            execution_model="llama3.1",
            boost_model="gemini-2.5-flash",
            boost_max_tokens=8192,
            boost_enabled=True,
            boost_daily_limit=100,
        ))

    def test_boost_eligible_task(self):
        d = self.router.route("Search for papers", task_type="RESEARCH")
        assert d.tier == ModelTier.BOOST
        assert d.model == "gemini-2.5-flash"
        assert d.max_tokens == 8192

    def test_boost_eligible_literature(self):
        d = self.router.route("Find literature on quantum", task_type="LITERATURE")
        assert d.tier == ModelTier.BOOST

    def test_boost_eligible_paper(self):
        d = self.router.route("Write a paper draft", task_type="PAPER")
        assert d.tier == ModelTier.BOOST

    def test_boost_eligible_doe(self):
        d = self.router.route("Plan experiment", task_type="DOE")
        assert d.tier == ModelTier.BOOST

    def test_boost_eligible_synthesize(self):
        d = self.router.route("Combine results", task_type="SYNTHESIZE")
        assert d.tier == ModelTier.BOOST

    def test_boost_eligible_autoresearch(self):
        d = self.router.route("Run autonomous research", task_type="AUTORESEARCH")
        assert d.tier == ModelTier.BOOST

    def test_boost_ineligible_task(self):
        """Non-eligible tasks stay on execution tier even with boost enabled."""
        d = self.router.route("Run simulation", task_type="SIMULATE")
        assert d.tier == ModelTier.EXECUTION
        assert d.model == "qwen2.5-coder:7b"  # Coding specialist for SIMULATE

    def test_boost_ineligible_analyze(self):
        d = self.router.route("Analyze data", task_type="ANALYZE")
        assert d.tier == ModelTier.EXECUTION

    def test_boost_disabled(self):
        """When boost is disabled, eligible tasks stay on execution."""
        self.router.config.boost_enabled = False
        d = self.router.route("Search for papers", task_type="RESEARCH")
        assert d.tier == ModelTier.EXECUTION

    def test_boost_no_task_type(self):
        """Without task_type, no boost even if enabled."""
        d = self.router.route("Search for papers")
        assert d.tier == ModelTier.EXECUTION

    def test_force_boost(self):
        d = self.router.route("Any prompt", force_tier=ModelTier.BOOST)
        assert d.tier == ModelTier.BOOST
        assert d.model == "gemini-2.5-flash"

    def test_planning_not_affected_by_boost(self):
        """Planning prompts still route to Anthropic regardless of boost."""
        d = self.router.route(
            "Create a plan.md for the project", task_type="RESEARCH",
        )
        assert d.tier == ModelTier.PLANNING
        assert d.model == "claude-sonnet-4-6"


class TestBoostDailyLimit:
    """Boost daily limit prevents unlimited free calls."""

    def setup_method(self):
        self.router = ModelRouter(TierConfig(
            boost_enabled=True,
            boost_daily_limit=3,
            boost_model="gemini-2.5-flash",
        ))

    def test_under_daily_limit(self):
        for _ in range(3):
            d = self.router.route("Search", task_type="RESEARCH")
            assert d.tier == ModelTier.BOOST

    def test_over_daily_limit_falls_to_execution(self):
        for _ in range(3):
            self.router.route("Search", task_type="RESEARCH")
        # 4th call should fall to execution
        d = self.router.route("Search", task_type="RESEARCH")
        assert d.tier == ModelTier.EXECUTION

    def test_daily_limit_resets_on_new_day(self):
        for _ in range(3):
            self.router.route("Search", task_type="RESEARCH")
        # Simulate new day by resetting date tracker
        self.router._boost_today_date = "1999-01-01"
        d = self.router.route("Search", task_type="RESEARCH")
        assert d.tier == ModelTier.BOOST


class TestBoostCreditExhaustionFallback:
    """When credits exhausted and boost enabled, planning falls to boost."""

    def setup_method(self):
        self.router = ModelRouter(TierConfig(
            planning_model="claude-sonnet-4-6",
            execution_model="llama3.1",
            boost_model="gemini-2.5-flash",
            boost_enabled=True,
            boost_daily_limit=100,
        ))

    def test_credits_exhausted_falls_to_boost(self):
        self.router.mark_credits_exhausted()
        d = self.router.route("Create a plan.md for the project")
        assert d.tier == ModelTier.BOOST
        assert d.model == "gemini-2.5-flash"

    def test_credits_exhausted_boost_disabled_falls_to_execution(self):
        self.router.config.boost_enabled = False
        self.router.mark_credits_exhausted()
        d = self.router.route("Create a plan.md for the project")
        assert d.tier == ModelTier.EXECUTION
        assert d.forced_fallback is True

    def test_credits_exhausted_boost_limit_reached_falls_to_execution(self):
        self.router.config.boost_daily_limit = 0
        self.router.mark_credits_exhausted()
        d = self.router.route("Create a plan.md for the project")
        assert d.tier == ModelTier.EXECUTION
        assert d.forced_fallback is True


# ── Stats tests ──────────────────────────────────────────────────────────────


class TestStats:
    """Router should track call statistics."""

    def test_stats_tracking(self):
        router = ModelRouter()
        router.route("Create a plan.md")
        router.route("Simple query")
        router.route("Another simple query")
        stats = router.stats
        assert stats["planning_calls"] == 1
        assert stats["execution_calls"] == 2
        assert stats["credits_exhausted"] is False

    def test_stats_after_exhaustion(self):
        router = ModelRouter()
        router.route("Create a plan.md")  # planning
        router.mark_credits_exhausted()
        router.route("Create another plan.md")  # forced to execution
        stats = router.stats
        assert stats["planning_calls"] == 1
        assert stats["execution_calls"] == 1
        assert stats["credits_exhausted"] is True

    def test_stats_with_boost(self):
        router = ModelRouter(TierConfig(boost_enabled=True, boost_daily_limit=100))
        router.route("Search", task_type="RESEARCH")
        router.route("Simple query")
        stats = router.stats
        assert stats["boost_calls"] == 1
        assert stats["execution_calls"] == 1
        assert stats["boost_enabled"] is True
        assert stats["boost_today"] == 1


# ── TierConfig tests ─────────────────────────────────────────────────────────


class TestTierConfig:
    """TierConfig should have sensible defaults."""

    def test_defaults(self):
        cfg = TierConfig()
        assert cfg.planning_model == "claude-sonnet-4-6"
        assert cfg.execution_model == "qwen3:8b"
        assert cfg.coding_model == "qwen2.5-coder:7b"
        assert cfg.reasoning_model == "glm4:9b"
        assert cfg.boost_model == "gemini-2.5-flash"
        assert cfg.boost_enabled is False
        assert cfg.boost_daily_limit == 100
        assert cfg.rl_model == "qwen3:8b"
        assert cfg.rl_max_tokens == 12288
        assert cfg.credits_exhausted is False
        assert cfg.credit_retry_interval == 3600.0

    def test_custom_config(self):
        cfg = TierConfig(
            planning_model="claude-opus-4-6-20260301",
            execution_model="llama3.1:8b",
            boost_model="claude-sonnet-4-5",
            boost_enabled=True,
            credit_retry_interval=1800.0,
        )
        router = ModelRouter(cfg)
        d = router.route("Create a plan.md")
        assert d.model == "claude-opus-4-6-20260301"
        d2 = router.route("Simple query")
        assert d2.model == "llama3.1:8b"
        d3 = router.route("Research task", task_type="RESEARCH")
        assert d3.model == "claude-sonnet-4-5"


# ── Boost eligible tasks constant ────────────────────────────────────────────


class TestBoostEligibleTasks:
    """BOOST_ELIGIBLE_TASKS should contain the expected task types."""

    def test_eligible_tasks_present(self):
        expected = {
            "RESEARCH", "LITERATURE", "PAPER", "DOE",
            "SYNTHESIZE", "AUTORESEARCH", "DEERFLOW",
            "DEEP_RESEARCH", "SWARM_RESEARCH", "FULL_SWARM",
            "UNIPAT_SWARM",
        }
        assert BOOST_ELIGIBLE_TASKS == expected

    def test_simulate_not_eligible(self):
        assert "SIMULATE" not in BOOST_ELIGIBLE_TASKS

    def test_analyze_not_eligible(self):
        assert "ANALYZE" not in BOOST_ELIGIBLE_TASKS


class TestSpecialistRouting:
    """Task-type-aware specialist model routing (Qwen3 multi-model strategy)."""

    def setup_method(self):
        self.router = ModelRouter()  # Uses default TierConfig (Qwen3 models)

    def test_coding_task_routes_to_coder(self):
        d = self.router.route("Run simulation", task_type="SIMULATE")
        assert d.tier == ModelTier.EXECUTION
        assert d.model == "qwen2.5-coder:7b"

    def test_analyze_routes_to_coder(self):
        d = self.router.route("Analyze data", task_type="ANALYZE")
        assert d.model == "qwen2.5-coder:7b"

    def test_parameter_golf_routes_to_coder(self):
        d = self.router.route("Train model", task_type="PARAMETER_GOLF")
        assert d.model == "qwen2.5-coder:7b"

    def test_reasoning_task_routes_to_glm(self):
        d = self.router.route("Design experiment", task_type="DOE")
        assert d.model == "glm4:9b"

    def test_debate_routes_to_glm(self):
        d = self.router.route("Debate topic", task_type="DEBATE")
        assert d.model == "glm4:9b"

    def test_deep_research_routes_to_glm(self):
        d = self.router.route("Research topic", task_type="DEEP_RESEARCH")
        assert d.model == "glm4:9b"

    def test_general_task_routes_to_qwen3(self):
        d = self.router.route("Summarize findings", task_type="RESEARCH")
        # RESEARCH is boost-eligible but boost is disabled by default
        assert d.model == "qwen3:8b"

    def test_no_task_type_routes_to_qwen3(self):
        d = self.router.route("Hello world")
        assert d.model == "qwen3:8b"

    def test_rl_evolved_overrides_specialist(self):
        """RL_EVOLVED tier takes priority over specialist routing."""
        self.router.config.rl_enabled = True
        self.router.config.rl_proxy_url = "http://localhost:30000/v1"
        self.router.config.rl_enabled_agents = {"research"}
        d = self.router.route("Research", task_type="RESEARCH", agent_name="research")
        assert d.tier == ModelTier.RL_EVOLVED

    def test_default_model_names(self):
        cfg = TierConfig()
        assert cfg.execution_model == "qwen3:8b"
        assert cfg.coding_model == "qwen2.5-coder:7b"
        assert cfg.reasoning_model == "glm4:9b"
        assert cfg.rl_model == "qwen3:8b"
        assert cfg.rl_max_tokens == 12288
