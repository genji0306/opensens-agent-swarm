"""OAS module registry — dynamic capability registration and discovery."""

from oas_core.registry.capability import (
    ModuleCapability,
    ModuleHealth,
    ModuleStatus,
    CostEstimate,
)
from oas_core.registry.module_registry import ModuleRegistry, get_module_registry

__all__ = [
    "ModuleCapability",
    "ModuleHealth",
    "ModuleStatus",
    "CostEstimate",
    "ModuleRegistry",
    "get_module_registry",
]
