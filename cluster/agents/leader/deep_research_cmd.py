"""Deep Research command handler for dispatch.py.

Implements /deepresearch <topic> — runs the iterative deep research pipeline
with academic source search, synthesis, and convergence evaluation.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from shared.models import Task, TaskResult
from shared.config import settings

__all__ = ["handle"]

logger = logging.getLogger("darklab.deep_research_cmd")


async def handle(task: Task) -> TaskResult:
    """Execute a deep research request.

    Usage: /deepresearch solid-state battery commercialization timeline
    """
    text = task.payload.get("text", "").strip()
    if not text:
        return TaskResult(
            task_id=task.task_id,
            agent_name="deep-research",
            status="error",
            result={"error": "Usage: /deepresearch <research topic>"},
        )

    try:
        from oas_core.deep_research import ResearchOrchestrator, ResearchConfig

        config = ResearchConfig(
            max_iterations=5,
            threshold=0.75,
        )
        orchestrator = ResearchOrchestrator(config)

        # Wire LLM synthesizer if Ollama/LiteLLM is available
        synthesizer = None
        try:
            from oas_core.deep_research.llm_synthesizer import LLMSynthesizer, SYNTHESIZER_AVAILABLE
            if SYNTHESIZER_AVAILABLE:
                ollama_url = settings.litellm_base_url or "http://localhost:11434"
                synth = LLMSynthesizer(ollama_url=ollama_url, model="qwen3:8b")
                synthesizer = synth.synthesize
        except Exception:
            pass  # Fall back to placeholder synthesis

        result = await orchestrator.run(
            topic=text,
            request_id=task.task_id,
            synthesizer=synthesizer,
        )

        return TaskResult(
            task_id=task.task_id,
            agent_name="deep-research",
            status="ok",
            result=result.to_dict(),
        )
    except Exception as exc:
        logger.error("deep_research_failed", error=str(exc))
        return TaskResult(
            task_id=task.task_id,
            agent_name="deep-research",
            status="error",
            result={"error": str(exc)},
        )
