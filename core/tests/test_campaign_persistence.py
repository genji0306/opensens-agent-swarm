"""Contract tests for campaign persistence (checkpoint save/restore/resume).

Tests cover:
- Campaign save and load round-trip
- Active campaign listing
- Campaign deletion
- Find by request_id
- Campaign resume from checkpoint (skip completed steps)
"""

from __future__ import annotations

import pytest
from pathlib import Path

from oas_core.schemas.campaign import (
    CampaignSchema,
    CampaignStepSchema,
    CampaignStatus,
)
from oas_core.schemas.persistence import CampaignStore


@pytest.fixture
def store(tmp_path: Path) -> CampaignStore:
    return CampaignStore(base_dir=tmp_path / "campaigns")


@pytest.fixture
def sample_campaign() -> CampaignSchema:
    return CampaignSchema(
        title="Test Campaign",
        request_id="req_abc123",
        objective="Test persistence",
        agent_name="leader",
        device="leader",
        steps=[
            CampaignStepSchema(step=1, command="research", args="quantum dots"),
            CampaignStepSchema(step=2, command="simulate", args="QD model", depends_on=[1]),
            CampaignStepSchema(step=3, command="analyze", args="results", depends_on=[2]),
        ],
    )


class TestCampaignStore:
    @pytest.mark.asyncio
    async def test_save_and_load(self, store: CampaignStore, sample_campaign: CampaignSchema):
        await store.save(sample_campaign)
        loaded = await store.load(sample_campaign.campaign_id)
        assert loaded is not None
        assert loaded.campaign_id == sample_campaign.campaign_id
        assert loaded.title == "Test Campaign"
        assert len(loaded.steps) == 3

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, store: CampaignStore):
        loaded = await store.load("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete(self, store: CampaignStore, sample_campaign: CampaignSchema):
        await store.save(sample_campaign)
        assert await store.delete(sample_campaign.campaign_id) is True
        assert await store.load(sample_campaign.campaign_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store: CampaignStore):
        assert await store.delete("nonexistent") is False

    @pytest.mark.asyncio
    async def test_list_active(self, store: CampaignStore):
        # Create campaigns in different states
        draft = CampaignSchema(title="Draft")
        running = CampaignSchema(title="Running", status=CampaignStatus.RUNNING)
        completed = CampaignSchema(title="Completed", status=CampaignStatus.COMPLETED)
        failed = CampaignSchema(title="Failed", status=CampaignStatus.FAILED)

        for c in [draft, running, completed, failed]:
            await store.save(c)

        active = await store.list_active()
        titles = {c.title for c in active}
        assert "Draft" in titles
        assert "Running" in titles
        assert "Completed" not in titles
        assert "Failed" not in titles

    @pytest.mark.asyncio
    async def test_list_all(self, store: CampaignStore):
        for i in range(5):
            await store.save(CampaignSchema(title=f"Campaign {i}"))
        all_campaigns = await store.list_all()
        assert len(all_campaigns) == 5

    @pytest.mark.asyncio
    async def test_list_all_with_limit(self, store: CampaignStore):
        for i in range(5):
            await store.save(CampaignSchema(title=f"Campaign {i}"))
        limited = await store.list_all(limit=3)
        assert len(limited) == 3

    @pytest.mark.asyncio
    async def test_find_by_request_id(self, store: CampaignStore, sample_campaign: CampaignSchema):
        await store.save(sample_campaign)
        found = await store.find_by_request_id("req_abc123")
        assert found is not None
        assert found.campaign_id == sample_campaign.campaign_id

    @pytest.mark.asyncio
    async def test_find_by_request_id_not_found(self, store: CampaignStore):
        found = await store.find_by_request_id("nonexistent")
        assert found is None


class TestCampaignResume:
    """Test that campaigns can be resumed from checkpoint."""

    @pytest.mark.asyncio
    async def test_resume_skips_completed_steps(self, store: CampaignStore):
        """When resuming, completed steps should be skipped."""
        campaign = CampaignSchema(
            title="Interrupted Campaign",
            status=CampaignStatus.RUNNING,
            steps=[
                CampaignStepSchema(step=1, command="research", args="QD", status="completed",
                                   result={"output": "found stuff"}),
                CampaignStepSchema(step=2, command="simulate", args="QD model", depends_on=[1],
                                   status="pending"),
                CampaignStepSchema(step=3, command="analyze", args="results", depends_on=[2],
                                   status="pending"),
            ],
        )
        await store.save(campaign)

        # Restore and check which steps need execution
        restored = await store.load(campaign.campaign_id)
        assert restored is not None
        pending = [s for s in restored.steps if s.status == "pending"]
        completed = [s for s in restored.steps if s.status == "completed"]
        assert len(completed) == 1
        assert len(pending) == 2
        assert pending[0].step == 2

    @pytest.mark.asyncio
    async def test_checkpoint_preserves_step_results(self, store: CampaignStore):
        """Step results from completed steps must survive checkpoint round-trip."""
        campaign = CampaignSchema(
            title="Partial Campaign",
            status=CampaignStatus.RUNNING,
            steps=[
                CampaignStepSchema(
                    step=1, command="research", args="test", status="completed",
                    result={"findings": "important data", "confidence": 0.9},
                ),
                CampaignStepSchema(step=2, command="simulate", args="test", depends_on=[1]),
            ],
        )
        await store.save(campaign)
        restored = await store.load(campaign.campaign_id)
        assert restored is not None
        assert restored.steps[0].result == {"findings": "important data", "confidence": 0.9}

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, store: CampaignStore):
        """Saving an existing campaign overwrites the previous checkpoint."""
        campaign = CampaignSchema(title="Evolving")
        await store.save(campaign)

        campaign.title = "Updated Title"
        campaign.transition_to(CampaignStatus.APPROVED)
        await store.save(campaign)

        loaded = await store.load(campaign.campaign_id)
        assert loaded is not None
        assert loaded.title == "Updated Title"
        assert loaded.status == CampaignStatus.APPROVED
