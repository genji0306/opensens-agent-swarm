"""Contract tests for OAS-1 schema registry, campaign schemas, and intents.

Tests cover:
- Campaign schema creation, serialization, and checkpoint round-trip
- Campaign state machine transitions (valid and invalid)
- Cost attribution model
- Intent package schemas (RIP, SIP, EIP, KA, RR, Compute)
- Schema registry registration, validation, discovery
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from oas_core.schemas.campaign import (
    CampaignSchema,
    CampaignStepSchema,
    CampaignStatus,
    CostAttribution,
    SCHEMA_VERSION,
)
from oas_core.schemas.intents import (
    ResearchIntentPackage,
    KnowledgeArtifact,
    SimulationIntentPackage,
    ExperimentIntentPackage,
    RunRecord,
    ComputeRequest,
    ComputeReceipt,
    EvidenceType,
    IntentPriority,
)
from oas_core.schemas.registry import SchemaRegistry, SchemaEntry


# ── Campaign Schema ─────────────────────────────────────────


class TestCampaignSchema:
    def test_create_with_defaults(self):
        c = CampaignSchema(title="Test Campaign", objective="Run tests")
        assert c.schema_version == SCHEMA_VERSION
        assert c.status == CampaignStatus.DRAFT
        assert len(c.campaign_id) == 16
        assert c.title == "Test Campaign"

    def test_campaign_id_unique(self):
        a = CampaignSchema()
        b = CampaignSchema()
        assert a.campaign_id != b.campaign_id

    def test_checkpoint_roundtrip(self):
        c = CampaignSchema(
            title="Research QD",
            objective="Quantum dot synthesis",
            agent_name="leader",
            device="leader",
            steps=[
                CampaignStepSchema(step=1, command="research", args="quantum dots"),
                CampaignStepSchema(step=2, command="simulate", args="QD model", depends_on=[1]),
            ],
        )
        data = c.to_checkpoint()
        restored = CampaignSchema.from_checkpoint(data)
        assert restored.title == c.title
        assert restored.campaign_id == c.campaign_id
        assert len(restored.steps) == 2
        assert restored.steps[1].depends_on == [1]

    def test_step_duration(self):
        s = CampaignStepSchema(
            step=1,
            command="research",
            args="test",
            started_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 0, 1, 30, tzinfo=timezone.utc),
        )
        assert s.duration_seconds == 90.0

    def test_step_duration_none_when_incomplete(self):
        s = CampaignStepSchema(step=1, command="research", args="test")
        assert s.duration_seconds is None

    def test_completed_and_failed_steps(self):
        c = CampaignSchema(
            steps=[
                CampaignStepSchema(step=1, command="research", args="a", status="completed"),
                CampaignStepSchema(step=2, command="simulate", args="b", status="failed"),
                CampaignStepSchema(step=3, command="analyze", args="c", status="completed"),
            ]
        )
        assert len(c.completed_steps) == 2
        assert len(c.failed_steps) == 1

    def test_cost_attribution(self):
        cost = CostAttribution(
            campaign_id="test123",
            step_id=1,
            model="claude-sonnet-4-6-20260301",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.015,
            latency_ms=2340.0,
            agent_name="leader",
        )
        assert cost.cost_usd == 0.015
        assert cost.input_tokens + cost.output_tokens == 1500


# ── Campaign State Machine ──────────────────────────────────


class TestCampaignStateMachine:
    """Test all valid and invalid state transitions."""

    def test_draft_to_pending_approval(self):
        c = CampaignSchema()
        c.transition_to(CampaignStatus.PENDING_APPROVAL)
        assert c.status == CampaignStatus.PENDING_APPROVAL

    def test_draft_to_approved(self):
        c = CampaignSchema()
        c.transition_to(CampaignStatus.APPROVED)
        assert c.status == CampaignStatus.APPROVED

    def test_draft_to_cancelled(self):
        c = CampaignSchema()
        c.transition_to(CampaignStatus.CANCELLED)
        assert c.status == CampaignStatus.CANCELLED

    def test_approved_to_running(self):
        c = CampaignSchema(status=CampaignStatus.APPROVED)
        c.transition_to(CampaignStatus.RUNNING)
        assert c.status == CampaignStatus.RUNNING
        assert c.started_at is not None

    def test_running_to_completed(self):
        c = CampaignSchema(status=CampaignStatus.RUNNING)
        c.transition_to(CampaignStatus.COMPLETED)
        assert c.status == CampaignStatus.COMPLETED
        assert c.completed_at is not None

    def test_running_to_failed(self):
        c = CampaignSchema(status=CampaignStatus.RUNNING)
        c.transition_to(CampaignStatus.FAILED)
        assert c.status == CampaignStatus.FAILED

    def test_running_to_paused(self):
        c = CampaignSchema(status=CampaignStatus.RUNNING)
        c.transition_to(CampaignStatus.PAUSED)
        assert c.status == CampaignStatus.PAUSED

    def test_paused_to_running(self):
        c = CampaignSchema(status=CampaignStatus.PAUSED)
        c.transition_to(CampaignStatus.RUNNING)
        assert c.status == CampaignStatus.RUNNING

    def test_failed_to_running_retry(self):
        c = CampaignSchema(status=CampaignStatus.FAILED)
        c.transition_to(CampaignStatus.RUNNING)
        assert c.status == CampaignStatus.RUNNING

    def test_invalid_draft_to_running(self):
        c = CampaignSchema()
        with pytest.raises(ValueError, match="Invalid transition"):
            c.transition_to(CampaignStatus.RUNNING)

    def test_invalid_draft_to_completed(self):
        c = CampaignSchema()
        with pytest.raises(ValueError, match="Invalid transition"):
            c.transition_to(CampaignStatus.COMPLETED)

    def test_invalid_completed_to_running(self):
        c = CampaignSchema(status=CampaignStatus.COMPLETED)
        with pytest.raises(ValueError, match="Invalid transition"):
            c.transition_to(CampaignStatus.RUNNING)

    def test_invalid_cancelled_to_anything(self):
        c = CampaignSchema(status=CampaignStatus.CANCELLED)
        for target in CampaignStatus:
            if target != CampaignStatus.CANCELLED:
                with pytest.raises(ValueError):
                    c.transition_to(target)

    def test_transition_updates_timestamp(self):
        c = CampaignSchema()
        original_updated = c.updated_at
        c.transition_to(CampaignStatus.APPROVED)
        assert c.updated_at >= original_updated


# ── Intent Schemas ──────────────────────────────────────────


class TestIntentSchemas:
    def test_research_intent_package(self):
        rip = ResearchIntentPackage(
            objective="Investigate quantum dot photoluminescence",
            constraints=["Use only open-access sources"],
            budget_limit_usd=5.0,
            source_requirements=5,
        )
        assert rip.intent_id.startswith("rip-")
        assert rip.priority == IntentPriority.NORMAL
        assert rip.convergence_threshold == 0.75

    def test_knowledge_artifact(self):
        ka = KnowledgeArtifact(
            campaign_id="camp123",
            findings="QD exhibit size-dependent emission",
            confidence=0.85,
            evidence_type=EvidenceType.LITERATURE,
            sources=[{"title": "Smith 2024", "doi": "10.1234/test"}],
        )
        assert ka.artifact_id.startswith("ka-")
        assert ka.confidence == 0.85

    def test_simulation_intent_package(self):
        sip = SimulationIntentPackage(
            model_spec="DFT B3LYP/6-31G*",
            parameters={"basis_set": "6-31G*", "functional": "B3LYP"},
            compute_budget_usd=10.0,
        )
        assert sip.intent_id.startswith("sip-")

    def test_experiment_intent_package(self):
        eip = ExperimentIntentPackage(
            protocol="Sol-gel synthesis",
            materials=["TEOS", "HCl", "EtOH"],
            safety_requirements=["fume hood", "PPE"],
            approval_required=True,
        )
        assert eip.intent_id.startswith("eip-")
        assert eip.approval_required is True

    def test_run_record(self):
        rr = RunRecord(
            campaign_id="camp123",
            results={"energy": -150.234, "converged": True},
            metrics={"wall_time": 120.5, "iterations": 42},
            artifacts=["output.log", "trajectory.xyz"],
            duration_seconds=120.5,
        )
        assert rr.record_id.startswith("rr-")
        assert rr.metrics["wall_time"] == 120.5

    def test_compute_request_receipt(self):
        req = ComputeRequest(
            campaign_id="camp123",
            requested_resources={"gpu": 1, "memory_gb": 16},
            max_cost_usd=5.0,
        )
        receipt = ComputeReceipt(
            request_id=req.request_id,
            campaign_id="camp123",
            allocated_resources={"gpu": 1, "memory_gb": 16},
            cost_usd=3.50,
        )
        assert receipt.request_id == req.request_id
        assert receipt.cost_usd == 3.50

    def test_intent_id_uniqueness(self):
        a = ResearchIntentPackage(objective="A")
        b = ResearchIntentPackage(objective="B")
        assert a.intent_id != b.intent_id

    def test_schema_version_present(self):
        rip = ResearchIntentPackage(objective="Test")
        ka = KnowledgeArtifact()
        sip = SimulationIntentPackage()
        assert rip.schema_version == "1.0.0"
        assert ka.schema_version == "1.0.0"
        assert sip.schema_version == "1.0.0"


# ── Schema Registry ─────────────────────────────────────────


class TestSchemaRegistry:
    def test_register_and_get(self):
        reg = SchemaRegistry()
        reg.register("campaign", "1.0.0", CampaignSchema, description="Test")
        entry = reg.get("campaign")
        assert entry is not None
        assert entry.name == "campaign"
        assert entry.version == "1.0.0"

    def test_get_by_version(self):
        reg = SchemaRegistry()
        reg.register("campaign", "1.0.0", CampaignSchema)
        reg.register("campaign", "2.0.0", CampaignSchema)
        v1 = reg.get("campaign", "1.0.0")
        v2 = reg.get("campaign", "2.0.0")
        assert v1 is not None
        assert v2 is not None
        # Default (latest) should be v2
        default = reg.get("campaign")
        assert default is not None and default.version == "2.0.0"

    def test_validate(self):
        reg = SchemaRegistry()
        reg.register("research_intent", "1.0.0", ResearchIntentPackage)
        result = reg.validate("research_intent", {"objective": "Test query"})
        assert isinstance(result, ResearchIntentPackage)
        assert result.objective == "Test query"

    def test_validate_unknown_schema_raises(self):
        reg = SchemaRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.validate("nonexistent", {})

    def test_list_schemas(self):
        reg = SchemaRegistry()
        reg.register("campaign", "1.0.0", CampaignSchema, description="Campaign object")
        reg.register("research_intent", "1.0.0", ResearchIntentPackage, description="Research")
        schemas = reg.list_schemas()
        assert len(schemas) == 2
        names = {s["name"] for s in schemas}
        assert names == {"campaign", "research_intent"}

    def test_list_versions(self):
        reg = SchemaRegistry()
        reg.register("campaign", "1.0.0", CampaignSchema)
        reg.register("campaign", "1.1.0", CampaignSchema)
        versions = reg.list_versions("campaign")
        assert "1.0.0" in versions
        assert "1.1.0" in versions

    def test_json_schema(self):
        entry = SchemaEntry("test", "1.0.0", CampaignSchema)
        schema = entry.json_schema()
        assert "properties" in schema
        assert "campaign_id" in schema["properties"]

    def test_schema_count(self):
        reg = SchemaRegistry()
        assert reg.schema_count == 0
        reg.register("a", "1.0.0", CampaignSchema)
        reg.register("b", "1.0.0", CampaignSchema)
        assert reg.schema_count == 2

    def test_get_registry_singleton(self):
        from oas_core.schemas.registry import get_registry
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
        assert r1.schema_count == 10  # All default schemas registered
