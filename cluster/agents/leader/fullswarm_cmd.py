"""Full Swarm command handler — end-to-end research pipeline.

Implements /fullswarm <mode> <topic> — orchestrates the complete 6-phase
research pipeline from discovery through deliverables.

Modes:
  auto   — Fully autonomous overnight run. All phases execute without
           human intervention. Prioritizes local LLM ($0 cost).
           Best for: overnight research, batch topics, cost-sensitive runs.
  semi   — Runs Phase 1-2 (discovery + deep analysis) automatically,
           then pauses with a summary and awaits /fullswarm resume
           before proceeding to experiments and deliverables.
           Best for: guided research where you review findings first.
  manual — Shows the full campaign plan and requires explicit approval
           via Paperclip governance before any execution begins.
           Best for: budget-conscious runs, unfamiliar topics.

Usage via Telegram:
  /fullswarm auto quantum error correction
  /fullswarm semi solid-state battery commercialization
  /fullswarm manual room-temperature superconductors
  /fullswarm status                — check running/completed swarm runs
  /fullswarm resume <run_id>       — resume a paused semi run
  /fullswarm results               — list completed swarm results
"""
from __future__ import annotations

import asyncio
import json
import structlog
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.models import Task, TaskResult
from shared.config import settings

__all__ = ["handle"]

logger = structlog.get_logger("darklab.fullswarm_cmd")

# Persistent state for swarm runs
SWARM_STATE_DIR = Path(settings.darklab_home) / "fullswarm"

# ── Phase Definitions ────────────────────────────────────────────────────────

PHASE_1_DISCOVERY = [
    {"step": 1, "command": "research", "args": "{topic}", "depends_on": []},
    {"step": 2, "command": "literature", "args": "{topic}", "depends_on": []},
    {"step": 3, "command": "perplexity", "args": "{topic} latest advances 2025-2026", "depends_on": []},
    {"step": 4, "command": "deerflow", "args": "{topic}", "depends_on": []},
]

PHASE_2_DEEP_ANALYSIS = [
    {"step": 5, "command": "deepresearch", "args": "{topic}", "depends_on": [1, 2, 3, 4]},
    {"step": 6, "command": "swarmresearch", "args": "{topic}", "depends_on": [1, 2, 3, 4]},
    {"step": 7, "command": "debate", "args": "{topic}", "depends_on": [1, 2, 3, 4]},
]

PHASE_3_EXPERIMENTATION = [
    {"step": 8, "command": "doe", "args": "Design experiments for {topic} based on literature gaps", "depends_on": [5, 6]},
    {"step": 9, "command": "synthetic", "args": "Generate training dataset for {topic}", "depends_on": [8]},
    {"step": 10, "command": "simulate", "args": "Run simulation for {topic}", "depends_on": [8]},
    {"step": 11, "command": "analyze", "args": "Analyze simulation and research results for {topic}", "depends_on": [9, 10]},
]

PHASE_4_OPTIMIZATION = [
    {"step": 12, "command": "parametergolf", "args": "Optimize parameters for {topic}", "depends_on": [11]},
    {"step": 13, "command": "autoresearch", "args": "Train models for {topic} [Codex Oath: mechanical metric, one change per iteration, git is memory, honest limits]", "depends_on": [11]},
]

PHASE_5_DELIVERABLES = [
    {"step": 14, "command": "synthesize", "args": "Synthesize all research findings on {topic}", "depends_on": [5, 6, 7, 11, 12, 13]},
    {"step": 15, "command": "report-data", "args": "Generate publication-quality visualizations for {topic}", "depends_on": [14]},
    {"step": 16, "command": "report", "args": "Generate comprehensive report on {topic}", "depends_on": [14, 15]},
    {"step": 17, "command": "paper", "args": "Write research paper on {topic}", "depends_on": [14, 15]},
]

PHASE_6_EXTRAS = [
    {"step": 18, "command": "notebooklm", "args": "Generate audio overview of {topic} research", "depends_on": [16]},
]

