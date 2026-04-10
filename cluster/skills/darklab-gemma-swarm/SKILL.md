---
name: darklab-gemma-swarm
description: >
  On-device Gemma 4 agent worker swarm — routes research, literature, analysis,
  and tool-use tasks to local Ollama-hosted Gemma 4 models on the Mac mini
  Leader. Uses native function calling, Per-Layer Embeddings (PLE) efficiency,
  and 128K-256K context for zero-cost agentic workflows. Can be combined with
  Claude cloud orchestrator via hybrid routing or run fully offline.
metadata:
  {"openclaw": {"emoji": "sparkles", "requires": {"env": []}}}
---

# DarkLab Gemma Swarm Agent

Runs local Gemma 4 (E4B / 12B / 26B MoE) via Ollama as on-device agent workers
with native function calling and structured JSON output. Designed for zero-cost
research, literature, analysis, and tool-use tasks on the Leader Mac mini
(16GB unified memory).

Based on findings from the 2026-04-04 full swarm research run combining
Google Gemma 4 (February 2026 release, Apache 2.0) with Claude Code
architectural patterns from the March 2026 source leak.

## Commands

```
/gemma-swarm <prompt>             — chat / function-call against local Gemma
/gemma-swarm status               — show available local models + health
/gemma-swarm pull <model>         — download a Gemma model via Ollama
/gemma-swarm bench                — quick token/sec benchmark on Leader
```

## Models Available on Leader

| Model | Active / Total | Memory (Q4) | Context | Use Case |
|-------|----------------|-------------|---------|----------|
| `gemma3:4b` | 4B | ~3.0 GB | 128K | Light workers, fast iteration |
| `gemma3:12b` | 12B | ~7.2 GB | 128K | Standard workers, analysis |
| `gemma3:27b` | 27B | ~16 GB | 128K | High-quality (single-slot) |

(Gemma 4 PLE variants — `gemma4:e2b`, `gemma4:e4b` — pulled if Ollama release
available. Fallback to Gemma 3 QAT models if not.)

## Key Architecture

### Per-Layer Embeddings (PLE)
Secondary embedding table feeds a small residual signal into **every** decoder
layer. E4B runs with 4B effective params but carries representational depth of
~9B. Result: 3–4 Gemma workers fit in 16GB with TurboQuant KV compression.

### Native Function Calling
Gemma 4 follows the standard OpenAI function-calling format via Ollama API.
No template hacks needed — the model outputs structured JSON tool calls that
map directly to OAS dispatch commands.

### Hybrid Attention
Interleaved local sliding-window + full global attention (final layer always
global). Delivers low memory footprint without sacrificing long-context
awareness.

## Ollama Integration

```bash
# Leader Mac mini (16GB)
ollama pull gemma3:4b              # default worker
ollama pull gemma3:12b             # analysis worker
ollama serve                        # OpenAI-compatible endpoint on :11434

# Client (Python)
from openai import AsyncOpenAI
client = AsyncOpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",  # Ollama ignores auth but SDK requires a value
)
response = await client.chat.completions.create(
    model="gemma3:4b",
    messages=[{"role": "user", "content": "Summarize: ..."}],
    tools=[...],  # native function calling
)
```

## Hybrid Routing (OAS v2)

```
Claude Sonnet (cloud orchestrator)
    │
    ▼  Task complexity score
┌───┴────┐
│ < 0.3  │ → Gemma 3 4B  (local, $0)
│ 0.3–0.7│ → Gemma 3 12B (local, $0)
│ > 0.7  │ → Claude Sonnet/Opus (cloud, $$)
└────────┘
```

**Cost impact**: 77% reduction ($150/mo → $35/mo) for daily research swarm
operation by routing literature / research / DOE / analysis to local Gemma.

## Usage Examples

### Local dev
```bash
PYTHONPATH=core:cluster/agents .venv/bin/python -m leader.gemma_swarm_cmd \
  '{"task_type":"gemma_swarm","payload":{"text":"Summarize latest quantum sensor papers"}}'
```

### Leader HTTP dispatch
```bash
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -d '{"command":"gemma-swarm","args":"Summarize MXenes synthesis progress 2026"}'
```

### Telegram / PicoClaw
```
/gemma-swarm What are the latest findings on perovskite stability?
/gemma-swarm bench
/gemma-swarm status
```

## Key References

- [Google Blog — Gemma 4](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)
- [HuggingFace — Welcome Gemma 4](https://huggingface.co/blog/gemma4)
- [Ollama — Gemma 4 Library](https://ollama.com/library/gemma4)
- [Superagentic AI — Gemma 4 with MLX](https://shashikantjagtap.net/gemma-4-with-mlx-for-local-agentic-ai-at-superagentic-ai/)
- [2026-04-04 Gemma+Claude Swarm v2 Report](../../../results/research/2026-04-04_Gemma-Claude-Agent-Swarm-v2-Research.md)
