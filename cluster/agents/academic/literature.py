"""DarkLab Literature Agent: deep literature reviews with structured citations.

Uses Perplexity (API or browser-use fallback), Gemini, and Claude for
comprehensive literature discovery and synthesis.
"""
from __future__ import annotations

import json
from shared.models import Task, TaskResult
from shared.llm_client import call_anthropic, call_perplexity, call_gemini
from shared.config import settings
from shared.node_bridge import run_agent

SYSTEM_PROMPT = """\
You are the DarkLab Literature Agent. Conduct a deep literature review on the given topic.

For each relevant paper or source found, extract:
- Title
- Authors (if available)
- Year
- Key findings
- Methodology summary
- Relevance to the research topic

Organize findings into themes and identify:
1. Consensus findings (agreed upon by multiple sources)
2. Contradictory findings (areas of disagreement)
3. Research gaps (unexplored areas)
4. Methodological trends

Output valid JSON:
{
  "topic": "string",
  "themes": [{"name": "string", "description": "string", "papers": [...]}],
  "consensus": ["string"],
  "contradictions": ["string"],
  "gaps": ["string"],
  "methodology_trends": ["string"],
  "total_sources": 0
}
"""


async def handle(task: Task) -> TaskResult:
    topic = task.payload.get("text", task.payload.get("topic", ""))
    if not topic:
        return TaskResult(
            task_id=task.task_id,
            agent_name="LiteratureAgent",
            status="error",
            result={"error": "No topic provided."},
        )

    search_results = {}

    # Step 1: Perplexity for real-time web research (if API key available)
    if settings.perplexity_api_key:
        try:
            perplexity_data = await call_perplexity(
                f"Comprehensive literature review: {topic}. "
                f"Include recent papers, key authors, and methodologies."
            )
            search_results["perplexity"] = perplexity_data
        except Exception as e:
            search_results["perplexity_error"] = str(e)
    else:
        # Browser-use fallback is handled by darklab-perplexity skill
        search_results["perplexity"] = "API key not configured; use darklab-perplexity skill for browser fallback"

    # Step 2: Gemini for cross-validation (if available)
    if settings.google_ai_api_key:
        try:
            gemini_text = await call_gemini(
                f"Literature review for: {topic}. List key papers, findings, and gaps."
            )
            search_results["gemini"] = gemini_text
        except Exception as e:
            search_results["gemini_error"] = str(e)

    # Step 3: Claude for synthesis
    synthesis_prompt = f"""Research topic: {topic}

Available search results:
{json.dumps(search_results, indent=2, default=str)}

Synthesize these into a structured literature review."""

    synthesis = await call_anthropic(synthesis_prompt, system=SYSTEM_PROMPT)

    try:
        result_data = json.loads(synthesis)
    except json.JSONDecodeError:
        result_data = {"synthesis": synthesis, "raw_search": search_results}

    result_data["sources_used"] = list(search_results.keys())

    return TaskResult(
        task_id=task.task_id,
        agent_name="LiteratureAgent",
        status="ok",
        result=result_data,
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="LiteratureAgent")