ALL_PHASES = {
    "discovery": PHASE_1_DISCOVERY,
    "deep_analysis": PHASE_2_DEEP_ANALYSIS,
    "experimentation": PHASE_3_EXPERIMENTATION,
    "optimization": PHASE_4_OPTIMIZATION,
    "deliverables": PHASE_5_DELIVERABLES,
    "extras": PHASE_6_EXTRAS,
}

PHASE_NAMES = {
    "discovery": "Phase 1: Discovery",
    "deep_analysis": "Phase 2: Deep Analysis",
    "experimentation": "Phase 3: Experimentation",
    "optimization": "Phase 4: Optimization",
    "deliverables": "Phase 5: Deliverables",
    "extras": "Phase 6: Audio & Extras",
}


def _build_full_plan(topic: str, include_phases: list[str] | None = None) -> list[dict]:
    """Build the complete campaign plan with topic substituted."""
    phases = include_phases or list(ALL_PHASES.keys())
    plan: list[dict] = []
    for phase_key in phases:
        for step_template in ALL_PHASES[phase_key]:
            step = {
                "step": step_template["step"],
                "command": step_template["command"],
                "args": step_template["args"].format(topic=topic),
                "depends_on": list(step_template["depends_on"]),
                "phase": phase_key,
            }
            plan.append(step)
    return plan


def _load_run(run_id: str) -> dict | None:
    """Load a swarm run state from disk."""
    state_file = SWARM_STATE_DIR / f"{run_id}.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return None


def _save_run(run_state: dict) -> None:
    """Persist a swarm run state to disk."""
    SWARM_STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = SWARM_STATE_DIR / f"{run_state['run_id']}.json"
    state_file.write_text(json.dumps(run_state, indent=2, default=str))


