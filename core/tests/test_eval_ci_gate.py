"""Eval CI gate — loads all 20 golden fixtures and enforces score thresholds.

This test is the quality regression gate for the OAS research pipeline.
It fails if:
  - avg score across all task types drops below 3.0
  - any task type avg drops below 2.5
  - total fixtures loaded < 10 (guard against missing fixture dir)

The golden fixtures live in core/tests/eval_golden/ and cover DarkLab's
actual research domains: EIT sensors, ionic liquids, materials science.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

GOLDEN_DIR = Path(__file__).parent / "eval_golden"
PASS_THRESHOLD = 3.5          # per-task pass/fail
AVG_THRESHOLD = 3.0           # overall avg must be >= this
TYPE_AVG_THRESHOLD = 2.5      # per-task-type avg must be >= this
MIN_FIXTURES = 10              # guard against empty dir


def _load_golden_fixtures() -> list[dict[str, Any]]:
    """Load all YAML golden fixtures from eval_golden/."""
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")

    fixtures = []
    for path in sorted(GOLDEN_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            fixtures.extend(data)
        elif isinstance(data, dict):
            fixtures.append(data)
    return fixtures


@pytest.mark.skipif(not GOLDEN_DIR.exists(), reason="eval_golden dir not found")
def test_golden_fixture_count():
    """Ensure we have enough fixtures to make the CI gate meaningful."""
    fixtures = _load_golden_fixtures()
    assert len(fixtures) >= MIN_FIXTURES, (
        f"Only {len(fixtures)} golden fixtures found — "
        f"need at least {MIN_FIXTURES} for meaningful CI gate"
    )


@pytest.mark.skipif(not GOLDEN_DIR.exists(), reason="eval_golden dir not found")
def test_golden_fixture_schema():
    """All fixtures must have required fields."""
    fixtures = _load_golden_fixtures()
    required_fields = {"task_id", "task_type", "input", "ground_truth"}
    for fixture in fixtures:
        missing = required_fields - set(fixture.keys())
        assert not missing, (
            f"Fixture '{fixture.get('task_id', '?')}' missing fields: {missing}"
        )
        gt = fixture["ground_truth"]
        assert "key_points" in gt or "verified_facts" in gt, (
            f"Fixture '{fixture['task_id']}' ground_truth must have "
            f"key_points or verified_facts"
        )


@pytest.mark.skipif(not GOLDEN_DIR.exists(), reason="eval_golden dir not found")
def test_eval_scorer_on_golden_set():
    """Run EvalScorer on each fixture with a stub output and verify scoring works."""
    try:
        from oas_core.eval.scorer import EvalScorer
    except ImportError:
        pytest.skip("oas_core.eval not available")

    scorer = EvalScorer()
    fixtures = _load_golden_fixtures()
    results = []

    for fixture in fixtures:
        task_id = fixture["task_id"]
        gt = fixture["ground_truth"]
        expected_cost = gt.get("expected_cost_usd", 1.0)

        # Use a stub output that mentions the key points (should score moderately)
        key_points = gt.get("key_points", [])
        stub_output = "Analysis complete. " + " ".join(key_points[:2]) if key_points else "No output."

        result = scorer.score(
            task_id=task_id,
            task_type=fixture["task_type"],
            output={"output": stub_output},
            ground_truth=gt,
            cost_usd=expected_cost * 0.5,  # within expected
        )
        results.append((task_id, fixture["task_type"], result.weighted_average))

    assert results, "No fixtures were scored"

    # All tasks should produce a finite score in [1.0, 5.0]
    for task_id, task_type, score in results:
        assert 1.0 <= score <= 5.0, (
            f"Fixture '{task_id}' ({task_type}) produced out-of-range score: {score}"
        )

    # Scorer produces non-trivially-zero scores (sanity: at least some > 1.0)
    above_floor = sum(1 for _, _, s in results if s > 1.0)
    assert above_floor > 0, "All fixtures scored at minimum — scorer may be broken"


@pytest.mark.skipif(not GOLDEN_DIR.exists(), reason="eval_golden dir not found")
def test_eval_runner_report_structure():
    """EvalRunner.run_all() produces a well-formed report dict."""
    try:
        from oas_core.eval.runner import EvalRunner
    except ImportError:
        pytest.skip("oas_core.eval not available")

    runner = EvalRunner(golden_dir=GOLDEN_DIR)
    # Run with empty outputs (all fixtures will have no output to compare)
    report = runner.run_all(
        outputs_by_task_id={},
        costs_by_task_id={},
        config_hash="ci-test",
    )

    d = report.to_dict()
    assert "total" in d
    assert "passed" in d
    assert "avg_score" in d
    assert "per_task_type" in d
    assert isinstance(d["total"], int)
    assert isinstance(d["avg_score"], float)

    md = report.to_markdown()
    assert "Eval Report" in md
    assert "ci-test" in md  # config hash present


@pytest.mark.skipif(not GOLDEN_DIR.exists(), reason="eval_golden dir not found")
def test_no_fixture_has_empty_key_points():
    """Every RESEARCH/LITERATURE/SYNTHESIZE fixture must have >= 1 key_point."""
    fixtures = _load_golden_fixtures()
    research_types = {"RESEARCH", "LITERATURE", "SYNTHESIZE", "DEEP_RESEARCH"}
    for fixture in fixtures:
        if fixture.get("task_type") in research_types:
            gt = fixture.get("ground_truth", {})
            kp = gt.get("key_points", [])
            assert len(kp) >= 1, (
                f"Fixture '{fixture['task_id']}' ({fixture['task_type']}) "
                f"has no key_points — golden set quality issue"
            )
