---
name: darklab-perplexity
description: Web research queries using Perplexity AI -- API-first with browser automation fallback for Pro features.
metadata:
  {"openclaw": {"emoji": "globe_with_meridians", "requires": {"bins": ["python3"]}}}
---

# DarkLab Perplexity

Performs real-time web research via Perplexity AI with structured citation output.

## Access Methods

1. **API (preferred)**: If `PERPLEXITY_API_KEY` is set, uses the Perplexity API directly
2. **Browser (fallback)**: Uses Chrome profile `perplexity-research` for Pro features

## API Usage

```python
import httpx

response = await httpx.AsyncClient().post(
    "https://api.perplexity.ai/chat/completions",
    headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}"},
    json={
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [{"role": "user", "content": query}]
    }
)
```

## Browser Usage (browser-use)

When the API is unavailable, the skill falls back to [browser-use](https://github.com/browser-use/browser-use) for LLM-driven browser automation:

1. Launch Chrome with `perplexity-research` user-data-dir (separate from OpenClaw's CDP)
2. Navigate to `perplexity.ai` with the query
3. LLM perceives DOM + screenshot, decides actions autonomously
4. Extract text and citations via custom Controller actions
5. Save citations to `~/.darklab/data/citations.jsonl`

This replaces the previous brittle Playwright selectors with a vision-capable agent that adapts to UI changes.

### Custom Controller Actions

- `save_citation(title, url, authors, year)` — appends to citations JSONL
- `download_pdf(url)` — saves PDFs to `~/.darklab/artifacts/`

## Input

```json
{
  "query": "Recent advances in MnO2 nanoparticle synthesis for supercapacitors",
  "focus": "academic",
  "max_results": 10
}
```

## Output

```json
{
  "query": "string",
  "answer": "string (comprehensive summary)",
  "citations": [
    {"title": "string", "url": "string", "snippet": "string"}
  ],
  "follow_up_questions": ["string"]
}
```
