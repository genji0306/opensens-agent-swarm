---
name: darklab-paper
description: Draft research papers and manuscripts from analyzed data using OpenAI and Gemini for multi-perspective writing.
metadata:
  {"openclaw": {"emoji": "memo", "requires": {"env": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]}}}
---

# DarkLab Paper Agent

Drafts research papers and reports from analyzed experimental and simulation data.

## Capabilities

- Draft paper sections (abstract, introduction, methods, results, discussion, conclusion)
- Format citations in standard academic styles (APA, ACS, Nature)
- Generate LaTeX or Word-compatible output
- Cross-validate claims using multiple AI services
- Create supplementary information sections

## Multi-AI Writing Strategy

1. **Claude OPUS**: Primary writing engine for coherent long-form text
2. **OpenAI GPT-4o**: Cross-validation, alternative phrasings, fact-checking
3. **Gemini**: Literature context verification, citation accuracy

## Input

```json
{
  "title": "string",
  "data": {},
  "research_plan": {},
  "figures": ["path/to/fig1.png"],
  "target_journal": "string",
  "format": "latex|docx"
}
```

## Output

```json
{
  "manuscript": {
    "title": "string",
    "abstract": "string (250 words)",
    "sections": [
      {"heading": "Introduction", "content": "string"},
      {"heading": "Methods", "content": "string"},
      {"heading": "Results", "content": "string"},
      {"heading": "Discussion", "content": "string"},
      {"heading": "Conclusion", "content": "string"}
    ],
    "references": ["formatted citation strings"],
    "word_count": 5000
  },
  "artifacts": ["manuscript.tex", "manuscript.docx"]
}
```
