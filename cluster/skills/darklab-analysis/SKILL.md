---
name: darklab-analysis
description: Data ingestion, statistical analysis, EIS fitting, and feature extraction from experimental and synthetic data.
metadata:
  {"openclaw": {"emoji": "bar_chart", "requires": {"env": ["ANTHROPIC_API_KEY"], "bins": ["python3"]}}}
---

# DarkLab Analysis Agent

Ingests, processes, and analyzes data from experiments and simulations.

## Capabilities

- CSV/JSON data ingestion and validation
- Descriptive statistics and distribution analysis
- Electrochemical impedance spectroscopy (EIS) fitting
- Cyclic voltammetry (CV) peak detection
- UV-Vis spectral processing
- Correlation analysis and feature extraction
- Outlier detection

## Supported Analysis Types

| Type | Description | Output |
|------|-------------|--------|
| summary | Descriptive statistics | mean, std, min, max, quartiles |
| correlation | Feature correlation matrix | heatmap + correlation coefficients |
| eis_fit | EIS equivalent circuit fitting | R, C, W parameters |
| cv_peaks | CV peak detection | peak positions, currents |
| distribution | Distribution fitting | best-fit distribution + params |
| outlier | Outlier detection | flagged data points |

## Input

```json
{
  "analysis_type": "summary",
  "data": "path/to/data.csv or inline JSON",
  "columns": ["col1", "col2"],
  "options": {}
}
```

## Output

```json
{
  "status": "complete",
  "analysis_type": "summary",
  "results": {
    "shape": [100, 5],
    "statistics": {},
    "missing_values": {},
    "dtypes": {}
  },
  "artifacts": ["analysis_report.json", "figures/distribution.png"]
}
```
