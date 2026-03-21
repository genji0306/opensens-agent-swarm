"""DarkLab Synthesis Agent: merge multi-source research into coherent narratives.

Invoked by OpenClaw node-host via:
  python3 -m leader.synthesis '{"task_type":"synthesize","payload":{...}}'

Combines research findings, simulation results, and data analyses from
Academic and Experiment agents into publication-ready narratives.
"""
from __future__ import annotations

import hashlib
import json

from shared.models import Task, TaskResult
from shared.llm_client import call_anthropic
from shared.config import settings
from shared.audit import log_event
from shared.node_bridge import run_agent

SYSTEM_PROMPT = """\
You are the DarkLab Synthesis Agent, a scientific writing specialist.
Given multiple data sources (research findings, simulation results, data analyses),
produce a structured synthesis.

Requirements:
- Cross-reference claims across sources, flag inconsistencies
- Maintain scientific accuracy and cite source agents
- Use clear, formal scientific language

Output ONLY valid JSON with this structure:
{
  "executive_summary": "string (300 words max)",
  "key_findings": ["string"],
  "methodology_validation": "string — assess whether methods across sources are consistent",
  "data_consistency": {
    "score": 0.0-1.0,
    "issues": ["string — any discrepancies between sources"]
  },
  "recommendations": ["string — next steps based on findings"],
  "full_narrative": "string (2000+ words, publication-ready)"
}
"""


async def handle(task: Task) -> TaskResult:
    research_results = task.payload.get("research_results", {})
    simulation_data = task.payload.get("simulation_data", {})
    analysis_results = task.payload.get("analysis_results", {})
    original_plan = task.payload.get("original_plan", {})
    output_format = task.payload.get("output_format", "structured_report")

    sources = {
        k: v for k, v in {
            "research_results": research_results,
            "simulation_data": simulation_data,
            "analysis_results": analysis_results,
        }.items() if v
    }

    if not sources:
        return TaskResult(
            task_id=task.task_id,
            agent_name="SynthesisAgent",
            status="error",
            result={"error": "No data sources provided. Include at least one of: "
                    "research_results, simulation_data, analysis_results."},
        )

    prompt_parts = [f"Synthesize the following {len(sources)} data source(s) "
                    f"into a {output_format}.\n"]

    for name, data in sources.items():
        prompt_parts.append(f"### {name}\n{json.dumps(data, indent=2, default=str)}\n")

    if original_plan:
        prompt_parts.append(f"### Original Research Plan\n{json.dumps(original_plan, indent=2)}\n")

    prompt = "\n".join(prompt_parts)

    log_event("synthesis_start", sources=list(sources.keys()), format=output_format)

    response = await call_anthropic(
        prompt,
        system=SYSTEM_PROMPT,
        model="claude-opus-4-6-20260301",
        max_tokens=8192,
    )

    try:
        result_data = json.loads(response)
    except json.JSONDecodeError:
        result_data = {"raw_response": response, "format": "unstructured"}

    result_data["sources_used"] = list(sources.keys())
    result_data["output_format"] = output_format

    # Save artifact
    artifacts = []
    output_path = settings.artifacts_dir / f"synthesis_{task.task_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result_data, indent=2, default=str))
    artifacts.append(str(output_path))

    payload_hash = hashlib.sha256(
        json.dumps(task.payload, sort_keys=True, default=str).encode()
    ).hexdigest()

    log_event("synthesis_complete", task_id=task.task_id, artifact=str(output_path))

    return TaskResult(
        task_id=task.task_id,
        agent_name="SynthesisAgent",
        status="ok",
        result=result_data,
        artifacts=artifacts,
        payload_hash=payload_hash,
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="SynthesisAgent")
