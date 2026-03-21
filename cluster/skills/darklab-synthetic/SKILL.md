---
name: darklab-synthetic
description: Generate realistic synthetic datasets that approximate expected experimental distributions for testing and simulation validation.
metadata:
  {"openclaw": {"emoji": "factory", "requires": {"env": ["ANTHROPIC_API_KEY"], "bins": ["python3"]}}}
---

# DarkLab Synthetic Data Agent

Generates synthetic datasets based on experimental parameters and expected distributions, for use before real lab data is available.

## Capabilities

- Generate synthetic XRD patterns for given crystal structures
- Simulate CV curves for electrochemical experiments
- Create synthetic BET surface area data
- Generate noise-realistic sensor data
- Produce multi-parameter correlated datasets

## Input

```json
{
  "data_type": "cv_curve",
  "parameters": {
    "scan_rate": {"value": 50, "unit": "mV/s"},
    "potential_range": [-0.5, 1.0],
    "n_cycles": 3,
    "noise_level": 0.02
  },
  "n_samples": 100,
  "seed": 42
}
```

## Output

```json
{
  "status": "complete",
  "data": {
    "potential": [0.0, 0.01, 0.02],
    "current": [0.001, 0.0012, 0.0015],
    "metadata": {"scan_rate": 50, "unit": "mV/s"}
  },
  "statistics": {
    "mean_peak_current": 0.05,
    "peak_potential": 0.45
  },
  "artifacts": ["synthetic_cv.csv", "synthetic_cv.json"]
}
```

## Notes

- Synthetic data is labeled as such in metadata to prevent confusion with real data
- Random seeds are recorded for reproducibility
- Data distributions are based on literature-reported ranges from the Academic Agent
