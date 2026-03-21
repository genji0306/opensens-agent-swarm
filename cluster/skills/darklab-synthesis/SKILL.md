---
name: darklab-synthesis
description: Synthesize multi-source research results into coherent narratives, executive summaries, and structured reports.
metadata:
  {"openclaw": {"emoji": "link", "requires": {"env": ["ANTHROPIC_API_KEY"]}}}
---

# DarkLab Synthesis Agent

Combines research findings, simulation results, and data analyses into coherent, publication-ready narratives.

## Capabilities

- Merge findings from multiple research queries
- Cross-reference results with original research plans
- Generate executive summaries
- Identify inconsistencies between sources
- Create structured report outlines

## Input

```json
{
  "research_results": {},
  "simulation_data": {},
  "analysis_results": {},
  "original_plan": {},
  "output_format": "narrative|executive_summary|structured_report"
}
```

## Output

```json
{
  "synthesis": {
    "executive_summary": "string (300 words)",
    "key_findings": ["string"],
    "methodology_validation": "string",
    "data_consistency": {"score": 0.92, "issues": []},
    "recommendations": ["string"],
    "full_narrative": "string (2000+ words)"
  }
}
```

## Notes

- Uses Claude OPUS for high-quality narrative generation
- Cross-references all claims with cited sources
- Flags any inconsistencies between research and simulation results
