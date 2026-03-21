---
name: darklab-media-gen
description: Generate multimedia research output -- Word documents, presentations, infographics, and formatted reports using Claude OPUS and Gemini.
metadata:
  {"openclaw": {"emoji": "art", "requires": {"env": ["ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY"]}}}
---

# DarkLab Media Generator

Creates final multimedia deliverables from synthesized research results.

## Output Types

| Type | Format | AI Used |
|------|--------|---------|
| Research report | Word (.docx) / PDF | Claude OPUS |
| Presentation | Markdown slides / PPTX | Gemini |
| Infographic | SVG / PNG | Gemini + DALL-E |
| Data visualization | Interactive HTML (Plotly) | Python + Claude |
| Audio summary | MP3 (via NotebookLM) | NotebookLM |

## Input

```json
{
  "synthesis": {},
  "output_types": ["report", "presentation", "infographic"],
  "style": "academic|executive|technical",
  "branding": {"logo": "path", "colors": ["#hex"]}
}
```

## Output

```json
{
  "deliverables": [
    {"type": "report", "path": "output/research_report.docx", "pages": 15},
    {"type": "presentation", "path": "output/slides.pptx", "slides": 12},
    {"type": "infographic", "path": "output/infographic.png"}
  ]
}
```

## Notes

- Word documents generated using python-docx
- Presentations use structured markdown that can be converted to PPTX
- For audio/video summaries, delegates to darklab-notebooklm skill
