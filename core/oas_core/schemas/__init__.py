"""OAS schemas — versioned Pydantic models for campaigns, intents, and artifacts."""

from oas_core.schemas.campaign import (
    CampaignSchema,
    CampaignStepSchema,
    CampaignStatus,
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
from oas_core.schemas.registry import SchemaRegistry, get_registry

__all__ = [
    "CampaignSchema",
    "CampaignStepSchema",
    "CampaignStatus",
    "CostAttribution",
    "ResearchIntentPackage",
    "KnowledgeArtifact",
    "SimulationIntentPackage",
    "ExperimentIntentPackage",
    "RunRecord",
    "ComputeRequest",
    "ComputeReceipt",
    "SchemaRegistry",
    "get_registry",
]
