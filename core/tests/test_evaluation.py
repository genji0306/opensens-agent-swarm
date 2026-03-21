"""Tests for oas_core.evaluation — self-evaluation loop."""
import pytest

from oas_core.evaluation import (
    Evaluator,
    EvaluationResult,
    QualityLevel,
    RuleBasedEvaluator,
)
from oas_core.protocols.drvp import configure


@pytest.fixture(autouse=True)
def disable_drvp():
    configure(company_id="test", redis_client=None, paperclip_client=None)


class TestQualityLevel:
    def test_excellent(self):
        assert QualityLevel.from_score(0.95) == QualityLevel.EXCELLENT

    def test_good(self):
        assert QualityLevel.from_score(0.75) == QualityLevel.GOOD

    def test_acceptable(self):
        assert QualityLevel.from_score(0.55) == QualityLevel.ACCEPTABLE

    def test_poor(self):
        assert QualityLevel.from_score(0.35) == QualityLevel.POOR

    def test_failed(self):
        assert QualityLevel.from_score(0.1) == QualityLevel.FAILED


class TestEvaluationResult:
    def test_to_dict(self):
        r = EvaluationResult(
            score=0.85,
            quality=QualityLevel.GOOD,
            criteria_scores={"completeness": 0.9},
            feedback="Looks good",
        )
        d = r.to_dict()
        assert d["score"] == 0.85
        assert d["quality"] == "good"
        assert d["should_retry"] is False


class TestRuleBasedEvaluator:
    def test_good_research_result(self):
        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(
            command="research",
            request="Research quantum dots for EIT",
            output={
                "findings": "Quantum dots show promise for EIT electrode materials. " * 20,
                "sources": [
                    {"title": "QD Electrodes Review", "doi": "10.1234/a"},
                    {"title": "EIT Materials", "doi": "10.1234/b"},
                    {"title": "Nanomaterials for Sensing", "doi": "10.1234/c"},
                ],
            },
        )
        assert result.score >= 0.7
        assert result.quality in (QualityLevel.GOOD, QualityLevel.EXCELLENT)
        assert not result.should_retry

    def test_empty_output(self):
        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(
            command="research",
            request="Research something",
            output={},
        )
        assert result.score < 0.5
        assert result.quality in (QualityLevel.POOR, QualityLevel.FAILED)

    def test_error_output(self):
        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(
            command="simulate",
            request="Run simulation",
            output={"error": "Simulation crashed", "status": "error"},
        )
        assert result.criteria_scores["error_free"] == 0.0
        assert result.score < 0.5

    def test_short_output(self):
        evaluator = RuleBasedEvaluator(min_output_length=200)
        result = evaluator.evaluate(
            command="analyze",
            request="Analyze data",
            output={"analysis": "Short."},
        )
        assert result.criteria_scores["completeness"] < 0.5

    def test_no_sources_for_research(self):
        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(
            command="research",
            request="Research topic",
            output={"findings": "Some findings " * 30},
        )
        assert result.criteria_scores["sources"] == 0.0

    def test_simulate_ignores_sources(self):
        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(
            command="simulate",
            request="Run sim",
            output={"results": "Simulation output " * 20, "parameters": {"a": 1}},
        )
        assert result.criteria_scores["sources"] == 1.0  # Not required

    def test_structure_check(self):
        evaluator = RuleBasedEvaluator()
        # Research expects "findings" and "sources"
        result = evaluator.evaluate(
            command="research",
            request="test",
            output={"findings": "x" * 200, "sources": ["a", "b", "c"]},
        )
        assert result.criteria_scores["structure"] == 1.0

    def test_retry_threshold(self):
        evaluator = RuleBasedEvaluator(retry_threshold=0.6)
        result = evaluator.evaluate(
            command="research",
            request="test",
            output={"text": "Short"},
        )
        assert result.should_retry is True


class TestEvaluator:
    @pytest.mark.asyncio
    async def test_evaluate_step_basic(self):
        evaluator = Evaluator()
        result = await evaluator.evaluate_step(
            request_id="req_1",
            step_number=1,
            command="research",
            request="quantum sensors",
            output={"findings": "Good research " * 30, "sources": ["a", "b", "c"]},
            agent_name="academic",
            device="academic",
        )
        assert isinstance(result, EvaluationResult)
        assert result.score > 0

    @pytest.mark.asyncio
    async def test_evaluate_step_with_llm_fallback(self):
        async def mock_llm(command, request, output):
            return {"score": 0.8, "feedback": "LLM says it's fine"}

        evaluator = Evaluator(llm_eval_fn=mock_llm, use_llm_for_poor=True)
        result = await evaluator.evaluate_step(
            request_id="req_2",
            step_number=1,
            command="research",
            request="test",
            output={},  # empty → will be poor
            agent_name="academic",
            device="academic",
        )
        # LLM should have bumped the score
        assert "LLM" in result.feedback or result.score > 0

    @pytest.mark.asyncio
    async def test_evaluate_campaign(self):
        evaluator = Evaluator()
        result = await evaluator.evaluate_campaign(
            request_id="req_3",
            original_request="Full EIT study",
            step_results=[
                {"command": "research", "result": {"findings": "x" * 200, "sources": ["a", "b"]}},
                {"command": "simulate", "result": {"results": "y" * 200, "parameters": {}}},
            ],
            agent_name="leader",
            device="leader",
        )
        assert result.score > 0
        assert result.criteria_scores["step_count"] == 2

    @pytest.mark.asyncio
    async def test_evaluate_empty_campaign(self):
        evaluator = Evaluator()
        result = await evaluator.evaluate_campaign(
            request_id="req_4",
            original_request="test",
            step_results=[],
            agent_name="leader",
            device="leader",
        )
        assert result.quality == QualityLevel.FAILED
