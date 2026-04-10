"""Claude Code sub-agent integration.

Spawns Claude Code CLI as a subprocess to handle code-intensive tasks
(e.g., firmware analysis, data processing scripts, visualization code)
within a campaign step.

Requires the ``claude`` CLI to be installed and accessible on PATH.
Streams output via DRVP events for real-time visibility.

ECC Integration:
    When ``skill`` is specified, the agent loads the corresponding
    Everything Claude Code (ECC) skill from ``.claude/skills/`` and
    prepends its content to the system prompt, giving the sub-agent
    domain-specific patterns and best practices for the task.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

__all__ = [
    "ClaudeCodeAgent",
    "ClaudeCodeResult",
    "load_ecc_skill",
    "list_ecc_skills",
]

logger = logging.getLogger("oas.subagents.claude_code")

# ---------------------------------------------------------------------------
# ECC Skill helpers
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk up from this file to find the workspace root.

    The workspace root is identified by having BOTH pyproject.toml and a
    .claude/ directory (to distinguish from member packages like core/).
    Falls back to pyproject.toml-only match, preferring the highest ancestor.
    """
    cur = Path(__file__).resolve().parent
    candidates: list[Path] = []
    for _ in range(10):
        if (cur / "pyproject.toml").exists():
            # Prefer root that has .claude/ directory
            if (cur / ".claude").is_dir():
                return cur
            candidates.append(cur)
        cur = cur.parent
    # Fall back to highest pyproject.toml ancestor
    return candidates[-1] if candidates else Path.cwd()


_PROJECT_ROOT = _find_project_root()
_ECC_SKILLS_DIR = _PROJECT_ROOT / ".claude" / "skills"
_ECC_AGENTS_DIR = _PROJECT_ROOT / ".claude" / "agents"


def load_ecc_skill(skill_name: str) -> str | None:
    """Load an ECC skill definition by name.

    Returns the SKILL.md content or None if not found.
    """
    skill_path = _ECC_SKILLS_DIR / skill_name / "SKILL.md"
    if skill_path.is_file():
        return skill_path.read_text(encoding="utf-8")
    return None


def load_ecc_agent(agent_name: str) -> str | None:
    """Load an ECC agent definition by name.

    Returns the agent markdown content or None if not found.
    """
    agent_path = _ECC_AGENTS_DIR / f"{agent_name}.md"
    if agent_path.is_file():
        return agent_path.read_text(encoding="utf-8")
    return None


def list_ecc_skills() -> list[str]:
    """Return names of all installed ECC skills."""
    if not _ECC_SKILLS_DIR.is_dir():
        return []
    return sorted(
        d.name for d in _ECC_SKILLS_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def list_ecc_agents() -> list[str]:
    """Return names of all installed ECC agents."""
    if not _ECC_AGENTS_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in _ECC_AGENTS_DIR.glob("*.md")
    )


# Map DarkLab task types to relevant ECC skills for auto-enrichment
TASK_SKILL_MAP: dict[str, list[str]] = {
    "RESEARCH": ["deep-research", "search-first"],
    "LITERATURE": ["deep-research"],
    "SIMULATE": ["python-patterns", "pytorch-patterns", "benchmark"],
    "ANALYZE": ["python-patterns", "benchmark"],
    "SYNTHESIZE": ["python-patterns"],
    "AUTORESEARCH": ["autonomous-loops", "eval-harness", "pytorch-patterns"],
    "PARAMETER_GOLF": ["benchmark", "cost-aware-llm-pipeline"],
    "DEEP_RESEARCH": ["deep-research", "search-first"],
    "SWARM_RESEARCH": ["deep-research", "agentic-engineering"],
    "DEERFLOW": ["agentic-engineering", "autonomous-agent-harness"],
    "RL_TRAIN": ["pytorch-patterns", "eval-harness"],
    "DEBATE": ["agentic-engineering"],
    "DFT": ["python-patterns"],
    "PAPER_REVIEW": ["deep-research", "verification-loop"],
    "KAIROS": ["darklab-kairos-ops", "darklab-knowledge-wiki"],
    "WIKI_COMPILE": ["darklab-knowledge-wiki", "darklab-memory-ops"],
    "WIKI_LINT": ["darklab-knowledge-wiki"],
    "EVAL_RUN": ["darklab-eval-harness", "benchmark"],
    "PLAN_AUTHOR": ["darklab-plan-authoring", "darklab-model-routing"],
    "MODEL_INSPECT": ["darklab-model-routing"],
    "ORCHESTRATE": ["darklab-plan-authoring", "agentic-engineering"],
    "ANE_RESEARCH": ["deep-research", "darklab-knowledge-wiki"],
    "GEMMA_SWARM": ["agentic-engineering", "darklab-model-routing"],
    "UNIPAT_SWARM": ["agentic-engineering", "python-patterns"],
    "TURBO_SWARM": ["agentic-engineering", "darklab-swarm-ops"],
    "FULL_SWARM": ["darklab-swarm-ops", "darklab-drvp-events"],
}


