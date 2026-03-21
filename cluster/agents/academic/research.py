"""DarkLab Research Agent: literature search, gap analysis, and research framing.

Invoked by OpenClaw node-host via:
  python3 -m darklab.agents.academic.research '{"task_type":"research","payload":{"text":"..."}}'
"""
from __future__ import annotations

import json
from shared.models import Task, TaskResult
from shared.llm_client import call_anthropic, call_multi_ai
from shared.node_bridge import run_agent

SYSTEM_PROMPT = """\
You are the DarkLab Research Agent, a scientific literature researcher.
Given a research topic, produce a comprehensive research framework with:

1. Refined research question
2. Key sub-questions (3-5)
3. Literature search strategy with suggested search terms
4. Potential data sources and databases
5. Identified research gaps
6. Proposed experimental approach
7. Success criteria

Output ONLY valid JSON with keys:
{
  "topic": "string",
  "refined_question": "string",
  "sub_questions": ["string"],
  "search_terms": ["string"],
  "data_sources": ["string"],
  "key_findings": ["string"],
  "research_gaps": ["string"],
  "proposed_approach": "string",
  "citations": [{"title": "string", "url": "string", "relevance": "string"}],
  "confidence": 0.85
}
"""


async def handle(task: Task) -> TaskResult:
    user_text = task.payload.get("text", "")
    if not user_text:
        return TaskResult(
            task_id=task.task_id,
            agent_name="ResearchAgent",
            status="error",
            result={"error": "No research topic provided. Include 'text' in payload."},
        )

    # Multi-AI research: Claude primary, cross-validate with available providers
    providers = ["anthropic"]
    if task.payload.get("cross_validate", False):
        providers.extend(["gemini", "openai"])

    if len(providers) > 1:
        responses = await call_multi_ai(
            f"Research topic: {user_text}\n\nProvide a comprehensive research framework.",
            system=SYSTEM_PROMPT,
            providers=providers,
        )
        # Use Claude as primary, include cross-validation
        primary = responses.get("anthropic", "")
        cross_val = {k: v for k, v in responses.items() if k != "anthropic"}
    else:
        primary = await call_anthropic(user_text, system=SYSTEM_PROMPT)
        cross_val = {}

    # Parse the primary response
    try:
        result_data = json.loads(primary)
    except json.JSONDecodeError:
        result_data = {"raw_response": primary}

    if cross_val:
        result_data["cross_validation"] = cross_val

    return TaskResult(
        task_id=task.task_id,
        agent_name="ResearchAgent",
        status="ok",
        result=result_data,
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="ResearchAgent")
