"""Swarm Research command handler — multi-angle parallel research.

Implements /swarmresearch <topic> — decomposes a topic into 5 specialist
perspectives and runs parallel deep research for each, then synthesizes
results into a unified report.

Perspectives:
  A — Foundations (classical theory, established methods)
  B — State of the Art (recent advances, current SOTA)
  C — Novel Pathways (unconventional approaches, cross-domain)
  D — Computational (simulation, verification, AI methods)
  E — Practical (applications, implementation, feasibility)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from shared.models import Task, TaskResult

__all__ = ["handle"]

logger = logging.getLogger("darklab.swarm_research_cmd")

PERSPECTIVES = [
    {
        "name": "foundations",
        "label": "Foundations",
        "prompt_suffix": "Focus on classical theory, established methods, foundational principles, and historical development.",
    },
    {
        "name": "sota",
        "label": "State of the Art",
        "prompt_suffix": "Focus on recent advances (last 2 years), current SOTA results, benchmarks, and leading research groups.",
    },
    {
        "name": "novel",
        "label": "Novel Pathways",
        "prompt_suffix": "Focus on unconventional approaches, cross-domain inspiration, emerging techniques, and speculative but promising directions.",
    },
    {
        "name": "computational",
        "label": "Computational",
        "prompt_suffix": "Focus on computational methods, simulations, AI/ML approaches, numerical techniques, and verification strategies.",
    },
    {
        "name": "practical",
        "label": "Practical",
        "prompt_suffix": "Focus on real-world applications, implementation challenges, cost analysis, scalability, and industry adoption.",
    },
]


async def handle(task: Task) -> TaskResult:
    """Execute multi-perspective swarm research.

    Usage: /swarmresearch quantum sensor applications for environmental monitoring
    """
    text = task.payload.get("text", "").strip()
    if not text:
        return TaskResult(
            task_id=task.task_id,
            agent_name="swarm-research",
            status="error",
            result={"error": "Usage: /swarmresearch <research topic>"},
        )

    # Emit start event
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        await emit(DRVPEvent(
            event_type=DRVPEventType.DEEP_RESEARCH_STARTED,
            request_id=task.task_id,
            agent_name="swarm-research",
            device="leader",
            payload={
                "topic": text[:200],
                "mode": "swarm",
                "perspectives": len(PERSPECTIVES),
            },
        ))
    except Exception:
        pass

    try:
        from oas_core.deep_research import ResearchOrchestrator, ResearchConfig

        # Run all perspectives in parallel (sequential on 16GB — set max_iterations=2 per angle)
        config = ResearchConfig(max_iterations=2, threshold=0.6)  # Lower bar per perspective
        orchestrator = ResearchOrchestrator(config)

        async def run_perspective(perspective: dict[str, str]) -> dict[str, Any]:
            augmented_topic = f"{text}\n\n{perspective['prompt_suffix']}"
            req_id = f"{task.task_id}-{perspective['name']}"
            result = await orchestrator.run(augmented_topic, req_id)
            return {
                "perspective": perspective["label"],
                "output": result.output,
                "score": round(result.final_score, 3),
                "sources": result.total_sources,
                "iterations": result.iterations_completed,
                "converged": result.converged,
            }

        # Run perspectives sequentially to respect 16GB RAM constraint
        perspective_results: list[dict[str, Any]] = []
        for i, perspective in enumerate(PERSPECTIVES):
            try:
                from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
                await emit(DRVPEvent(
                    event_type=DRVPEventType.DEEP_RESEARCH_ITERATION,
                    request_id=task.task_id,
                    agent_name="swarm-research",
                    device="leader",
                    payload={
                        "iteration": i + 1,
                        "total": len(PERSPECTIVES),
                        "perspective": perspective["label"],
                    },
                ))
            except Exception:
                pass

            pr = await run_perspective(perspective)
            perspective_results.append(pr)

        # Synthesize results
        total_sources = sum(r["sources"] for r in perspective_results)
        avg_score = sum(r["score"] for r in perspective_results) / len(perspective_results) if perspective_results else 0

        synthesis = _synthesize_perspectives(text, perspective_results)

        # Store to knowledge base
        try:
            from oas_core.deep_research.knowledge_base import KnowledgeBase
            from shared.config import settings
            kb = KnowledgeBase(settings.darklab_home / "deep-research")
            kb.store_research(
                topic=text,
                score=avg_score,
                summary=synthesis[:500],
                sources_count=total_sources,
                iterations=sum(r["iterations"] for r in perspective_results),
                converged=all(r["converged"] for r in perspective_results),
            )
        except Exception:
            pass

        # Emit completion
        try:
            from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
            await emit(DRVPEvent(
                event_type=DRVPEventType.DEEP_RESEARCH_COMPLETED,
                request_id=task.task_id,
                agent_name="swarm-research",
                device="leader",
                payload={"score": round(avg_score, 3), "sources": total_sources},
            ))
        except Exception:
            pass

        return TaskResult(
            task_id=task.task_id,
            agent_name="swarm-research",
            status="ok",
            result={
                "output": synthesis,
                "topic": text,
                "mode": "swarm",
                "perspectives": perspective_results,
                "total_sources": total_sources,
                "average_score": round(avg_score, 3),
            },
        )
    except Exception as exc:
        logger.error("swarm_research_failed", error=str(exc))
        return TaskResult(
            task_id=task.task_id,
            agent_name="swarm-research",
            status="error",
            result={"error": str(exc)},
        )


def _synthesize_perspectives(topic: str, results: list[dict[str, Any]]) -> str:
    """Merge perspective outputs into a unified report."""
    sections = [
        f"# Swarm Research Report: {topic}\n",
        f"**Mode:** Multi-perspective swarm ({len(results)} angles)\n",
        f"**Sources:** {sum(r['sources'] for r in results)} papers\n",
        f"**Average score:** {sum(r['score'] for r in results) / len(results):.2f}/1.0\n",
    ]

    for r in results:
        sections.append(f"\n## {r['perspective']}")
        sections.append(f"*Score: {r['score']}/1.0 | {r['sources']} sources | {r['iterations']} iterations*\n")
        # Take first 1000 chars of each perspective output
        output = r.get("output", "")
        if output:
            # Strip the top-level heading to avoid nested # conflicts
            lines = output.split("\n")
            content_lines = [l for l in lines if not l.startswith("# ")]
            sections.append("\n".join(content_lines[:40]))

    sections.append("\n---\n*Generated by DarkLab Swarm Research*")
    return "\n".join(sections)
