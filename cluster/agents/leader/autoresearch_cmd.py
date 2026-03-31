"""AutoResearch Telegram command handler.

Manages research topics and triggers on-device autoresearch runs.
Topics are stored in ~/.darklab/autoresearch/topics.json.

Governed by the Codex Autoresearch Oath (8 core principles):
  1. Constraint Enables Autonomy — bounded scope, single metric, fixed cost
  2. Humans Set Direction, Agents Execute — user defines goal, agent iterates
  3. Metrics Must Be Mechanical — only measurable outcomes count
  4. Fast Verification Wins — fastest trustworthy check first
  5. One Change Per Iteration — atomic experiments for causality
  6. Git Is Memory — kept/discarded logged in research-results.tsv
  7. Simplicity Is A Tiebreaker — less complexity wins on equal metrics
  8. Honest Limits — stop and say so if unsafe

Usage via Telegram:
  /autoresearch <research question>     — add topic and run immediately
  /autoresearch list                    — show pending/done topics
  /autoresearch run                     — trigger next pending topic
  /autoresearch clear                   — clear completed topics
  /autoresearch oath                    — show the Codex Autoresearch principles
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

import structlog

from shared.models import Task, TaskResult
from shared.config import settings

__all__ = ["handle"]

logger = structlog.get_logger("darklab.autoresearch_cmd")

TOPICS_FILE = Path(settings.darklab_home) / "autoresearch" / "topics.json"
RESULTS_DIR = Path(settings.darklab_home) / "autoresearch" / "results"
RUNNER_SCRIPT = Path(settings.darklab_home) / "autoresearch" / "runner.py"

# Codex Autoresearch skill root — check container-mount and host paths
_CODEX_CANDIDATES = [
    Path(settings.darklab_home) / "codex-autoresearch",
    Path.home() / "darklab" / "codex-autoresearch",
    Path("/app/codex-autoresearch"),
]
CODEX_SKILL_ROOT = next((p for p in _CODEX_CANDIDATES if p.exists()), _CODEX_CANDIDATES[0])

CODEX_OATH = """\
Codex Autoresearch Oath
========================
8 Core Principles governing autonomous research loops.

1. CONSTRAINT ENABLES AUTONOMY
   Bounded scope, single metric, fixed iteration cost.
   Prefer a bounded file set. Prefer a single metric.

2. HUMANS SET DIRECTION, AGENTS EXECUTE
   The user defines the goal. The agent iterates autonomously
   within declared boundaries.

3. METRICS MUST BE MECHANICAL
   If a command cannot decide whether the result improved,
   the loop is not ready.
   Good: test count, coverage %, benchmark throughput, val_bpb
   Bad: "looks better", "feels cleaner", "probably faster"

4. FAST VERIFICATION WINS
   Use the fastest trustworthy check. Slow verification
   destroys iteration speed.

5. ONE CHANGE PER ITERATION
   Atomic experiments create causality.
   If the result changes, the agent knows why.

6. GIT IS MEMORY
   Kept experiments stay in history. Failed experiments are
   rolled back. research-results.tsv records every experiment.

7. SIMPLICITY IS A TIEBREAKER
   Equal metric + less complexity = win.
   Marginal improvement + added complexity = discard.

8. HONEST LIMITS
   If permissions, tooling, flakiness, or missing context
   make the loop unsafe, stop and say so.

