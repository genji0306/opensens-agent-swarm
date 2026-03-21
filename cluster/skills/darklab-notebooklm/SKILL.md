---
name: darklab-notebooklm
description: Generate audio summaries, video overviews, and study guides using Google NotebookLM via browser automation.
metadata:
  {"openclaw": {"emoji": "notebook", "requires": {"bins": ["google-chrome"]}, "os": ["darwin"]}}
---

# DarkLab NotebookLM

Automates Google NotebookLM via browser control to generate multimedia research summaries.

## Prerequisites

- Google Chrome installed
- Chrome profile `notebooklm-research` logged into a Google account with NotebookLM access
- Profile path: `~/.darklab/browser-profiles/notebooklm-research`

## Capabilities

- Upload source documents (PDFs, text files) to a NotebookLM notebook
- Generate audio overviews (podcast-style summaries)
- Create study guides from research materials
- Extract structured summaries

## Workflow

1. Open Chrome with the `notebooklm-research` profile
2. Navigate to `notebooklm.google.com`
3. Create a new notebook or open an existing one
4. Upload source documents
5. Trigger the desired generation (audio overview, study guide, etc.)
6. Wait for generation to complete
7. Download the generated assets
8. Return file paths

## Input

```json
{
  "sources": ["path/to/report.pdf", "path/to/data_summary.txt"],
  "generate": ["audio_overview", "study_guide"],
  "notebook_name": "MnO2 Research Summary"
}
```

## Output

```json
{
  "notebook_url": "https://notebooklm.google.com/notebook/...",
  "artifacts": [
    {"type": "audio_overview", "path": "output/audio_summary.mp3", "duration_sec": 300},
    {"type": "study_guide", "path": "output/study_guide.md"}
  ]
}
```

## Notes

- This skill requires browser automation (no NotebookLM API exists)
- Uses OpenClaw's `pw-ai-module.ts` for resilient UI interaction via screenshot + LLM vision
- Generation can take several minutes; the skill handles waiting
