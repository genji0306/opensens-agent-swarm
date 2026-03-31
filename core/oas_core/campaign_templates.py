"""Campaign template library — YAML-defined reusable campaign patterns.

Templates define common research workflows as step sequences that can
be instantiated into full CampaignSchema objects with optional overrides.
Templates are loaded from a directory of YAML files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from oas_core.schemas.campaign import CampaignSchema, CampaignStepSchema

__all__ = ["CampaignTemplate", "TemplateRegistry", "YAML_AVAILABLE"]

logger = logging.getLogger("oas.campaign_templates")

try:
    import yaml
    from yaml import CSafeLoader as _Loader
except ImportError:
    try:
        import yaml  # type: ignore[no-redef]
        from yaml import SafeLoader as _Loader  # type: ignore[assignment,no-redef]
    except ImportError:
        yaml = None  # type: ignore[assignment]
        _Loader = None  # type: ignore[assignment,misc]

YAML_AVAILABLE = yaml is not None


class TemplateStep(BaseModel):
    """A step definition within a template."""

    step: int
    command: str
    args_template: str = ""  # Supports {objective} placeholder
    depends_on: list[int] = Field(default_factory=list)
    device: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class CampaignTemplate(BaseModel):
    """A reusable campaign template loaded from YAML."""

    name: str
    description: str = ""
    category: str = "general"
    steps: list[TemplateStep] = Field(default_factory=list)
    default_config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    def instantiate(
        self,
        objective: str = "",
        overrides: dict[str, Any] | None = None,
    ) -> CampaignSchema:
        """Create a CampaignSchema from this template.

        Args:
            objective: The campaign objective (substituted into step args).
            overrides: Optional overrides for template defaults.
        """
        ovr = overrides or {}
        steps = []
        for ts in self.steps:
            args = ts.args_template.replace("{objective}", objective)
            # Apply per-step overrides if provided
            step_overrides = ovr.get(f"step_{ts.step}", {})
            if "args" in step_overrides:
                args = step_overrides["args"]

            steps.append(CampaignStepSchema(
                step=ts.step,
                command=ts.command,
                args=args,
                depends_on=ts.depends_on,
            ))

        campaign = CampaignSchema(
            title=ovr.get("title", f"{self.name}: {objective[:80]}"),
            objective=objective,
            steps=steps,
            metadata={
                "template": self.name,
                "category": self.category,
                **self.default_config,
                **ovr.get("metadata", {}),
            },
        )

        return campaign


class TemplateRegistry:
    """Registry of campaign templates loaded from YAML files.

    Usage::

        registry = TemplateRegistry()
        registry.load_from_dir(Path("cluster/templates"))

        # List available templates
        for t in registry.list():
            print(t.name, t.description)

        # Instantiate a template
        campaign = registry.instantiate("literature-review", "quantum dot synthesis")
    """

    def __init__(self) -> None:
        self._templates: dict[str, CampaignTemplate] = {}

    def register(self, template: CampaignTemplate) -> None:
        """Register a template."""
        self._templates[template.name] = template
        logger.info("template_registered", extra={"name": template.name})

    def get(self, name: str) -> CampaignTemplate | None:
        return self._templates.get(name)

    def list(self) -> list[CampaignTemplate]:
        return list(self._templates.values())

    def list_by_category(self, category: str) -> list[CampaignTemplate]:
        return [t for t in self._templates.values() if t.category == category]

    def load_from_dir(self, directory: Path) -> int:
        """Load all YAML template files from a directory.

        Returns the number of templates loaded.
        """
        if not directory.exists():
            logger.warning("template_dir_not_found", extra={"path": str(directory)})
            return 0

        count = 0
        for path in sorted(directory.glob("*.yaml")):
            try:
                template = self._load_file(path)
                self.register(template)
                count += 1
            except Exception as e:
                logger.warning(
                    "template_load_failed",
                    extra={"path": str(path), "error": str(e)},
                )
        return count

    def _load_file(self, path: Path) -> CampaignTemplate:
        """Parse a single YAML template file."""
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML is required to load template files")
        with open(path) as f:
            data = yaml.load(f, Loader=_Loader)  # type: ignore[union-attr]

        if not isinstance(data, dict):
            raise ValueError(f"Template must be a YAML mapping, got {type(data)}")

        return CampaignTemplate.model_validate(data)

    def instantiate(
        self,
        template_name: str,
        objective: str = "",
        overrides: dict[str, Any] | None = None,
    ) -> CampaignSchema:
        """Instantiate a named template into a CampaignSchema.

        Raises KeyError if the template doesn't exist.
        """
        template = self._templates.get(template_name)
        if template is None:
            raise KeyError(f"Template '{template_name}' not found")
        return template.instantiate(objective, overrides)

    @property
    def count(self) -> int:
        return len(self._templates)
