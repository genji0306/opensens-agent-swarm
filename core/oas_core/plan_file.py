"""Plan-file parser for YAML-frontmatter + markdown orchestration plans."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]
    YAML_AVAILABLE = False

try:
    from oas_core.schemas.campaign import (
        CampaignSchema,
        CampaignStatus,
        CampaignStepSchema,
    )
    _SCHEMAS_AVAILABLE = True
except ImportError:  # pragma: no cover - schemas not deployed on all nodes
    _SCHEMAS_AVAILABLE = False

__all__ = ["PlanFile", "YAML_AVAILABLE"]

logger = logging.getLogger("oas.plan_file")


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+)\.)\s+(.*)$")
_EMPHASIS_RE = re.compile(r"(\*\*|__|`)")
_SECTION_ALIASES = {
    "objective": "objective",
    "steps": "steps",
    "constraints": "constraints",
    "success criteria": "success_criteria",
    "success criteria ": "success_criteria",
    "success_criteria": "success_criteria",
}
_KNOWN_COMMANDS = {
    "research",
    "literature",
    "doe",
    "paper",
    "perplexity",
    "simulate",
    "analyze",
    "synthetic",
    "report-data",
    "autoresearch",
    "deerflow",
    "synthesize",
    "deepresearch",
    "swarmresearch",
    "debate",
}
_COMMAND_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("swarmresearch", ("swarm research", "triangulat", "cross-validate", "cross validate")),
    ("deepresearch", ("deep research",)),
    ("deerflow", ("deerflow",)),
    ("perplexity", ("perplexity",)),
    ("literature", ("literature", "peer-reviewed", "peer reviewed", "citations", "survey")),
    ("doe", ("design of experiments", "doe", "experiment design", "factorial", "sweep plan")),
    ("simulate", ("simulate", "simulation", "run dft", "dft run", "benchmark model")),
    ("analyze", ("analysis", "analyze", "post-process", "post process")),
    ("report-data", ("report data", "metrics dashboard", "metrics table", "results table")),
    ("paper", ("paper draft", "manuscript", "paper writeup", "paper write-up")),
    ("autoresearch", ("autoresearch", "auto research")),
    ("synthesize", ("synthesis", "synthesize", "merge results", "combine findings", "summary report", "write report")),
    ("debate", ("debate", "counterargument", "counter-argument")),
]
_INTENT_FALLBACKS: dict[str, str] = {
    "research": "research",
    "implement": "research",
    "simulate": "simulate",
    "synthesize": "synthesize",
    "debate": "debate",
}


class PlanFile(BaseModel):
    """Parsed orchestration plan file."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    intent: Literal["research", "implement", "simulate", "synthesize", "debate"]
    mode: Literal["sequential", "parallel", "hybrid"] = "sequential"
    budget_usd: float = Field(default=0.0, ge=0.0)
    sonnet_cap_usd: float = Field(
        default=0.0, ge=0.0,
        description="Per-mission hard ceiling for automatic Sonnet escalation ($).",
    )
    opus_allowed: bool = Field(
        default=False,
        description="If True, Leader may REQUEST Opus; Boss still approves each call.",
    )
    confidential: bool = Field(
        default=False,
        description="If True, blocks all cloud tiers at router level.",
    )
    tier: Literal["default", "boost", "local_only"] = "default"
    approvals_required: bool = False
    readiness_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    research_backends: list[str] = Field(default_factory=list)
    synthesis: Literal["default", "uniscientist", "none"] = "default"
    allow_kairos_followup: bool = True
    deadline: datetime | None = None
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    tags: list[str] = Field(default_factory=list)
    objective: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    source_path: str | None = None
    source_sha256: str = ""

    @classmethod
    def from_markdown(
        cls,
        text: str,
        *,
        source_path: str | Path | None = None,
    ) -> "PlanFile":
        """Parse a plan file from markdown text."""
        if not YAML_AVAILABLE:
            raise RuntimeError("pyyaml is required to parse plan files (pip install pyyaml)")
        normalized = text.replace("\r\n", "\n")
        frontmatter_text, body = _split_frontmatter(normalized)
        data = yaml.safe_load(frontmatter_text) or {}
        if not isinstance(data, dict):
            raise ValueError("Plan frontmatter must be a YAML mapping")

        sections = _extract_sections(body)
        objective = _normalize_block_text(sections.get("objective", ""))
        steps = _parse_markdown_list(sections.get("steps", ""))
        constraints = _parse_markdown_list(sections.get("constraints", ""))
        success_criteria = _parse_markdown_list(sections.get("success_criteria", ""))

        if not objective:
            raise ValueError("Plan file is missing an Objective section")
        if not steps:
            raise ValueError("Plan file is missing a Steps section")

        payload = {
            **data,
            "objective": objective,
            "steps": steps,
            "constraints": constraints,
            "success_criteria": success_criteria,
            "source_path": str(source_path) if source_path is not None else None,
            "source_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        }
        return cls.model_validate(payload)

    @classmethod
    def from_path(cls, path: str | Path) -> "PlanFile":
        """Parse a plan file directly from disk."""
        plan_path = Path(path).expanduser().resolve()
        return cls.from_markdown(
            plan_path.read_text(encoding="utf-8"),
            source_path=plan_path,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "PlanFile":
        """Alias for ``from_path`` — reads and parses a plan file from disk."""
        return cls.from_path(path)

    def to_campaign_steps(self) -> list[dict[str, Any]]:
        """Convert steps into the format CampaignEngine expects.

        Returns a list of dicts with keys: step, command, args, depends_on.
        The ``command`` is inferred from step text using heuristics and
        ``intent`` as the fallback command. Does NOT require
        ``oas_core.schemas`` — works on any node.
        """
        result: list[dict[str, Any]] = []
        total = len(self.steps)
        for index, raw_step in enumerate(self.steps, start=1):
            explicit_command, explicit_args = _extract_explicit_command(raw_step)
            label, detail = _split_step_text(explicit_args or raw_step)
            command = explicit_command or _infer_step_command(
                label=label,
                detail=detail,
                intent=self.intent,
                is_last=index == total,
            )
            args = detail or label or _normalize_inline_text(raw_step)
            depends_on = [index - 1] if index > 1 else []
            result.append({
                "step": index,
                "command": command,
                "args": args,
                "depends_on": depends_on,
            })
        return result

    def to_campaign(self) -> "CampaignSchema":
        """Convert this plan file into a campaign schema.

        Requires ``oas_core.schemas.campaign`` — raises ImportError if
        the schemas module is not available on this node.
        """
        if not _SCHEMAS_AVAILABLE:
            raise ImportError(
                "oas_core.schemas.campaign not available; use to_campaign_steps() instead"
            )
        campaign_steps: list["CampaignStepSchema"] = []
        total_steps = len(self.steps)

        for index, raw_step in enumerate(self.steps, start=1):
            explicit_command, explicit_args = _extract_explicit_command(raw_step)
            label, detail = _split_step_text(explicit_args or raw_step)
            command = explicit_command or _infer_step_command(
                label=label,
                detail=detail,
                intent=self.intent,
                is_last=index == total_steps,
            )
            args = detail or label or _normalize_inline_text(raw_step)
            command_source = "explicit" if explicit_command else "heuristic"
            if not explicit_command and command == _INTENT_FALLBACKS.get(self.intent, "research"):
                command_source = "intent_fallback"

            campaign_steps.append(
                CampaignStepSchema(
                    step=index,
                    command=command,
                    args=args,
                    depends_on=[index - 1] if index > 1 else [],
                    metadata={
                        "raw_text": raw_step,
                        "label": label,
                        "command_source": command_source,
                        "plan_intent": self.intent,
                    },
                )
            )

        plan_meta = {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
        }

        metadata = {
            "intent": self.intent,
            "mode": self.mode,
            "budget_usd": self.budget_usd,
            "sonnet_cap_usd": self.sonnet_cap_usd,
            "opus_allowed": self.opus_allowed,
            "confidential": self.confidential,
            "tier": self.tier,
            "approvals_required": self.approvals_required,
            "readiness_threshold": self.readiness_threshold,
            "research_backends": list(self.research_backends),
            "synthesis": self.synthesis,
            "allow_kairos_followup": self.allow_kairos_followup,
            "priority": self.priority,
            "tags": list(self.tags),
            "constraints": list(self.constraints),
            "success_criteria": list(self.success_criteria),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "plan_file": plan_meta,
        }

        return CampaignSchema(
            campaign_id=self.id,
            request_id=self.id,
            title=self.title,
            objective=self.objective,
            status=(
                CampaignStatus.PENDING_APPROVAL
                if self.approvals_required
                else CampaignStatus.APPROVED
            ),
            steps=campaign_steps,
            metadata=metadata,
        )


def _split_frontmatter(text: str) -> tuple[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("Plan file must begin with YAML frontmatter delimited by ---")
    return match.group(1), match.group(2)


def _normalize_heading(value: str) -> str:
    normalized = re.sub(r"[_-]+", " ", value.strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return _SECTION_ALIASES.get(normalized, normalized)


def _extract_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            sections[current_key] = "\n".join(current_lines).strip()
        current_lines = []

    for raw_line in body.splitlines():
        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            flush()
            current_key = _normalize_heading(heading_match.group(1))
            if current_key not in _SECTION_ALIASES.values():
                current_key = None
            continue
        if current_key is not None:
            current_lines.append(raw_line)

    flush()
    return sections


def _normalize_block_text(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def _parse_markdown_list(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []

    for raw_line in value.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if current:
                items.append(_normalize_inline_text(" ".join(current)))
                current = []
            continue

        item_match = _LIST_ITEM_RE.match(line)
        if item_match:
            if current:
                items.append(_normalize_inline_text(" ".join(current)))
            current = [item_match.group(1).strip()]
            continue

        if current:
            current.append(line.strip())
        else:
            current = [line.strip()]

    if current:
        items.append(_normalize_inline_text(" ".join(current)))

    return [item for item in items if item]


def _normalize_inline_text(value: str) -> str:
    stripped = _EMPHASIS_RE.sub("", value)
    stripped = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped


def _split_step_text(value: str) -> tuple[str, str]:
    cleaned = _normalize_inline_text(value)
    if not cleaned:
        return "", ""

    match = re.match(r"^(?P<label>[^-:]+?)\s*(?:--| - |: )\s*(?P<detail>.+)$", cleaned)
    if match:
        return match.group("label").strip(), match.group("detail").strip()

    return cleaned, cleaned


def _extract_explicit_command(value: str) -> tuple[str | None, str]:
    cleaned = _normalize_inline_text(value)
    match = re.match(r"^/(?P<command>[a-z0-9-]+)\b\s*(?P<args>.*)$", cleaned)
    if not match:
        return None, cleaned
    command = match.group("command").strip().lower()
    if command not in _KNOWN_COMMANDS:
        return None, cleaned
    return command, match.group("args").strip()


def _infer_step_command(
    *,
    label: str,
    detail: str,
    intent: str,
    is_last: bool,
) -> str:
    haystack = f"{label} {detail}".strip().lower()

    for command, patterns in _COMMAND_PATTERNS:
        if any(pattern in haystack for pattern in patterns):
            return command

    if is_last and any(token in haystack for token in ("report", "summary", "deliverable", "final")):
        return "synthesize"

    return _INTENT_FALLBACKS.get(intent, "research")