@dataclass
class ClaudeCodeResult:
    """Result from a Claude Code sub-agent execution."""

    exit_code: int
    output: str
    cost_usd: float | None = None
    session_id: str | None = None
    files_changed: list[str] | None = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "success": self.success,
            "output": self.output,
            "cost_usd": self.cost_usd,
            "session_id": self.session_id,
            "files_changed": self.files_changed,
        }


class ClaudeCodeAgent:
    """Spawns Claude Code CLI as a sub-agent for code tasks.

    Usage::

        agent = ClaudeCodeAgent(working_dir=Path("/path/to/project"))
        result = await agent.run(
            prompt="Analyze the EIT firmware and list all ADC configuration registers",
            request_id="req_123",
            agent_name="experiment",
            device="experiment",
        )
        if result.success:
            print(result.output)

    Environment notes:
        - Strips CLAUDECODE env var to avoid recursion when spawning
        - Uses --print flag for non-interactive output
        - Supports model override and max-turns limit
    """

    def __init__(
        self,
        working_dir: Path | None = None,
        *,
        claude_bin: str = "claude",
        model: str | None = None,
        max_turns: int = 10,
        timeout: float = 300.0,
        allowed_tools: list[str] | None = None,
        skill: str | None = None,
        ecc_agent: str | None = None,
        task_type: str | None = None,
    ):
        self.working_dir = working_dir or Path.cwd()
        self._claude_bin = claude_bin
        self._model = model
        self._max_turns = max_turns
        self._timeout = timeout
        self._allowed_tools = allowed_tools
        self._skill = skill
        self._ecc_agent = ecc_agent
        self._task_type = task_type

    async def run(
        self,
        prompt: str,
        request_id: str = "",
        agent_name: str = "claude_code",
        device: str = "leader",
        *,
        system_prompt: str | None = None,
        skill: str | None = None,
        task_type: str | None = None,
    ) -> ClaudeCodeResult:
        """Execute a prompt via Claude Code CLI.

        Args:
            prompt: The task description for Claude Code
            request_id: DRVP request ID for event correlation
            agent_name: Agent name for DRVP events
            device: Device name for DRVP events
            system_prompt: Optional system prompt override
            skill: ECC skill name to load (overrides constructor)
            task_type: DarkLab task type for auto skill mapping
        """
        # Enrich system prompt with ECC skill context
        system_prompt = self._enrich_with_ecc(
            system_prompt,
            skill=skill or self._skill,
            task_type=task_type or self._task_type,
        )
        cmd = self._build_command(prompt, system_prompt)

        await emit(DRVPEvent(
            event_type=DRVPEventType.TOOL_CALL_STARTED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"tool_name": "claude_code", "prompt": prompt[:200]},
        ))

        # Strip CLAUDECODE env var to prevent recursion
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )

            output = stdout.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

            result = ClaudeCodeResult(
                exit_code=exit_code,
                output=output,
            )

            # Try to extract structured info from JSON output
            result = self._parse_output(result, output)

            await emit(DRVPEvent(
                event_type=DRVPEventType.TOOL_CALL_COMPLETED,
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={
                    "tool_name": "claude_code",
                    "exit_code": exit_code,
                    "output_length": len(output),
                    "cost_usd": result.cost_usd,
                },
            ))

            logger.info(
                "claude_code_completed",
                extra={
                    "exit_code": exit_code,
                    "output_chars": len(output),
                    "cost_usd": result.cost_usd,
                },
            )

            return result

        except asyncio.TimeoutError:
            # Kill the orphaned subprocess to prevent resource leaks
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            await emit(DRVPEvent(
                event_type=DRVPEventType.TOOL_CALL_FAILED,
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={
                    "tool_name": "claude_code",
                    "error": f"Timed out after {self._timeout}s",
                },
            ))
            return ClaudeCodeResult(
                exit_code=124,
                output=f"Claude Code timed out after {self._timeout}s",
            )

        except FileNotFoundError:
            logger.error("claude_code_not_found", extra={"bin": self._claude_bin})
            return ClaudeCodeResult(
                exit_code=127,
                output=f"Claude Code CLI not found: {self._claude_bin}",
            )

        except Exception as e:
            logger.error("claude_code_error", extra={"error": str(e)})
            return ClaudeCodeResult(
                exit_code=1,
                output=f"Error: {e}",
            )

    def _enrich_with_ecc(
        self,
        system_prompt: str | None,
        skill: str | None = None,
        task_type: str | None = None,
    ) -> str | None:
        """Enrich system prompt with ECC skill/agent context.

        Priority: explicit skill > task_type auto-map > ecc_agent > passthrough.
        """
        parts: list[str] = []

        # 1. Load explicit skill
        if skill:
            content = load_ecc_skill(skill)
            if content:
                parts.append(f"# ECC Skill: {skill}\n\n{content}")
                logger.debug("ecc_skill_loaded", extra={"skill": skill})

        # 2. Auto-map from task type
        if not skill and task_type:
            mapped = TASK_SKILL_MAP.get(task_type.upper(), [])
            for sk in mapped[:2]:  # Limit to 2 skills to avoid prompt bloat
                content = load_ecc_skill(sk)
                if content:
                    parts.append(f"# ECC Skill: {sk}\n\n{content}")
                    logger.debug("ecc_skill_auto_mapped", extra={"skill": sk, "task_type": task_type})

        # 3. Load ECC agent persona
        if self._ecc_agent:
            content = load_ecc_agent(self._ecc_agent)
            if content:
                parts.append(f"# ECC Agent: {self._ecc_agent}\n\n{content}")
                logger.debug("ecc_agent_loaded", extra={"agent": self._ecc_agent})

        if not parts:
            return system_prompt

        ecc_context = "\n\n---\n\n".join(parts)
        if system_prompt:
            return f"{system_prompt}\n\n---\n\n{ecc_context}"
        return ecc_context

    def _build_command(self, prompt: str, system_prompt: str | None) -> list[str]:
        """Build the CLI command arguments."""
        cmd = [self._claude_bin, "--print", "--output-format", "text"]

        if self._model:
            cmd.extend(["--model", self._model])

        if self._max_turns:
            cmd.extend(["--max-turns", str(self._max_turns)])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        if self._allowed_tools:
            for tool in self._allowed_tools:
                cmd.extend(["--allowedTools", tool])

        cmd.extend(["--prompt", prompt])
        return cmd

    def _parse_output(self, result: ClaudeCodeResult, output: str) -> ClaudeCodeResult:
        """Try to extract structured data from Claude Code output."""
        # Look for JSON blocks in output
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    if "cost_usd" in data:
                        result.cost_usd = data["cost_usd"]
                    if "session_id" in data:
                        result.session_id = data["session_id"]
                    if "files_changed" in data:
                        result.files_changed = data["files_changed"]
                except json.JSONDecodeError:
                    pass
        return result

    async def check_available(self) -> bool:
        """Check if the Claude Code CLI is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._claude_bin, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError):
            return False
