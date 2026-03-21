"""Bridge between OpenClaw node-host system.run and Python agent handlers.

OpenClaw's node-host invokes Python agents via `system.run`:
  python3 -m academic.research '{"task_type":"research","payload":{"text":"..."}}'

This module standardizes the stdin/argv → parse → dispatch → stdout JSON contract.
"""
from __future__ import annotations

import asyncio
import json
import sys
import traceback

import structlog

from shared.models import Task, TaskResult
from shared.audit import log_task, log_result

logger = structlog.get_logger("darklab.bridge")


def run_agent(handler, agent_name: str = "UnknownAgent") -> None:
    """Universal agent entry point for OpenClaw system.run invocation.

    Reads JSON from argv[1] or stdin, calls handler(task), writes JSON result to stdout.
    The handler can be sync or async.
    """
    from shared.logging_setup import setup_logging, request_id_var
    setup_logging()

    try:
        # Read input
        if len(sys.argv) > 1:
            raw = sys.argv[1]
        else:
            raw = sys.stdin.read()

        if not raw.strip():
            _emit_error(agent_name, "empty_input", "No input provided")
            return

        payload = json.loads(raw)
        task = Task(**payload)

        # Bind request ID for structured log context
        request_id_var.set(task.task_id)

        # Audit input
        log_task(task)

        # Dispatch (support both sync and async handlers)
        if asyncio.iscoroutinefunction(handler):
            result = asyncio.run(handler(task))
        else:
            result = handler(task)

        # Audit output
        log_result(result)

        # Emit result to stdout (OpenClaw captures this)
        print(json.dumps(result.model_dump(), default=str))

    except json.JSONDecodeError as e:
        _emit_error(agent_name, "json_parse_error", f"Invalid JSON input: {e}")
    except Exception as e:
        logger.exception("agent_failed", agent_name=agent_name)
        _emit_error(agent_name, "agent_error", f"{type(e).__name__}: {e}")


def _emit_error(agent_name: str, status: str, error_msg: str) -> None:
    result = TaskResult(
        task_id="error",
        agent_name=agent_name,
        status=status,
        result={"error": error_msg},
    )
    print(json.dumps(result.model_dump(), default=str))