Core Loop: Read -> Define metric -> Baseline -> Change -> Verify -> Keep/Discard -> Log -> Repeat
"""


def _load_topics() -> list[dict]:
    if not TOPICS_FILE.exists():
        TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOPICS_FILE.write_text("[]")
        return []
    return json.loads(TOPICS_FILE.read_text())


def _save_topics(topics: list[dict]) -> None:
    TOPICS_FILE.write_text(json.dumps(topics, indent=2))


def _add_topic(query: str, category: str = "telegram") -> dict:
    """Add a new research topic and return it."""
    topics = _load_topics()
    topic_id = str(len(topics) + 1).zfill(3)
    topic = {
        "id": topic_id,
        "query": query,
        "category": category,
        "priority": "high",
        "status": "pending",
    }
    topics.append(topic)
    _save_topics(topics)
    return topic


def _list_topics() -> str:
    """Format topics list for display."""
    topics = _load_topics()
    if not topics:
        return "No topics. Add one with: /autoresearch <your research question>"

    pending = [t for t in topics if t.get("status") != "done"]
    done = [t for t in topics if t.get("status") == "done"]

    lines = []
    if pending:
        lines.append(f"PENDING ({len(pending)}):")
        for t in pending:
            lines.append(f"  [{t['id']}] {t['query'][:80]}")
    if done:
        lines.append(f"\nDONE ({len(done)}):")
        for t in done[-5:]:  # Last 5 completed
            lines.append(f"  [{t['id']}] {t['query'][:60]}...")

    lines.append(f"\nScheduler: every 2 hours (launchd)")
    lines.append(f"LLM: Ollama llama3.1:8b ($0 cost)")
    return "\n".join(lines)


def _clear_done() -> int:
    """Remove completed topics. Returns count removed."""
    topics = _load_topics()
    pending = [t for t in topics if t.get("status") != "done"]
    removed = len(topics) - len(pending)
    _save_topics(pending)
    return removed


def _trigger_run() -> str:
    """Trigger the autoresearch runner as a subprocess."""
    if not RUNNER_SCRIPT.exists():
        return "Runner script not found at " + str(RUNNER_SCRIPT)

    topics = _load_topics()
    pending = [t for t in topics if t.get("status") != "done"]
    if not pending:
        return "No pending topics to run."

    try:
        # Find the venv python
        venv_python = Path.home() / "darklab" / "darklab-installer" / ".venv" / "bin" / "python3"
        if not venv_python.exists():
            venv_python = "python3"

        # Run in background — results will be sent to Telegram by the runner
        subprocess.Popen(
            [str(venv_python), str(RUNNER_SCRIPT)],
            env={
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                "PYTHONPATH": "",
                "DARKLAB_HOME": str(settings.darklab_home),
                "HOME": str(Path.home()),
            },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Running: {pending[0]['query'][:60]}...\nResult will be sent to Telegram."
    except Exception as e:
        return f"Failed to start runner: {e}"


async def handle(task: Task) -> TaskResult:
    """Handle /autoresearch commands from Telegram."""
    args = task.payload.get("query") or task.payload.get("args", "")
    args = args.strip()

    # Subcommands
    if not args or args.lower() == "help":
        codex_installed = CODEX_SKILL_ROOT.exists()
        codex_status = "installed" if codex_installed else "not installed"
        output = (
            "AutoResearch — on-device research via Ollama ($0 cost)\n"
            "================================================\n"
            "Governed by the Codex Autoresearch Oath (8 principles)\n\n"
            "/autoresearch <question>  — add topic & run now\n"
            "/autoresearch list        — show topics\n"
            "/autoresearch run         — trigger next pending\n"
            "/autoresearch clear       — remove completed\n"
            "/autoresearch status      — scheduler status\n"
            "/autoresearch oath        — show the 8 core principles\n\n"
            f"Codex skill: {codex_status}\n"
            f"Loop: Read -> Metric -> Baseline -> Change -> Verify -> Keep/Discard -> Log -> Repeat"
        )
    elif args.lower() == "oath":
        output = CODEX_OATH
    elif args.lower() == "list":
        output = _list_topics()
    elif args.lower() == "clear":
        count = _clear_done()
        output = f"Cleared {count} completed topics."
    elif args.lower() == "run":
        output = _trigger_run()
    elif args.lower() == "status":
        topics = _load_topics()
        pending = len([t for t in topics if t.get("status") != "done"])
        done = len([t for t in topics if t.get("status") == "done"])
        results = list(RESULTS_DIR.glob("*.md")) if RESULTS_DIR.exists() else []
        codex_installed = CODEX_SKILL_ROOT.exists()
        codex_scripts = len(list(CODEX_SKILL_ROOT.glob("scripts/*.py"))) if codex_installed else 0
        output = (
            f"Topics: {pending} pending, {done} done\n"
            f"Results: {len(results)} saved reports\n"
            f"Scheduler: launchd (every 2h)\n"
            f"LLM: Ollama llama3.1:8b (on-device, $0)\n"
            f"Search: DuckDuckGo (no API key)\n"
            f"Codex Oath: {'active' if codex_installed else 'not installed'}"
            + (f" ({codex_scripts} scripts)" if codex_scripts else "")
        )
    else:
        # Treat as a new research question — add and run
        topic = _add_topic(args)
        run_msg = _trigger_run()
        output = f"Added topic [{topic['id']}]: {args[:80]}\n{run_msg}"

    return TaskResult(
        task_id=task.task_id,
        agent_name="AutoResearch",
        status="ok",
        result={"output": output},
    )
