"""DarkLab Perplexity Agent: web research with citations.

API-first with browser-use fallback for when API key is not configured.
"""
from __future__ import annotations

import json
from shared.models import Task, TaskResult
from shared.llm_client import call_perplexity
from shared.config import settings
from shared.node_bridge import run_agent


async def _api_search(query: str) -> dict:
    """Search via Perplexity API (fast path)."""
    result = await call_perplexity(query)
    return {
        "source": "api",
        "text": result["text"],
        "citations": result.get("citations", []),
    }


async def _browser_search(query: str) -> dict:
    """Search via browser-use powered browser automation (fallback)."""
    try:
        from academic.browser_agent import browse_perplexity
        result = await browse_perplexity(query)
        return {
            "source": "browser",
            "text": str(result.final_result()) if hasattr(result, 'final_result') else str(result),
        }
    except ImportError:
        return {
            "source": "unavailable",
            "error": "browser-use not installed. Install with: uv pip install browser-use",
        }
    except Exception as e:
        return {
            "source": "browser_error",
            "error": str(e),
        }


async def handle(task: Task) -> TaskResult:
    query = task.payload.get("query", task.payload.get("text", ""))
    if not query:
        return TaskResult(
            task_id=task.task_id,
            agent_name="PerplexityAgent",
            status="error",
            result={"error": "No query provided."},
        )

    # API-first, browser-use fallback
    if settings.perplexity_api_key:
        try:
            result_data = await _api_search(query)
        except Exception as e:
            # API failed, try browser fallback
            result_data = await _browser_search(query)
    else:
        result_data = await _browser_search(query)

    return TaskResult(
        task_id=task.task_id,
        agent_name="PerplexityAgent",
        status="ok" if "error" not in result_data else "error",
        result=result_data,
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="PerplexityAgent")
