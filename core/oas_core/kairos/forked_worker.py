"""ForkedWorker — subprocess isolation for KAIROS background tasks.

autoDream and RL curation run inside forked subprocesses so that a
crash or memory leak in the background task cannot corrupt the main
Leader orchestrator. The worker captures stdout/stderr and returns a
structured result.

On macOS the worker is launched via ``asyncio.create_subprocess_exec``
with ``os.nice(19)`` applied inside the child (idle priority).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["ForkedWorker", "WorkerResult"]

logger = logging.getLogger("oas.kairos.forked_worker")


@dataclass(frozen=True)
class WorkerResult:
    """Structured result from a forked worker invocation."""

    success: bool
    output: dict[str, Any]
    return_code: int
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "return_code": self.return_code,
            "output": self.output,
            "stderr_length": len(self.stderr),
        }


class ForkedWorker:
    """Run a Python callable in an isolated subprocess.

    The callable must accept a single ``dict`` argument and return a
    ``dict`` result. Communication is via a temp file (JSON in, JSON out)
    to avoid pipe buffer limits on large payloads.
    """

    def __init__(
        self,
        *,
        timeout_s: float = 300.0,
        nice_level: int = 19,
        python_executable: str | None = None,
    ) -> None:
        self._timeout = timeout_s
        self._nice = nice_level
        self._python = python_executable or sys.executable

    async def run(
        self,
        module: str,
        function: str,
        payload: dict[str, Any],
    ) -> WorkerResult:
        """Fork a subprocess to run ``module.function(payload)``.

        The subprocess loads ``module``, calls ``function(payload)``,
        and writes the return dict to a temp file. Parent reads the
        result after the child exits.
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="kairos-"
        ) as inp:
            json.dump(payload, inp)
            input_path = inp.name

        output_path = input_path + ".out"

        # Inline script that the child process runs
        script = (
            f"import json, os, sys; "
            f"os.nice({self._nice}); "
            f"inp = json.load(open({input_path!r})); "
            f"from {module} import {function}; "
            f"result = {function}(inp); "
            f"json.dump(result or {{}}, open({output_path!r}, 'w'))"
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                self._python, "-c", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
            return_code = proc.returncode or 0
            stderr = stderr_bytes.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            logger.warning("forked_worker_timeout", extra={
                "module": module, "function": function, "timeout": self._timeout
            })
            try:
                proc.kill()
            except Exception:
                pass
            return WorkerResult(
                success=False,
                output={"error": f"timeout after {self._timeout}s"},
                return_code=-1,
                stderr="timeout",
            )
        except Exception as exc:
            return WorkerResult(
                success=False,
                output={"error": str(exc)},
                return_code=-1,
                stderr=str(exc),
            )
        finally:
            for p in (input_path, output_path):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass

        if return_code != 0:
            return WorkerResult(
                success=False,
                output={"error": stderr[:500]},
                return_code=return_code,
                stderr=stderr[:2000],
            )

        try:
            result_data = json.loads(Path(output_path).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            result_data = {"raw_stderr": stderr[:500]}

        return WorkerResult(
            success=True,
            output=result_data,
            return_code=return_code,
        )
