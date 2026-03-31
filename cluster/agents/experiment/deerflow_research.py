"""DeerFlow research handler — dispatched via /deerflow command.

Wraps the OAS DeerFlow adapter to execute deep, multi-step research tasks
using DeerFlow's sub-agent orchestration, skills, and sandbox capabilities.
Integrates with the OAS model router for tiered model selection (planning
via Anthropic, execution via Ollama, boost via AIClient).
"""
from __future__ import annotations

from typing import Any

import structlog

from shared.models import Task, TaskResult
from shared.node_bridge import run_agent

__all__ = ["handle"]

logger = structlog.get_logger("darklab.deerflow_research")


def _select_model(query: str) -> str | None:
    """Select a DeerFlow model name based on OAS model routing tier.

    Returns a model name string matching a name in DeerFlow's config.yaml,
    or None to use DeerFlow's default.
    """
    try:
        from shared.llm_client import get_model_router
        from oas_core.model_router import ModelTier

        router = get_model_router()
        if router is None:
            return None

        decision = router.route(query, task_type="DEERFLOW")
        tier_map: dict[Any, str] = {
            ModelTier.PLANNING: "claude-sonnet",
            ModelTier.BOOST: "gemini-boost",
            ModelTier.EXECUTION: "ollama-local",
        }
        return tier_map.get(decision.tier)
    except Exception as exc:
        logger.debug("model_selection_fallback", error=str(exc))
        return None


async def handle(task: Task) -> TaskResult:
    """Handle a /deerflow research task.

    Payload keys
    ------------
    query : str
        The research question or objective (also accepted as ``args``).
    model : str, optional
        Override the DeerFlow model name directly.
    files : list[str], optional
        Local file paths to upload before executing.
    thread_id : str, optional
        Reuse an existing DeerFlow thread for multi-turn context.
    thinking : bool, optional
        Enable extended thinking (default True).
    subagents : bool, optional
        Enable sub-agent spawning (default True).
    """
    try:
        from oas_core.adapters.deerflow import DeerFlowAdapter, DEERFLOW_AVAILABLE
    except ImportError:
        return TaskResult(
            task_id=task.task_id,
            agent_name="DeerFlowResearch",
            status="error",
            result={"error": "oas_core.adapters.deerflow not available"},
        )

    if not DEERFLOW_AVAILABLE:
        return TaskResult(
            task_id=task.task_id,
            agent_name="DeerFlowResearch",
            status="error",
            result={
                "error": "deerflow-harness not installed",
                "hint": "Install: uv pip install -e ./frameworks/deer-flow-main/backend/packages/harness",
            },
        )

    query = task.payload.get("query") or task.payload.get("args", "")
    if not query:
        return TaskResult(
            task_id=task.task_id,
            agent_name="DeerFlowResearch",
            status="error",
            result={"error": "No query provided. Usage: /deerflow <research objective>"},
        )

    model = task.payload.get("model")  # Explicit override only; let DeerFlow use its default
    files = task.payload.get("files", [])
    thread_id = task.payload.get("thread_id")
    thinking = task.payload.get("thinking", True)
    subagents = task.payload.get("subagents", True)

    adapter = DeerFlowAdapter(
        model_name=model,
        thinking_enabled=thinking,
        subagent_enabled=subagents,
    )

    try:
        result = await adapter.run_research(
            request_id=task.task_id,
            query=query,
            agent_name="deerflow",
            device="leader",
            thread_id=thread_id,
            files=files,
        )
    except Exception as exc:
        logger.error("deerflow_research_failed", error=str(exc), task_id=task.task_id)
        return TaskResult(
            task_id=task.task_id,
            agent_name="DeerFlowResearch",
            status="error",
            result={"error": str(exc)},
        )

    return TaskResult(
        task_id=task.task_id,
        agent_name="DeerFlowResearch",
        status="ok",
        result={
            "output": result.get("output", ""),
            "thread_id": result.get("thread_id"),
            "model": model,
        },
        artifacts=result.get("artifacts", []),
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="DeerFlowResearch")