def _list_runs() -> list[dict]:
    """List all swarm run states."""
    SWARM_STATE_DIR.mkdir(parents=True, exist_ok=True)
    runs = []
    for f in sorted(SWARM_STATE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            runs.append(json.loads(f.read_text()))
        except Exception:
            pass
    return runs


def _format_status(run_state: dict) -> str:
    """Format a run state for Telegram display."""
    status = run_state.get("status", "unknown")
    topic = run_state.get("topic", "")[:60]
    mode = run_state.get("mode", "?")
    run_id = run_state.get("run_id", "?")

    icon = {"running": "...", "paused": "||", "completed": "OK", "failed": "XX", "planned": "--"}.get(status, "??")

    lines = [
        f"[{icon}] {run_id}",
        f"  Topic: {topic}",
        f"  Mode: {mode} | Status: {status}",
    ]

    completed_steps = run_state.get("completed_steps", [])
    total_steps = run_state.get("total_steps", 18)
    lines.append(f"  Progress: {len(completed_steps)}/{total_steps} steps")

    current_phase = run_state.get("current_phase", "")
    if current_phase:
        lines.append(f"  Phase: {PHASE_NAMES.get(current_phase, current_phase)}")

    if run_state.get("paused_at"):
        lines.append(f"  Paused at: {run_state['paused_at']}")
        lines.append(f"  Resume: /fullswarm resume {run_id}")

    if run_state.get("error"):
        lines.append(f"  Error: {run_state['error'][:100]}")

    duration = run_state.get("duration_seconds")
    if duration:
        mins = int(duration // 60)
        lines.append(f"  Duration: {mins}m")

    return "\n".join(lines)


async def _emit_drvp(event_type: str, request_id: str, payload: dict) -> None:
    """Emit DRVP event (best-effort)."""
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        etype = getattr(DRVPEventType, event_type, DRVPEventType.REQUEST_CREATED)
        await emit(DRVPEvent(
            event_type=etype,
            request_id=request_id,
            agent_name="full-swarm",
            device="leader",
            payload=payload,
        ))
    except Exception:
        pass


async def _execute_plan_via_dispatch(
    plan: list[dict],
    run_state: dict,
    task: Task,
    stop_after_phase: str | None = None,
) -> dict:
    """Execute a campaign plan by calling dispatch.handle() directly.

    Each step is dispatched through the Leader's own handle() function,
    which goes through the full middleware pipeline (budget, audit,
    governance, memory, DRVP). No HTTP self-call needed — we're in-process.
    """
    from leader.dispatch import handle as dispatch_handle

    completed: list[int] = list(run_state.get("completed_steps", []))
    failed: list[int] = list(run_state.get("failed_steps", []))
    step_results: dict[int, Any] = run_state.get("step_results", {})
    # Convert string keys back to int (JSON serialization converts int keys to strings)
    step_results = {int(k): v for k, v in step_results.items()}

    for step in plan:
        step_num = step["step"]
        phase = step.get("phase", "")

        # Skip already completed steps (for resume)
        if step_num in completed:
            continue

        # Check dependencies
        deps = step.get("depends_on", [])
        deps_failed = [d for d in deps if d in failed]
        if deps_failed:
            failed.append(step_num)
            logger.info("step_skipped", step=step_num, deps_failed=deps_failed)
            continue

        deps_pending = [d for d in deps if d not in completed]
        if deps_pending:
            logger.warning("step_deps_pending", step=step_num, pending=deps_pending)
            continue

        # Check if we should pause after a phase
        if stop_after_phase and phase != stop_after_phase and phase:
            prev_phases = list(ALL_PHASES.keys())
            stop_idx = prev_phases.index(stop_after_phase) if stop_after_phase in prev_phases else -1
            curr_idx = prev_phases.index(phase) if phase in prev_phases else -1
            if curr_idx > stop_idx >= 0:
                run_state["status"] = "paused"
                run_state["current_phase"] = phase
                run_state["paused_at"] = datetime.now(timezone.utc).isoformat()
                run_state["completed_steps"] = completed
                run_state["failed_steps"] = failed
                run_state["step_results"] = {str(k): v for k, v in step_results.items()}
                _save_run(run_state)
                return run_state

        # Update current phase
        run_state["current_phase"] = phase
        _save_run(run_state)

        # Emit progress
        await _emit_drvp("CAMPAIGN_STEP_STARTED", task.task_id, {
            "step_number": step_num,
            "total_steps": len(plan),
            "command": step["command"],
            "phase": phase,
        })

        # Execute step by calling dispatch.handle() directly (in-process)
        cmd_text = f"/{step['command']} {step['args']}"
        try:
            step_task = Task(
                task_id=f"{task.task_id}-s{step_num}",
                task_type=task.task_type,
                user_id=task.user_id,
                payload={
                    "text": cmd_text,
                    "source": "fullswarm",
                    "parent_run_id": run_state["run_id"],
                },
                parent_task_id=task.task_id,
            )
            step_result = await asyncio.wait_for(
                dispatch_handle(step_task),
                timeout=600,
            )
            result_dict = step_result.result
            step_results[step_num] = result_dict
            completed.append(step_num)

            await _emit_drvp("CAMPAIGN_STEP_COMPLETED", task.task_id, {
                "step_number": step_num,
                "total_steps": len(plan),
                "command": step["command"],
                "status": "completed",
            })

            logger.info("step_completed", step=step_num, command=step["command"])

        except Exception as exc:
            failed.append(step_num)
            step_results[step_num] = {"error": str(exc)}
            logger.warning("step_failed", step=step_num, command=step["command"], error=str(exc))

            await _emit_drvp("CAMPAIGN_STEP_COMPLETED", task.task_id, {
                "step_number": step_num,
                "total_steps": len(plan),
                "command": step["command"],
                "status": "failed",
                "error": str(exc)[:200],
            })

    run_state["completed_steps"] = completed
    run_state["failed_steps"] = failed
    run_state["step_results"] = {str(k): v for k, v in step_results.items()}

    if failed and not completed:
        run_state["status"] = "failed"
    elif failed:
        run_state["status"] = "partial"
    else:
        run_state["status"] = "completed"

    run_state["finished_at"] = datetime.now(timezone.utc).isoformat()
    run_state["duration_seconds"] = time.time() - run_state.get("started_epoch", time.time())
    _save_run(run_state)
    return run_state


async def _handle_auto(task: Task, topic: str) -> TaskResult:
    """Fully autonomous overnight research — all 6 phases, local LLM priority."""
    run_id = f"swarm-{uuid.uuid4().hex[:8]}"
    plan = _build_full_plan(topic)

    run_state = {
        "run_id": run_id,
        "mode": "auto",
        "topic": topic,
        "status": "running",
        "plan": plan,
        "total_steps": len(plan),
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "current_phase": "discovery",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "started_epoch": time.time(),
        "model_preference": "local",
    }
    _save_run(run_state)

    await _emit_drvp("CAMPAIGN_STEP_STARTED", task.task_id, {
        "total_steps": len(plan),
        "step_number": 0,
        "mode": "auto",
        "topic": topic[:200],
    })

    # Execute full plan
    final_state = await _execute_plan_via_dispatch(plan, run_state, task)

    await _emit_drvp("CAMPAIGN_STEP_COMPLETED", task.task_id, {
        "total_steps": len(plan),
        "step_number": len(plan),
        "status": final_state["status"],
        "completed": len(final_state.get("completed_steps", [])),
        "failed": len(final_state.get("failed_steps", [])),
    })

    output = _format_status(final_state)
    return TaskResult(
        task_id=task.task_id,
        agent_name="full-swarm",
        status="ok",
        result={
            "output": output,
            "run_id": run_id,
            "mode": "auto",
            "status": final_state["status"],
            "completed": len(final_state.get("completed_steps", [])),
            "failed": len(final_state.get("failed_steps", [])),
            "total": len(plan),
            "duration_seconds": final_state.get("duration_seconds"),
        },
    )


async def _handle_semi(task: Task, topic: str) -> TaskResult:
    """Semi-manual mode — runs discovery + deep analysis, pauses for review."""
    run_id = f"swarm-{uuid.uuid4().hex[:8]}"
    plan = _build_full_plan(topic)

    run_state = {
        "run_id": run_id,
        "mode": "semi",
        "topic": topic,
        "status": "running",
        "plan": plan,
        "total_steps": len(plan),
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "current_phase": "discovery",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "started_epoch": time.time(),
        "model_preference": "local",
    }
    _save_run(run_state)

    await _emit_drvp("CAMPAIGN_STEP_STARTED", task.task_id, {
        "total_steps": len(plan),
        "step_number": 0,
        "mode": "semi",
        "topic": topic[:200],
    })

    # Execute only phases 1-2, pause before phase 3
    final_state = await _execute_plan_via_dispatch(
        plan, run_state, task, stop_after_phase="deep_analysis",
    )

    n_completed = len(final_state.get("completed_steps", []))
    is_paused = final_state.get("status") == "paused"

    if is_paused:
        output = (
            f"SWARM PAUSED after Phase 2 (Deep Analysis)\n"
            f"Run ID: {run_id}\n"
            f"Steps completed: {n_completed}/{len(plan)}\n"
            f"Topic: {topic[:80]}\n\n"
            f"Review findings, then resume:\n"
            f"  /fullswarm resume {run_id}\n\n"
            f"Or check results so far:\n"
            f"  /results"
        )
    else:
        output = _format_status(final_state)

    return TaskResult(
        task_id=task.task_id,
        agent_name="full-swarm",
        status="ok",
        result={
            "output": output,
            "run_id": run_id,
            "mode": "semi",
            "status": final_state["status"],
            "completed": n_completed,
            "total": len(plan),
            "paused": is_paused,
        },
    )


async def _handle_manual(task: Task, topic: str) -> TaskResult:
    """Manual mode — shows plan and requires governance approval."""
    run_id = f"swarm-{uuid.uuid4().hex[:8]}"
    plan = _build_full_plan(topic)

    run_state = {
        "run_id": run_id,
        "mode": "manual",
        "topic": topic,
        "status": "planned",
        "plan": plan,
        "total_steps": len(plan),
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "current_phase": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_preference": "local",
    }
    _save_run(run_state)

    # Format plan for display
    lines = [
        f"FULL SWARM PLAN: {topic[:80]}",
        f"Run ID: {run_id}",
        f"Steps: {len(plan)}",
        f"LLM: Local Ollama (qwen3:8b, $0 cost)",
        "",
    ]

    current_phase = ""
    for step in plan:
        phase = step.get("phase", "")
        if phase != current_phase:
            current_phase = phase
            lines.append(f"\n--- {PHASE_NAMES.get(phase, phase)} ---")

        deps_str = f" (after {step['depends_on']})" if step["depends_on"] else ""
        lines.append(f"  [{step['step']:2d}] /{step['command']} {step['args'][:60]}{deps_str}")

    lines.append(f"\nTo execute: /fullswarm resume {run_id}")
    lines.append("To cancel:  delete plan and move on")

    output = "\n".join(lines)

    # Create governance issue for approval
    try:
        from oas_core.adapters.paperclip import PaperclipClient
        if settings.paperclip_url and settings.paperclip_api_key:
            client = PaperclipClient(
                base_url=settings.paperclip_url,
                api_key=settings.paperclip_api_key,
                company_id=settings.paperclip_company_id,
            )
            await client.create_issue(
                title=f"Full Swarm: {topic[:80]}",
                description=f"Manual approval required for {len(plan)}-step campaign.\nRun ID: {run_id}",
                agent_id=settings.paperclip_agent_id,
                priority="high",
            )
    except Exception:
        pass

    return TaskResult(
        task_id=task.task_id,
        agent_name="full-swarm",
        status="ok",
        result={
            "output": output,
            "run_id": run_id,
            "mode": "manual",
            "status": "planned",
            "total": len(plan),
            "plan_summary": [
                {"step": s["step"], "command": s["command"], "phase": s.get("phase", "")}
                for s in plan
            ],
        },
    )


async def _handle_resume(task: Task, run_id: str) -> TaskResult:
    """Resume a paused or planned swarm run."""
    run_state = _load_run(run_id)
    if not run_state:
        return TaskResult(
            task_id=task.task_id,
            agent_name="full-swarm",
            status="error",
            result={"error": f"Run {run_id} not found. Use /fullswarm status to list runs."},
        )

    if run_state["status"] not in ("paused", "planned"):
        return TaskResult(
            task_id=task.task_id,
            agent_name="full-swarm",
            status="error",
            result={"error": f"Run {run_id} is {run_state['status']}, not resumable."},
        )

    run_state["status"] = "running"
    run_state["resumed_at"] = datetime.now(timezone.utc).isoformat()
    if not run_state.get("started_epoch"):
        run_state["started_epoch"] = time.time()
    _save_run(run_state)

    topic = run_state["topic"]
    plan = run_state["plan"]

    await _emit_drvp("CAMPAIGN_STEP_STARTED", task.task_id, {
        "total_steps": len(plan),
        "step_number": len(run_state.get("completed_steps", [])),
        "mode": f"{run_state['mode']}-resumed",
        "topic": topic[:200],
    })

    # Continue execution from where we left off
    final_state = await _execute_plan_via_dispatch(plan, run_state, task)

    output = _format_status(final_state)
    return TaskResult(
        task_id=task.task_id,
        agent_name="full-swarm",
        status="ok",
        result={
            "output": output,
            "run_id": run_id,
            "mode": run_state["mode"],
            "status": final_state["status"],
            "completed": len(final_state.get("completed_steps", [])),
            "total": len(plan),
        },
    )


async def _handle_status(task: Task) -> TaskResult:
    """List all swarm runs and their status."""
    runs = _list_runs()
    if not runs:
        output = "No swarm runs found. Start one with:\n  /fullswarm auto <topic>\n  /fullswarm semi <topic>\n  /fullswarm manual <topic>"
    else:
        lines = [f"FULL SWARM RUNS ({len(runs)} total)", ""]
        for run in runs[:10]:  # Last 10
            lines.append(_format_status(run))
            lines.append("")
        output = "\n".join(lines)

    return TaskResult(
        task_id=task.task_id,
        agent_name="full-swarm",
        status="ok",
        result={"output": output, "runs": len(runs)},
    )


async def _handle_results(task: Task) -> TaskResult:
    """List completed swarm runs with summary."""
    runs = _list_runs()
    completed = [r for r in runs if r.get("status") in ("completed", "partial")]

    if not completed:
        output = "No completed swarm runs. Start one with /fullswarm auto <topic>"
    else:
        lines = [f"COMPLETED SWARM RUNS ({len(completed)})", ""]
        for run in completed[:10]:
            lines.append(_format_status(run))
            lines.append("")
        output = "\n".join(lines)

    return TaskResult(
        task_id=task.task_id,
        agent_name="full-swarm",
        status="ok",
        result={"output": output, "completed": len(completed)},
    )


async def handle(task: Task) -> TaskResult:
    """Handle /fullswarm commands.

    Subcommands:
      /fullswarm auto <topic>        — fully autonomous overnight run
      /fullswarm semi <topic>        — auto discovery+analysis, pause before experiments
      /fullswarm manual <topic>      — show plan, require approval before execution
      /fullswarm resume <run_id>     — resume a paused/planned run
      /fullswarm status              — list all runs
      /fullswarm results             — list completed runs
      /fullswarm help                — show usage
    """
    text = (task.payload.get("text") or task.payload.get("args") or "").strip()

    if not text or text.lower() == "help":
        output = (
            "Full Swarm Research Pipeline\n"
            "============================\n"
            "Run ALL DarkLab agents on a topic in 6 phases.\n"
            "Prioritizes local LLM (Ollama qwen3:8b) for $0 cost.\n\n"
            "MODES:\n"
            "  /fullswarm auto <topic>\n"
            "    Fully autonomous. Runs all 18 steps overnight.\n"
            "    Best for batch research, overnight runs.\n\n"
            "  /fullswarm semi <topic>\n"
            "    Runs discovery + deep analysis (7 steps), then\n"
            "    pauses for you to review before experiments.\n"
            "    Resume with: /fullswarm resume <run_id>\n\n"
            "  /fullswarm manual <topic>\n"
            "    Shows the full 18-step plan. No execution until\n"
            "    you approve with: /fullswarm resume <run_id>\n\n"
            "MANAGEMENT:\n"
            "  /fullswarm status   — list all runs\n"
            "  /fullswarm results  — completed runs only\n"
            "  /fullswarm resume <id> — continue a paused run\n\n"
            "PHASES:\n"
            "  1. Discovery     — /research /literature /perplexity /deerflow\n"
            "  2. Deep Analysis — /deepresearch /swarmresearch /debate\n"
            "  3. Experiments   — /doe /synthetic /simulate /analyze\n"
            "  4. Optimization  — /parametergolf /autoresearch\n"
            "  5. Deliverables  — /synthesize /report-data /report /paper\n"
            "  6. Extras        — /notebooklm\n\n"
            "Cost: ~$0 with local LLM (Ollama)\n"
            "Duration: 2-6 hours (auto mode)"
        )
        return TaskResult(
            task_id=task.task_id,
            agent_name="full-swarm",
            status="ok",
            result={"output": output},
        )

    # Parse subcommand
    parts = text.split(None, 1)
    subcommand = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    if subcommand == "status":
        return await _handle_status(task)

    if subcommand == "results":
        return await _handle_results(task)

    if subcommand == "resume":
        if not args:
            return TaskResult(
                task_id=task.task_id,
                agent_name="full-swarm",
                status="error",
                result={"error": "Usage: /fullswarm resume <run_id>"},
            )
        return await _handle_resume(task, args.strip())

    if subcommand == "auto":
        if not args:
            return TaskResult(
                task_id=task.task_id,
                agent_name="full-swarm",
                status="error",
                result={"error": "Usage: /fullswarm auto <research topic>"},
            )
        return await _handle_auto(task, args)

    if subcommand == "semi":
        if not args:
            return TaskResult(
                task_id=task.task_id,
                agent_name="full-swarm",
                status="error",
                result={"error": "Usage: /fullswarm semi <research topic>"},
            )
        return await _handle_semi(task, args)

    if subcommand == "manual":
        if not args:
            return TaskResult(
                task_id=task.task_id,
                agent_name="full-swarm",
                status="error",
                result={"error": "Usage: /fullswarm manual <research topic>"},
            )
        return await _handle_manual(task, args)

    # If no recognized subcommand, treat the entire text as topic with auto mode
    # This allows: /fullswarm quantum error correction (defaults to auto)
    return await _handle_auto(task, text)
