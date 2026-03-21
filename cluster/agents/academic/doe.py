"""DarkLab DOE Agent: Design of Experiments and Bayesian optimization planning.

Generates structured experiment proposals (EIP documents) from research plans.
"""
from __future__ import annotations

import json
import uuid
from shared.models import Task, TaskResult
from shared.schemas import EIP, ExperimentParameter, SafetyCheck
from shared.llm_client import call_anthropic
from shared.node_bridge import run_agent

SYSTEM_PROMPT = """\
You are the DarkLab Design of Experiments (DOE) Agent.
Given a research plan or topic, generate a complete experimental design.

Include:
1. Clear hypothesis to test
2. Experimental method with step-by-step protocol
3. Parameters with ranges and units
4. Expected outputs and measurements
5. Control variables
6. Statistical design (factorial, Taguchi, Bayesian, etc.)
7. Safety considerations

Output valid JSON:
{
  "title": "string",
  "hypothesis": "string",
  "method": "string",
  "parameters": [{"name": "string", "value": null, "unit": "string", "range_min": 0, "range_max": 100}],
  "expected_outputs": ["string"],
  "controls": ["string"],
  "statistical_design": "string",
  "n_experiments": 0,
  "safety_notes": ["string"],
  "estimated_duration": "string"
}
"""


async def handle(task: Task) -> TaskResult:
    topic = task.payload.get("text", task.payload.get("topic", ""))
    research_plan = task.payload.get("research_plan", {})

    if not topic and not research_plan:
        return TaskResult(
            task_id=task.task_id,
            agent_name="DOEAgent",
            status="error",
            result={"error": "No topic or research plan provided."},
        )

    prompt = f"Research topic: {topic}"
    if research_plan:
        prompt += f"\n\nResearch plan context:\n{json.dumps(research_plan, indent=2)}"

    prompt += "\n\nGenerate a complete experimental design."

    response = await call_anthropic(prompt, system=SYSTEM_PROMPT)

    try:
        design = json.loads(response)
    except json.JSONDecodeError:
        design = {"raw_response": response}

    # Create a formal EIP if we got structured output
    eip = None
    if "title" in design and "hypothesis" in design:
        params = [
            ExperimentParameter(**p) for p in design.get("parameters", [])
        ]
        safety = [
            SafetyCheck(check_type="pre_run", description=note)
            for note in design.get("safety_notes", [])
        ]
        eip = EIP(
            eip_id=uuid.uuid4().hex[:12],
            title=design["title"],
            hypothesis=design["hypothesis"],
            method=design.get("method", ""),
            parameters=params,
            expected_outputs=design.get("expected_outputs", []),
            safety_checks=safety,
            created_by="DOEAgent",
        )
        design["eip"] = eip.model_dump(mode="json")

    return TaskResult(
        task_id=task.task_id,
        agent_name="DOEAgent",
        status="ok",
        result=design,
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="DOEAgent")
