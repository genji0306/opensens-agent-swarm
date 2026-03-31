"""Tests for the campaign reflection layer."""

import pytest

from oas_core.decision.reflection import CampaignReflector, ReflectionResult
from oas_core.schemas.campaign import CampaignSchema, CampaignStepSchema, CostAttribution
from oas_core.protocols import drvp


@pytest.fixture(autouse=True)
def _reset_drvp():
    """Reset DRVP transport to avoid Redis calls in tests."""
    drvp.configure(redis_client=None, paperclip_client=None, company_id="test")


def _make_campaign(steps=None):
    return CampaignSchema(
        campaign_id="test_camp",
        request_id="req_1",
        objective="Research quantum dot electrodes for EIT",
        steps=steps or [],
    )


def _make_step(step=1, command="research", status="completed", result=None):
    return CampaignStepSchema(
        step=step,
        command=command,
        args="quantum dots",
        status=status,
        result=result,
    )


class TestCampaignReflector:
    @pytest.mark.asyncio
    async def test_reflect_on_good_step(self):
        reflector = CampaignReflector()
        step = _make_step(result={
            "findings": "Quantum dot electrodes show promising EIT performance with 3x improvement",
            "sources": [{"title": "Paper A"}, {"title": "Paper B"}, {"title": "Paper C"}],
        })
        campaign = _make_campaign(steps=[step])

        result = await reflector.reflect_on_step(
            campaign=campaign, step=step, objective="quantum dot electrodes"
        )

        assert result.step_number == 1
        assert result.command == "research"
        assert result.intent_alignment > 0.5
        assert result.evidence_gain > 0.3
        assert len(result.learned) > 0
        assert result.recommendation in ("proceed_to_next_step", "continue_gathering")

    @pytest.mark.asyncio
    async def test_reflect_on_empty_step(self):
        reflector = CampaignReflector()
        step = _make_step(result={})
        campaign = _make_campaign(steps=[step])

        result = await reflector.reflect_on_step(campaign=campaign, step=step)
        assert result.intent_alignment < 0.5
        assert result.evidence_gain == 0.0
        assert result.recommendation == "retry_with_refinement"

    @pytest.mark.asyncio
    async def test_reflect_on_error_step(self):
        reflector = CampaignReflector()
        step = _make_step(result={"error": "timeout", "status": "error"})
        campaign = _make_campaign(steps=[step])

        result = await reflector.reflect_on_step(campaign=campaign, step=step)
        assert len(result.unknowns) > 0
        assert any("error" in u.lower() for u in result.unknowns)

    @pytest.mark.asyncio
    async def test_reflect_on_campaign(self):
        reflector = CampaignReflector()
        steps = [
            _make_step(step=1, command="research", result={
                "findings": "Good findings on quantum dots",
                "sources": [{"title": "A"}],
            }),
            _make_step(step=2, command="simulate", result={
                "results": {"efficiency": 0.85},
                "parameters": {"voltage": 1.2},
            }),
        ]
        campaign = _make_campaign(steps=steps)
        results = await reflector.reflect_on_campaign(campaign=campaign)
        assert len(results) == 2
        assert results[0].step_number == 1
        assert results[1].step_number == 2

    @pytest.mark.asyncio
    async def test_reflection_stores_lesson(self):
        stored = []

        class MockKB:
            def store_lesson(self, **kwargs):
                stored.append(kwargs)

        reflector = CampaignReflector(knowledge_store=MockKB())
        step = _make_step(result={"findings": "Important discovery about EIT"})
        campaign = _make_campaign(steps=[step])

        await reflector.reflect_on_step(campaign=campaign, step=step)
        assert len(stored) == 1
        assert "strategy" in stored[0]

    def test_reflection_result_to_dict(self):
        result = ReflectionResult(
            step_number=1,
            command="research",
            learned=["found 3 papers"],
            unknowns=["missing mechanism"],
            intent_alignment=0.8,
            evidence_gain=0.6,
            recommendation="proceed_to_next_step",
        )
        d = result.to_dict()
        assert d["step_number"] == 1
        assert d["intent_alignment"] == 0.8
        assert result.overall_score == 0.7
