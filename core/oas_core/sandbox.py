"""NemoClaw sandbox manager.

Wraps NemoClaw's blueprint lifecycle for running untrusted agent code
inside an OpenShell sandbox with Landlock + seccomp isolation.

Requires Linux (Ubuntu 22.04+) with k3s installed. On macOS, operations
fall back to a local subprocess with reduced isolation.

Usage::

    manager = SandboxManager()
    sandbox_id = await manager.create("research-task-1")
    result = await manager.run_code(sandbox_id, "print('hello')", timeout=30)
    await manager.destroy("research-task-1")
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["SandboxManager", "SandboxResult", "SANDBOX_AVAILABLE"]

logger = logging.getLogger("oas.sandbox")

_IS_LINUX = platform.system() == "Linux"
_sandbox_checked = False
SANDBOX_AVAILABLE = False


def _check_sandbox_available() -> bool:
    """Lazily check if NemoClaw CLI is available (deferred from import time)."""
    global _sandbox_checked, SANDBOX_AVAILABLE
    if _sandbox_checked:
        return SANDBOX_AVAILABLE
    _sandbox_checked = True
    if not _IS_LINUX:
        return False
    try:
        import subprocess
        result = subprocess.run(
            ["nemoclaw", "--version"], capture_output=True, timeout=5,
        )
        SANDBOX_AVAILABLE = result.returncode == 0
    except Exception:
        SANDBOX_AVAILABLE = False
    return SANDBOX_AVAILABLE


@dataclass
class SandboxResult:
    """Result from running code in a sandbox."""

    status: str  # "ok" | "error" | "timeout" | "blocked"
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
        }


class SandboxManager:
    """Manages NemoClaw sandbox creation, execution, and teardown.

    On Linux with NemoClaw installed: full Landlock + seccomp isolation.
    On macOS (dev): subprocess fallback with basic timeout enforcement.
    """

    def __init__(
        self,
        nemoclaw_bin: str = "nemoclaw",
        policy: str = "openclaw-sandbox",
        work_dir: str | Path | None = None,
    ):
        self.nemoclaw_bin = nemoclaw_bin
        self.default_policy = policy
        self.work_dir = Path(work_dir) if work_dir else Path(tempfile.gettempdir()) / "darklab-sandboxes"
        self._active: dict[str, dict[str, Any]] = {}

    async def create(self, name: str, policy: str | None = None) -> str:
        """Create a new sandbox instance.

        Returns the sandbox ID.
        """
        policy = policy or self.default_policy
        sandbox_dir = self.work_dir / name
        sandbox_dir.mkdir(parents=True, exist_ok=True)

        if _check_sandbox_available():
            proc = await asyncio.create_subprocess_exec(
                self.nemoclaw_bin, "create", name,
                "--policy", policy,
                "--workdir", str(sandbox_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"NemoClaw create failed: {stderr.decode()}")
            sandbox_id = stdout.decode().strip() or name
        else:
            sandbox_id = name
            logger.info("sandbox_fallback_mode", name=name, reason="NemoClaw not available")

        self._active[name] = {
            "id": sandbox_id,
            "policy": policy,
            "dir": str(sandbox_dir),
        }
        logger.info("sandbox_created", name=name, sandbox_id=sandbox_id)
        return sandbox_id

    async def destroy(self, name: str) -> None:
        """Destroy a sandbox and clean up resources."""
        if _check_sandbox_available() and name in self._active:
            proc = await asyncio.create_subprocess_exec(
                self.nemoclaw_bin, "destroy", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        self._active.pop(name, None)
        logger.info("sandbox_destroyed", name=name)

    async def run_code(
        self,
        name: str,
        code: str,
        *,
        language: str = "python",
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Execute code inside a sandbox.

        Args:
            name: Sandbox name (must be created first).
            code: Source code to execute.
            language: Programming language ("python" or "bash").
            timeout: Maximum execution time in seconds.
            env: Extra environment variables.
        """
        import time

        sandbox = self._active.get(name)
        if not sandbox:
            return SandboxResult(status="error", stderr=f"Sandbox '{name}' not found")

        sandbox_dir = Path(sandbox["dir"])
        start = time.monotonic()

        # Write code to temp file
        ext = ".py" if language == "python" else ".sh"
        code_file = sandbox_dir / f"run{ext}"
        code_file.write_text(code)

        cmd: list[str]
        if _check_sandbox_available():
            cmd = [self.nemoclaw_bin, "connect", name, "--", language, str(code_file)]
        else:
            # Fallback: direct subprocess (reduced isolation)
            cmd = [language if language != "python" else "python3", str(code_file)]

        proc = None
        try:
            proc_env = dict(os.environ)
            if env:
                proc_env.update(env)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(sandbox_dir),
                env=proc_env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            elapsed = time.monotonic() - start

            return SandboxResult(
                status="ok" if proc.returncode == 0 else "error",
                stdout=stdout.decode(errors="replace")[:10_000],
                stderr=stderr.decode(errors="replace")[:5_000],
                exit_code=proc.returncode or 0,
                duration_seconds=elapsed,
            )

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            return SandboxResult(
                status="timeout",
                stderr=f"Execution timed out after {timeout}s",
                duration_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return SandboxResult(
                status="error",
                stderr=str(exc),
                duration_seconds=elapsed,
            )

    @property
    def active_sandboxes(self) -> list[str]:
        """List names of active sandboxes."""
        return list(self._active.keys())
