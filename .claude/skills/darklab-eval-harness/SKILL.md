---
name: darklab-eval-harness
description: OAS eval subsystem — 5-dimension rubric, EvalScorer, EvalRunner, golden set YAML fixtures, CI regression gates, and Generator-Evaluator loop.
origin: OAS
---

# Eval Harness

Eval-driven development for OAS research pipelines. 5-dimension rubric with golden YAML fixtures covering EIT sensors, ionic liquids, and materials science.

## When to Activate

- Working on `core/oas_core/eval/` subsystem
- Adding or updating golden set fixtures in `core/tests/eval_golden/`
- Running CI regression checks
- Implementing the Generator-Evaluator loop

## 5-Dimension Rubric

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| completeness | 0.25 | Key points covered |
| accuracy | 0.25 | Verified facts present |
| source_quality | 0.20 | Expected sources cited |
| synthesis | 0.20 | Novel insight beyond source summary |
| cost_efficiency | 0.10 | Actual cost vs expected cost |

Pass threshold: **3.5 / 5.0** weighted average.

## EvalScorer

`core/oas_core/eval/scorer.py`

```python
from oas_core.eval import EvalScorer

scorer = EvalScorer()
result = scorer.score(
    task_id="research_ionic_liquids",
    output=step_output_text,
    ground_truth={
        "key_points": ["BMIM-BF4 conductivity", "electrode stability"],
        "verified_facts": ["conductivity > 10 mS/cm at 25°C"],
        "expected_sources": ["arxiv.org", "pubmed"],
    },
    actual_cost_usd=0.12,
    expected_cost_usd=0.50,
)
# result.weighted_average, result.passed, result.feedback
```

**Cost efficiency scoring**:
- Local-only (cost=0) or within expected → 5.0
- Up to 2× expected → 3.5
- Up to 5× expected → 2.0
- > 5× expected → 1.0

## EvalRunner

`core/oas_core/eval/runner.py`

```python
from oas_core.eval import EvalRunner

runner = EvalRunner(golden_dir="core/tests/eval_golden")
report = runner.run_all(
    outputs_by_task_id={"research_ionic_liquids": output_text, ...},
    costs={"research_ionic_liquids": 0.12, ...},
    config_hash="sha256:...",
)
print(report.to_markdown())
# report.passed / report.total, report.avg_score, report.per_task_type
```

Loads YAML golden set (supports both single-dict and list formats). Emits `eval.run.completed` DRVP event. Emits `eval.regression.detected` if avg_score drops > 0.3 from last run.

## Golden Set Format

`core/tests/eval_golden/{task_id}.yaml`

```yaml
task_id: research_ionic_liquids
task_type: RESEARCH
description: "Survey BMIM ionic liquid electrode literature"
input: "Research BMIM-based ionic liquids for EIT sensor electrodes"
ground_truth:
  key_points:
    - "BMIM-BF4 shows high ionic conductivity (>10 mS/cm)"
    - "Electrochemical stability window >3V"
  verified_facts:
    - "BMIM-BF4 melting point: -71°C"
  expected_sources:
    - "arxiv.org"
    - "pubmed.ncbi.nlm.nih.gov"
  expected_cost_usd: 0.50
```

**20 fixtures** covering: RESEARCH (6), SIMULATE (3), SYNTHESIZE (3), DOE (2), DEEP_RESEARCH (2), LITERATURE (2), ANALYZE (2).

Domain: EIT sensors, ionic liquids, DFT simulations, materials science (DarkLab's actual research areas).

## CI Regression Gate

```bash
# In pytest suite
pytest core/tests/test_eval_runner.py -q
# Fails if any fixture scores < 3.5 or regression > 0.3 from baseline
```

DRVP events:
- `eval.run.completed` — full report payload
- `eval.regression.detected` — score dropped vs baseline

## Generator-Evaluator Loop

```
Generator (CampaignEngine step)
    │ output
    ▼
EvalScorer.score()
    │ passed=False
    ▼
Retry prompt (up to 3 attempts)
    │ passed=True or max retries
    ▼
KnowledgeIngester.ingest()
```

Threshold: 3.5. Max retries: 3. On final failure: emit `eval.regression.detected`, continue with best attempt.

## EvalReport Output

```
## Eval Report — 2026-04-10T03:00:00Z

Config hash: sha256:abc123

| Metric | Value |
|--------|-------|
| Total | 20 |
| Passed | 18 |
| Failed | 2 |
| Avg score | 4.1/5.0 |

### By task type
| Type | Passed | Avg |
|------|--------|-----|
| RESEARCH | 6/6 | 4.3 |
| SIMULATE | 2/3 | 3.8 |
```
