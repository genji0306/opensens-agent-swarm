---
name: darklab-research
description: Literature search, gap analysis, and research framing using multi-AI (Claude, Perplexity, Gemini).
metadata:
  {"openclaw": {"emoji": "search", "requires": {"env": ["ANTHROPIC_API_KEY"]}}}
---

# DarkLab Research Agent

Performs comprehensive literature research using multiple AI services for robust results.

## Workflow

1. Receive research topic from Leader
2. Search literature via Perplexity (web) and Gemini (cross-validation)
3. Identify research gaps and opportunities
4. Structure findings into a research framework
5. Return structured plan to Leader

## AI Usage

- **Perplexity**: Real-time web search with citations (via darklab-perplexity skill or API)
- **Gemini**: Cross-validate findings, alternative perspectives
- **Claude**: Structure analysis, gap identification, plan generation

## Available Scientific Skills

When installed (via `~/.claude/skills/`), the research agent can leverage:

- **pubmed-database**: Search PubMed for biomedical literature
- **arxiv-database**: Search arXiv for preprints in physics, CS, math
- **biorxiv-database**: Search bioRxiv/medRxiv for biology preprints
- **citation-management**: Manage references and generate bibliographies
- **scientific-writing**: Academic paper formatting and style guidance

These skills are installed from [K-Dense-AI/claude-scientific-skills](https://github.com/K-Dense-AI/claude-scientific-skills).

## Output Format

```json
{
  "topic": "string",
  "summary": "string",
  "key_findings": ["string"],
  "research_gaps": ["string"],
  "proposed_approach": "string",
  "citations": [{"title": "string", "url": "string", "relevance": "string"}],
  "confidence": 0.85
}
```

## Example

```
/research MnO2 nanoparticle synthesis for supercapacitor electrodes
```

Returns a structured plan covering synthesis methods, characterization approaches, and identified gaps in the literature.
