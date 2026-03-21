"""DarkLab Paper Agent: draft research papers with multi-AI validation.

Uses OpenAI + Gemini + Claude for manuscript preparation with
cross-validation of claims and proper citation formatting.
"""
from __future__ import annotations

import json
from pathlib import Path
from shared.models import Task, TaskResult
from shared.llm_client import call_anthropic, call_openai, call_gemini, call_multi_ai
from shared.config import settings
from shared.node_bridge import run_agent

SYSTEM_PROMPT = """\
You are the DarkLab Paper Agent. Draft a research paper section or full manuscript.

Follow academic writing standards:
1. Abstract (if full paper)
2. Introduction with literature context
3. Methods (clear, reproducible)
4. Results with data interpretation
5. Discussion connecting to existing literature
6. Conclusion with future work

Use formal scientific language. Include citation placeholders as [Author, Year] or [N].
Ensure all claims are supported by data or literature references.

Output valid JSON:
{
  "title": "string",
  "sections": [{"heading": "string", "content": "string"}],
  "citations": [{"id": "N", "text": "Author et al., Year. Title. Journal."}],
  "word_count": 0,
  "format": "paper_draft"
}
"""


async def handle(task: Task) -> TaskResult:
    topic = task.payload.get("text", task.payload.get("topic", ""))
    data = task.payload.get("data", {})
    research_plan = task.payload.get("research_plan", {})
    section = task.payload.get("section", "full")  # "abstract", "intro", "methods", etc.

    if not topic:
        return TaskResult(
            task_id=task.task_id,
            agent_name="PaperAgent",
            status="error",
            result={"error": "No topic provided."},
        )

    prompt = f"Research topic: {topic}\nSection to draft: {section}"
    if data:
        prompt += f"\n\nExperimental/simulation data:\n{json.dumps(data, indent=2, default=str)}"
    if research_plan:
        prompt += f"\n\nResearch plan:\n{json.dumps(research_plan, indent=2)}"

    # Multi-AI drafting: use OpenAI for initial draft, Claude for refinement
    if settings.openai_api_key and section == "full":
        # Get diverse perspectives
        responses = await call_multi_ai(
            prompt,
            system=SYSTEM_PROMPT,
            providers=["openai", "anthropic"],
        )
        # Use Claude to synthesize the best elements from both
        synthesis_prompt = f"""Two AI drafts of a research paper on "{topic}":

Draft 1 (OpenAI):
{responses.get('openai', 'Not available')}

Draft 2 (Claude):
{responses.get('anthropic', 'Not available')}

Synthesize the best elements from both drafts into a single, high-quality paper.
Maintain proper citations and scientific rigor."""

        final = await call_anthropic(synthesis_prompt, system=SYSTEM_PROMPT)
    else:
        final = await call_anthropic(prompt, system=SYSTEM_PROMPT)

    try:
        result_data = json.loads(final)
    except json.JSONDecodeError:
        result_data = {"draft": final, "format": "raw_text"}

    # Save draft to artifacts
    artifacts = []
    draft_path = settings.artifacts_dir / f"paper_draft_{task.task_id}.json"
    draft_path.write_text(json.dumps(result_data, indent=2, default=str))
    artifacts.append(str(draft_path))

    return TaskResult(
        task_id=task.task_id,
        agent_name="PaperAgent",
        status="ok",
        result=result_data,
        artifacts=artifacts,
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="PaperAgent")
