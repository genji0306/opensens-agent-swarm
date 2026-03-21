---
name: darklab-report-data
description: Generate publication-quality figures, data tables, and statistical summaries for research reports.
metadata:
  {"openclaw": {"emoji": "chart_with_upwards_trend", "requires": {"env": ["ANTHROPIC_API_KEY"], "bins": ["python3"]}}}
---

# DarkLab Report Data Agent

Creates publication-quality data visualizations and formatted data tables.

## Capabilities

- Generate matplotlib/plotly figures from data
- Create formatted data tables (LaTeX, Markdown, HTML)
- Statistical summary tables
- Correlation heatmaps
- Time-series plots
- Parameter sweep visualizations

## Figure Types

| Type | Library | Output |
|------|---------|--------|
| scatter | matplotlib | PNG/SVG |
| heatmap | matplotlib/seaborn | PNG/SVG |
| line | plotly | HTML/PNG |
| bar | matplotlib | PNG/SVG |
| violin | matplotlib | PNG/SVG |
| 3d_surface | plotly | HTML |
| histogram | matplotlib | PNG/SVG |

## Input

```json
{
  "data": "path/to/data.csv or inline JSON",
  "figures": [
    {"type": "scatter", "x": "temperature", "y": "yield", "color": "catalyst"},
    {"type": "heatmap", "columns": ["temp", "time", "yield"]}
  ],
  "tables": [
    {"type": "summary_statistics", "columns": ["yield", "purity"]},
    {"type": "formatted", "format": "latex"}
  ],
  "style": "publication",
  "dpi": 300
}
```

## Output

```json
{
  "figures": [
    {"type": "scatter", "path": "figures/scatter_temp_yield.png", "caption": "string"},
    {"type": "heatmap", "path": "figures/correlation_heatmap.png", "caption": "string"}
  ],
  "tables": [
    {"type": "summary", "path": "tables/summary_stats.tex", "data": {}}
  ]
}
```
