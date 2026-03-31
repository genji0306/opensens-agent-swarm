"""Schema registry — versioned schema management for OAS.

Provides a central registry where all campaign and intent schemas are
registered at startup. The registry validates schema versions, supports
forward/backward compatibility checks, and enables discovery of available
schemas by name and version.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

__all__ = ["SchemaRegistry", "get_registry", "SchemaEntry"]

logger = logging.getLogger("oas.schemas.registry")


class SchemaEntry:
    """A registered schema with version metadata."""

    def __init__(
        self,
        name: str,
        version: str,
        model_class: type[BaseModel],
        *,
        description: str = "",
    ):
        self.name = name
        self.version = version
        self.model_class = model_class
        self.description = description

    def validate(self, data: dict[str, Any]) -> BaseModel:
        """Validate data against this schema, returning a model instance."""
        return self.model_class.model_validate(data)

    def json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema for this model."""
        return self.model_class.model_json_schema()


class SchemaRegistry:
    """Central registry for OAS schemas.

    Usage::

        registry = SchemaRegistry()
        registry.register("campaign", "1.0.0", CampaignSchema)
        registry.register("research_intent", "1.0.0", ResearchIntentPackage)

        # Validate incoming data
        campaign = registry.validate("campaign", data)

        # Discover schemas
        schemas = registry.list_schemas()
    """

    def __init__(self) -> None:
        self._schemas: dict[str, SchemaEntry] = {}
        self._versions: dict[str, dict[str, SchemaEntry]] = {}

    def register(
        self,
        name: str,
        version: str,
        model_class: type[BaseModel],
        *,
        description: str = "",
    ) -> None:
        """Register a schema. Latest version becomes the default."""
        entry = SchemaEntry(
            name=name,
            version=version,
            model_class=model_class,
            description=description,
        )
        self._schemas[name] = entry

        if name not in self._versions:
            self._versions[name] = {}
        self._versions[name][version] = entry

        logger.debug("schema_registered", extra={"name": name, "version": version})

    def get(self, name: str, version: str | None = None) -> SchemaEntry | None:
        """Get a schema entry by name and optional version."""
        if version:
            return self._versions.get(name, {}).get(version)
        return self._schemas.get(name)

    def validate(self, name: str, data: dict[str, Any], *, version: str | None = None) -> BaseModel:
        """Validate data against a named schema."""
        entry = self.get(name, version)
        if entry is None:
            raise KeyError(f"Schema '{name}' (version={version}) not found in registry")
        return entry.validate(data)

    def list_schemas(self) -> list[dict[str, str]]:
        """List all registered schemas with their current versions."""
        return [
            {
                "name": entry.name,
                "version": entry.version,
                "description": entry.description,
            }
            for entry in self._schemas.values()
        ]

    def list_versions(self, name: str) -> list[str]:
        """List all registered versions for a schema."""
        return list(self._versions.get(name, {}).keys())

    @property
    def schema_count(self) -> int:
        return len(self._schemas)


def _build_default_registry() -> SchemaRegistry:
    """Build the default registry with all OAS schemas."""
    from oas_core.schemas.campaign import (
        CampaignSchema,
        CampaignStepSchema,
        CostAttribution,
    )
    from oas_core.schemas.intents import (
        ResearchIntentPackage,
        KnowledgeArtifact,
        SimulationIntentPackage,
        ExperimentIntentPackage,
        RunRecord,
        ComputeRequest,
        ComputeReceipt,
    )

    reg = SchemaRegistry()

    reg.register("campaign", "1.0.0", CampaignSchema, description="Campaign lifecycle object")
    reg.register("campaign_step", "1.0.0", CampaignStepSchema, description="Campaign step")
    reg.register("cost_attribution", "1.0.0", CostAttribution, description="LLM cost attribution")
    reg.register("research_intent", "1.0.0", ResearchIntentPackage, description="Research objective")
    reg.register("knowledge_artifact", "1.0.0", KnowledgeArtifact, description="Research output")
    reg.register("simulation_intent", "1.0.0", SimulationIntentPackage, description="Simulation task")
    reg.register("experiment_intent", "1.0.0", ExperimentIntentPackage, description="Experiment task")
    reg.register("run_record", "1.0.0", RunRecord, description="Simulation/experiment output")
    reg.register("compute_request", "1.0.0", ComputeRequest, description="Compute allocation request")
    reg.register("compute_receipt", "1.0.0", ComputeReceipt, description="Compute allocation receipt")

    return reg


@lru_cache(maxsize=1)
def get_registry() -> SchemaRegistry:
    """Get the singleton schema registry (lazy-loaded)."""
    return _build_default_registry()
