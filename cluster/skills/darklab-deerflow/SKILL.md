---
name: darklab-deerflow
description: Deep multi-step research orchestrator powered by DeerFlow 2.0. Spawns sub-agents for literature review, data analysis, and artifact generation (reports, slides, web pages).
metadata:
  {"openclaw": {"emoji": "deer", "requires": {"env": ["ANTHROPIC_API_KEY"], "bins": ["python3"]}}}
---

# DarkLab DeerFlow Research Orchestrator

Deep research agent powered by ByteDance's DeerFlow 2.0 super agent harness.
Runs as an embedded client within the OAS pipeline, using DeerFlow's sub-agent
orchestration, skill system, and sandbox to produce comprehensive research artifacts.

## Workflow

1. Receive a research objective
2. DeerFlow's lead agent decomposes the objective into sub-tasks
3. Sub-agents execute in parallel (max 2 concurrent on M4 16GB)
4. Skills provide domain expertise (research, report generation, web search)
5. Results synthesized into structured output with artifacts
6. All events flow through DRVP for real-time visualization

## Input

```json
{
  "query": "Research the latest advances in on-device LLM inference on Apple Silicon",
  "model": "optional — override model (claude-sonnet, gemini-boost, ollama-local)",
  "files": ["optional local file paths to upload for analysis"],
  "thread_id": "optional — reuse existing DeerFlow thread for multi-turn",
  "thinking": true,
  "subagents": true
}
```

## Output

```json
{
  "output": "Full research output text",
  "thread_id": "deerflow-thread-id",
  "model": "claude-sonnet",
  "artifacts": ["report.md", "figures/chart.png"]
}
```

## Model Routing

Respects the OAS tiered model router:
- **PLANNING tier** → `claude-sonnet` (Anthropic API, paid)
- **BOOST tier** → `gemini-boost` (AIClient-2-API, free client accounts)
- **EXECUTION tier** → `ollama-local` (Ollama on Leader, free)

## Capabilities

- Multi-step research with automatic sub-task decomposition
- Literature review with web search and academic databases
- Data analysis with code execution in sandbox
- Report generation (Markdown, structured output)
- Long-term memory across research sessions
- File upload and artifact collection
- MCP server integration (bioRxiv, GitHub, etc.)

## Resource Constraints (M4 16GB)

- Max 2 concurrent sub-agents (reduced from DeerFlow default of 3)
- Summarization enabled to manage context window
- Memory capped at 50 facts
- DeerFlow memory debounce: 60 seconds

## Example

```
/deerflow Research the impact of quantization techniques on LLM accuracy for edge deployment on Apple Silicon
/deerflow Analyze these papers and generate a comparison report
/deerflow Plan a study on federated learning for medical imaging
```
