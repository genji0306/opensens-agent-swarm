"""Agency-agents persona loader.

Reads agent persona markdown files from ``frameworks/agency-agents/``
and converts them into system-prompt extensions layered on top of each
DarkLab agent's existing prompt.

Persona files use YAML frontmatter (``---`` delimited) followed by
markdown sections. The loader strips frontmatter and returns the
markdown body as a system-prompt extension.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

__all__ = ["load_persona", "parse_persona_file", "ROLE_PERSONA_MAP", "PersonaMeta"]

logger = logging.getLogger("oas.persona")

# Default personas directory (relative to OAS root)
_DEFAULT_PERSONAS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "frameworks"
    / "agency-agents"
)

# Maps DarkLab agent names → category/filename within agency-agents/
# Uses closest available persona for each DarkLab role.
ROLE_PERSONA_MAP: dict[str, str] = {
    # Academic device agents
    "academic.research": "engineering/engineering-ai-engineer.md",
    "academic.literature": "engineering/engineering-technical-writer.md",
    "academic.doe": "engineering/engineering-data-engineer.md",
    "academic.paper": "engineering/engineering-technical-writer.md",
    "academic.perplexity": "engineering/engineering-ai-engineer.md",
    "academic.browser_agent": "engineering/engineering-frontend-developer.md",
    # Experiment device agents
    "experiment.simulation": "engineering/engineering-ai-engineer.md",
    "experiment.analysis": "engineering/engineering-data-engineer.md",
    "experiment.synthetic": "engineering/engineering-ai-engineer.md",
    "experiment.report_data": "support/support-analytics-reporter.md",
    "experiment.autoresearch": "engineering/engineering-ai-engineer.md",
    # Leader device agents
    "leader.dispatch": "project-management/project-manager-senior.md",
    "leader.synthesis": "support/support-executive-summary-generator.md",
    "leader.media_gen": "design/design-visual-storyteller.md",
    "leader.notebooklm": "engineering/engineering-technical-writer.md",
}


class PersonaMeta:
    """Parsed metadata from a persona file's YAML frontmatter."""

    def __init__(
        self,
        name: str = "",
        description: str = "",
        color: str = "",
        emoji: str = "",
        vibe: str = "",
        extra: dict[str, Any] | None = None,
    ):
        self.name = name
        self.description = description
        self.color = color
        self.emoji = emoji
        self.vibe = vibe
        self.extra = extra or {}

    def __repr__(self) -> str:
        return f"PersonaMeta(name={self.name!r}, emoji={self.emoji!r})"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML frontmatter from markdown body.

    Returns (frontmatter_dict, body_text). If no frontmatter found,
    returns ({}, full_text).
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    fm_block = parts[1].strip()
    body = parts[2].strip()

    # Simple key: value parsing (avoids PyYAML dependency)
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")

    return fm, body


def parse_persona_file(filepath: Path) -> tuple[PersonaMeta, str]:
    """Parse a persona markdown file into metadata + body.

    Args:
        filepath: Path to the ``.md`` persona file

    Returns:
        Tuple of (PersonaMeta, markdown_body)

    Raises:
        FileNotFoundError: If the persona file doesn't exist
    """
    text = filepath.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)

    meta = PersonaMeta(
        name=fm.get("name", filepath.stem),
        description=fm.get("description", ""),
        color=fm.get("color", ""),
        emoji=fm.get("emoji", ""),
        vibe=fm.get("vibe", ""),
        extra={k: v for k, v in fm.items() if k not in ("name", "description", "color", "emoji", "vibe")},
    )

    return meta, body


def load_persona(
    agent_name: str,
    personas_dir: Path | None = None,
) -> str:
    """Load and return the system-prompt extension for *agent_name*.

    Looks up the agent name in ``ROLE_PERSONA_MAP``, reads the
    corresponding persona file, and returns the markdown body
    (without frontmatter) suitable for inclusion in an LLM system prompt.

    Args:
        agent_name: DarkLab agent identifier (e.g. ``"academic.research"``)
        personas_dir: Override directory for persona files

    Returns:
        Markdown body string, or empty string if no persona found
    """
    base_dir = personas_dir or _DEFAULT_PERSONAS_DIR

    rel_path = ROLE_PERSONA_MAP.get(agent_name)
    if not rel_path:
        logger.debug("no_persona_mapping", extra={"agent": agent_name})
        return ""

    filepath = base_dir / rel_path
    if not filepath.exists():
        logger.warning(
            "persona_file_missing",
            extra={"agent": agent_name, "path": str(filepath)},
        )
        return ""

    try:
        _meta, body = parse_persona_file(filepath)
        logger.info(
            "persona_loaded",
            extra={"agent": agent_name, "persona": _meta.name, "chars": len(body)},
        )
        return body
    except Exception as e:
        logger.warning("persona_load_failed", extra={"agent": agent_name, "error": str(e)})
        return ""
