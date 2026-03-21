"""DarkLab NotebookLM Agent: browser automation for Google NotebookLM.

Invoked by OpenClaw node-host via:
  python3 -m leader.notebooklm '{"task_type":"notebooklm","payload":{...}}'

Requires:
  - Google Chrome installed
  - Chrome profile 'notebooklm-research' at ~/.darklab/browser-profiles/notebooklm-research
  - Profile must be logged into a Google account with NotebookLM access

Uses browser-use (LLM-driven browser automation) for resilient UI interaction.
"""
from __future__ import annotations

import json
from pathlib import Path

import structlog

from shared.models import Task, TaskResult
from shared.config import settings
from shared.audit import log_event
from shared.node_bridge import run_agent

logger = structlog.get_logger("darklab.notebooklm")

PROFILES_DIR = Path(settings.darklab_home) / "browser-profiles"


async def _upload_and_generate(
    sources: list[str],
    notebook_name: str,
    generate: list[str],
) -> dict:
    """Use browser-use to interact with NotebookLM."""
    from browser_use import Agent, Controller, Browser, BrowserConfig
    from langchain_anthropic import ChatAnthropic

    profile_dir = PROFILES_DIR / "notebooklm-research"
    profile_dir.mkdir(parents=True, exist_ok=True)

    browser = Browser(config=BrowserConfig(
        headless=False,  # Requires pre-authenticated Google session
        extra_chromium_args=[f"--user-data-dir={profile_dir}"],
    ))

    controller = Controller()
    downloaded_assets: list[dict] = []

    @controller.action(description="Record a generated asset from NotebookLM")
    def record_asset(asset_type: str, description: str, url: str = "") -> str:
        asset = {"type": asset_type, "description": description, "url": url}
        downloaded_assets.append(asset)
        return f"Recorded asset: {asset_type}"

    source_list = "\n".join(f"  - {s}" for s in sources)
    generate_list = ", ".join(generate)

    task_prompt = (
        f"Go to notebooklm.google.com\n"
        f"Create a new notebook named: {notebook_name}\n"
        f"Upload these source documents:\n{source_list}\n"
        f"Wait for all sources to be processed.\n"
        f"Then generate these outputs: {generate_list}\n"
        f"For each generated output, use the record_asset action with:\n"
        f"  - asset_type: the type (audio_overview, study_guide, etc.)\n"
        f"  - description: brief description of the content\n"
        f"  - url: the URL if available (e.g., audio player URL)\n"
        f"Wait for each generation to complete before proceeding to the next.\n"
        f"Return a summary of all generated outputs."
    )

    agent = Agent(
        task=task_prompt,
        llm=ChatAnthropic(
            model="claude-sonnet-4-6-20260301",
            api_key=settings.anthropic_api_key,
        ),
        browser=browser,
        controller=controller,
        use_vision=True,
        max_steps=30,
    )

    notebook_url = ""
    summary = ""

    try:
        result = await agent.run()
        summary = result.final_result() if hasattr(result, "final_result") else str(result)
        # Try to extract notebook URL from the browser's current page
        try:
            page = await browser.get_current_page()
            if page and "notebooklm.google.com" in (page.url or ""):
                notebook_url = page.url
        except Exception:
            pass
    except Exception as e:
        logger.error(f"NotebookLM browser automation failed: {e}")
        summary = f"Browser automation error: {e}"
    finally:
        await browser.close()

    return {
        "notebook_name": notebook_name,
        "notebook_url": notebook_url,
        "summary": summary,
        "assets": downloaded_assets,
        "source": "notebooklm-browser-use",
    }


async def handle(task: Task) -> TaskResult:
    sources = task.payload.get("sources", [])
    generate = task.payload.get("generate", ["audio_overview"])
    notebook_name = task.payload.get("notebook_name", f"DarkLab Research {task.task_id}")

    if not sources:
        return TaskResult(
            task_id=task.task_id,
            agent_name="NotebookLMAgent",
            status="error",
            result={"error": "No sources provided. Include 'sources' list in payload."},
        )

    # Validate source files exist
    missing = [s for s in sources if not Path(s).exists()]
    if missing:
        return TaskResult(
            task_id=task.task_id,
            agent_name="NotebookLMAgent",
            status="error",
            result={"error": f"Source files not found: {missing}"},
        )

    log_event("notebooklm_start", sources=sources, generate=generate, notebook=notebook_name)

    result_data = await _upload_and_generate(sources, notebook_name, generate)

    # Save result metadata
    artifacts = []
    output_path = settings.artifacts_dir / f"notebooklm_{task.task_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result_data, indent=2, default=str))
    artifacts.append(str(output_path))

    log_event("notebooklm_complete", task_id=task.task_id, assets=len(result_data.get("assets", [])))

    return TaskResult(
        task_id=task.task_id,
        agent_name="NotebookLMAgent",
        status="ok",
        result=result_data,
        artifacts=artifacts,
    )


if __name__ == "__main__":
    run_agent(handle, agent_name="NotebookLMAgent")
