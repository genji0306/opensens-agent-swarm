"""model-router MCP server.

Exposes the OAS 7-tier model router as a Model Context Protocol server.
External tools can query the router to see which tier would handle a
given task type under a given routing context, without importing the
full OAS framework.

Tools exposed:
  - route_task: Given task_type and optional routing_context, return the
    tier that ``ModelRouter.route_v2`` would pick.
  - list_tiers: Return the 7 tiers with location, gate, and cost class.
  - inspect_policy: Return the active policy rules and their thresholds.

Run with::

    python -m oas_core.mcp.model_router

Talks JSON-RPC 2.0 over stdio per the MCP spec.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    Server = None  # type: ignore[assignment,misc]
    Tool = None  # type: ignore[assignment,misc]
    TextContent = None  # type: ignore[assignment,misc]

logger = logging.getLogger("oas.mcp.model_router")

__all__ = ["create_server", "main"]


TIER_TABLE: list[dict[str, str]] = [
    {
        "tier": "PLANNING_LOCAL",
        "location": "Leader (Gemma 4 E4B)",
        "gate": "Automatic",
        "cost_class": "zero",
    },
    {
        "tier": "REASONING_LOCAL",
        "location": "DEV (Gemma 4 27B MoE Q4, borrowed)",
        "gate": "Automatic",
        "cost_class": "zero",
    },
    {
        "tier": "WORKER_LOCAL",
        "location": "DEV (3x Gemma 4 E4B pool, borrowed)",
        "gate": "Automatic, time-sliced",
        "cost_class": "zero",
    },
    {
        "tier": "CODE_LOCAL",
        "location": "DEV (Qwen2.5-Coder 7B)",
        "gate": "DEV task delegation",
        "cost_class": "zero",
    },
    {
        "tier": "RL_EVOLVED",
        "location": "DEV (Qwen3 + per-agent LoRA)",
        "gate": "Automatic when LoRA available",
        "cost_class": "zero",
    },
    {
        "tier": "CLAUDE_SONNET",
        "location": "Cloud (Anthropic)",
        "gate": "Per-mission budget cap (SonnetBudgetRule)",
        "cost_class": "metered",
    },
    {
        "tier": "CLAUDE_OPUS",
        "location": "Cloud (Anthropic)",
        "gate": "Per-call Boss approval (OpusGateRule, no bypass)",
        "cost_class": "metered-gated",
    },
]


POLICY_RULES: list[dict[str, str]] = [
    {
        "name": "OpusGateRule",
        "effect": "Blocks CLAUDE_OPUS unless Boss has approved this specific call",
        "threshold": "Per-call approval required; 24-hour cooldown to disable",
    },
    {
        "name": "SonnetBudgetRule",
        "effect": "Blocks CLAUDE_SONNET once plan.sonnet_cap_usd is exhausted",
        "threshold": "Per-PlanFile instance; resets on new plan",
    },
    {
        "name": "IdleBudgetRule",
        "effect": "Blocks cloud tiers during KAIROS-initiated work past budget ratio",
        "threshold": "20% of daily spend budget",
    },
    {
        "name": "ConfidentialRule",
        "effect": "Blocks all cloud tiers when mission.confidential=true",
        "threshold": "Binary flag on the PlanFile",
    },
]


# Heuristic routing table that mirrors ModelRouter.route_v2 decisions
# without actually importing it (the MCP server must run in isolation
# so a fresh Python process can start it without the full OAS deps).
TASK_TYPE_DEFAULT_TIER: dict[str, str] = {
    "RESEARCH": "REASONING_LOCAL",
    "LITERATURE": "REASONING_LOCAL",
    "DEEP_RESEARCH": "REASONING_LOCAL",
    "SYNTHESIZE": "REASONING_LOCAL",
    "PAPER_REVIEW": "REASONING_LOCAL",
    "DEBATE": "REASONING_LOCAL",
    "PERPLEXITY": "CLAUDE_SONNET",
    "SIMULATE": "CODE_LOCAL",
    "ANALYZE": "WORKER_LOCAL",
    "DOE": "PLANNING_LOCAL",
    "PLAN": "PLANNING_LOCAL",
    "ORCHESTRATE": "PLANNING_LOCAL",
    "KAIROS": "PLANNING_LOCAL",
    "DFT": "CODE_LOCAL",
    "ANE_RESEARCH": "REASONING_LOCAL",
    "GEMMA_SWARM": "WORKER_LOCAL",
    "UNIPAT_SWARM": "WORKER_LOCAL",
    "TURBO_SWARM": "REASONING_LOCAL",
    "FULL_SWARM": "REASONING_LOCAL",
    "RL_TRAIN": "RL_EVOLVED",
    "AUTORESEARCH": "REASONING_LOCAL",
    "WIKI_COMPILE": "PLANNING_LOCAL",
    "WIKI_LINT": "PLANNING_LOCAL",
    "EVAL_RUN": "PLANNING_LOCAL",
    "EVAL_REPORT": "PLANNING_LOCAL",
}


def _route_task(task_type: str, context: dict[str, Any]) -> dict[str, Any]:
    """Return the tier the router would pick for (task_type, context)."""
    normalized = task_type.upper()
    default_tier = TASK_TYPE_DEFAULT_TIER.get(normalized, "PLANNING_LOCAL")

    confidential = bool(context.get("confidential", False))
    dev_reachable = bool(context.get("dev_reachable", True))
    quality_threshold = float(context.get("quality_threshold", 0.7))
    prior_tier_failed = bool(context.get("prior_tier_failed", False))
    budget_remaining_usd = float(context.get("budget_remaining_usd", 100.0))

    chosen = default_tier
    reason = f"default tier for {normalized}"

    if confidential and chosen in {"CLAUDE_SONNET", "CLAUDE_OPUS"}:
        chosen = "REASONING_LOCAL"
        reason = "confidential mission blocks cloud tiers"

    if chosen in {"REASONING_LOCAL", "WORKER_LOCAL", "CODE_LOCAL"} and not dev_reachable:
        chosen = "PLANNING_LOCAL"
        reason = "DEV unreachable, falling back to Leader-local"

    if prior_tier_failed and chosen.endswith("_LOCAL") and not confidential:
        if budget_remaining_usd > 1.0:
            chosen = "CLAUDE_SONNET"
            reason = "prior local tier failed, escalating to Sonnet within budget"
        else:
            reason = "prior local tier failed but budget exhausted, mission blocked"

    return {
        "task_type": normalized,
        "chosen_tier": chosen,
        "reason": reason,
        "quality_threshold": quality_threshold,
        "would_escalate_to_sonnet": chosen == "CLAUDE_SONNET",
        "would_request_opus": chosen == "CLAUDE_OPUS",
    }


def create_server() -> Any:
    """Construct an MCP Server with the model-router tools registered."""
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "mcp SDK not installed. Install with: pip install mcp"
        )

    server = Server("oas-model-router")  # type: ignore[misc]

    @server.list_tools()
    async def list_tools() -> list[Any]:
        return [
            Tool(  # type: ignore[misc]
                name="route_task",
                description=(
                    "Compute which model tier the OAS router would pick for a task_type. "
                    "Returns chosen_tier, reason, and whether cloud escalation would occur."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_type": {
                            "type": "string",
                            "description": "TaskType enum value, e.g. RESEARCH, SIMULATE, DEEP_RESEARCH",
                        },
                        "context": {
                            "type": "object",
                            "description": "RoutingContext fields (confidential, dev_reachable, quality_threshold, prior_tier_failed, budget_remaining_usd)",
                            "properties": {
                                "confidential": {"type": "boolean"},
                                "dev_reachable": {"type": "boolean"},
                                "quality_threshold": {"type": "number"},
                                "prior_tier_failed": {"type": "boolean"},
                                "budget_remaining_usd": {"type": "number"},
                            },
                        },
                    },
                    "required": ["task_type"],
                },
            ),
            Tool(  # type: ignore[misc]
                name="list_tiers",
                description="Return the full 7-tier model taxonomy with location, gate, and cost class.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(  # type: ignore[misc]
                name="inspect_policy",
                description="Return the active DecisionPolicyEngine rules (OpusGate, SonnetBudget, IdleBudget, Confidential).",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
        if name == "route_task":
            task_type = arguments.get("task_type", "")
            if not task_type:
                return [TextContent(type="text", text='{"error": "task_type is required"}')]  # type: ignore[misc]
            context = arguments.get("context", {}) or {}
            result = _route_task(task_type, context)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]  # type: ignore[misc]

        if name == "list_tiers":
            return [TextContent(type="text", text=json.dumps(TIER_TABLE, indent=2))]  # type: ignore[misc]

        if name == "inspect_policy":
            return [TextContent(type="text", text=json.dumps(POLICY_RULES, indent=2))]  # type: ignore[misc]

        return [TextContent(type="text", text=f'{{"error": "unknown tool: {name}"}}')]  # type: ignore[misc]

    return server


async def _run() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):  # type: ignore[misc]
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    if not _MCP_AVAILABLE:
        raise SystemExit(
            "mcp SDK not installed. Install with: pip install mcp"
        )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
