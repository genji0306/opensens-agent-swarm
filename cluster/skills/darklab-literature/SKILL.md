---
name: darklab-literature
description: Deep literature reviews using Perplexity (browser/API) and Gemini, with structured citation management.
metadata:
  {"openclaw": {"emoji": "books", "requires": {"env": ["ANTHROPIC_API_KEY"]}}}
---

# DarkLab Literature Agent

Performs deep, multi-source literature reviews with structured citation output.

## Capabilities

- Search academic databases via Perplexity Pro
- Cross-reference findings with Gemini
- Extract key parameters from papers
- Build citation libraries
- Identify methodological patterns

## Search Strategy

1. **Broad search**: Perplexity for recent papers and reviews
2. **Targeted search**: Specific authors, methods, materials
3. **Cross-validation**: Gemini verifies key claims
4. **Parameter extraction**: Pull numerical parameters from abstracts

## Output Format

```json
{
  "query": "string",
  "papers_found": 25,
  "top_papers": [
    {
      "title": "string",
      "authors": ["string"],
      "year": 2025,
      "doi": "string",
      "abstract_summary": "string",
      "key_parameters": {"param": "value"},
      "relevance_score": 0.92
    }
  ],
  "methodology_patterns": ["string"],
  "parameter_ranges": {"param": {"min": 0, "max": 100, "unit": "string"}}
}
```
