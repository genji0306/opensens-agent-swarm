---
name: darklab-unipat-swarm
description: >
  UniScientist-style polymathic scientific research agent — runs the UniPat-AI
  iterative agentic research loop (web search, Google Scholar, page fetching,
  code interpreter) against a local Ollama-hosted LLM (Gemma 4 or Qwen) on the
  Leader Mac mini. Produces research-grade reports across 50+ scientific
  disciplines using Serper / Jina / code-exec tools and candidate aggregation.
metadata:
  {"openclaw": {"emoji": "microscope", "requires": {"env": ["SERPER_KEY_ID", "JINA_API_KEYS"]}}}
---

# DarkLab UniPat Swarm Agent

Brings the UniScientist (UniPat-AI) methodology to the DarkLab cluster:
polymathic cross-disciplinary research with an iterative evidence-acquisition
loop and candidate report aggregation — running against **local Ollama**
(Gemma 4 / Qwen) instead of the upstream 30B vLLM deployment, so it fits on a
Mac mini 16GB.

Upstream: https://github.com/UniPat-AI/UniScientist

## Commands

```
/unipat <research question>       — run full agentic research loop + aggregate
/unipat status                    — show model + tool health
/unipat rollout <N> <question>    — generate N candidate rollouts and merge
/unipat tools                     — list available research tools
```

## Architecture

Three-stage pipeline (from UniScientist paper):

1. **Evolving Polymathic Synthesis** — LLM generates research sub-problems
   with co-evolved evaluation rubrics
2. **Agentic Research Loop** — iterative evidence acquisition using tools:
   - `web_search` (Serper API)
   - `google_scholar` (Serper API)
   - `page_fetching` (Jina Reader API)
   - `code_interpreter` (sandboxed Python exec)
3. **Report Aggregation** — synthesizes multiple candidate reports into a
   consolidated finding (best-of-N majority + rubric scoring)

## Local Deployment (Mac Mini 16GB)

UniScientist upstream uses `UniScientist-30B-A3B` (MoE, 30B total / ~3B active)
deployed via vLLM on port 8000. **A raw 30B model will not fit in 16GB.**
DarkLab adaptation:

| Upstream | DarkLab Leader |
|----------|----------------|
| `UniScientist-30B-A3B` (vLLM, ~18GB VRAM) | `gemma3:12b` or `qwen2.5:14b` (Ollama, ~8GB) |
| vLLM OpenAI server :8000 | Ollama :11434 (OpenAI-compatible) |
| NVIDIA GPU | Apple Silicon / MLX via Ollama auto-acceleration |
| vLLM rollout scripts | UniScientist agentic loop pointed at `OLLAMA_BASE_URL` |
| SERPER_KEY_ID / JINA_API_KEYS / OPENROUTER_API_KEY | Same, loaded from `~/.darklab/.env` |

The **agentic research loop code** from UniScientist is retained — only the
underlying model endpoint changes.

## Required API Keys

Place in `~/.darklab/.env`:
```
SERPER_KEY_ID=...          # Google web/Scholar search
JINA_API_KEYS=...          # page content extraction
OPENROUTER_API_KEY=...     # optional summarization fallback
OLLAMA_BASE_URL=http://localhost:11434/v1
UNIPAT_MODEL=gemma3:12b    # or qwen2.5:14b
```

## Usage Examples

### Local dev
```bash
PYTHONPATH=core:cluster/agents .venv/bin/python -m leader.unipat_swarm_cmd \
  '{"task_type":"unipat_swarm","payload":{"text":"Optimal electrolytes for lithium-sulfur batteries at sub-zero temperatures"}}'
```

### Leader HTTP dispatch
```bash
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -d '{"command":"unipat","args":"Mechanisms of catalyst deactivation in ammonia synthesis"}'
```

### Telegram / PicoClaw
```
/unipat What are the binding affinities of recent PROTAC degraders?
/unipat rollout 3 Crystal structure prediction accuracy of MACE-MP-0
/unipat tools
```

## Integration with OAS

UniPat-swarm complements the existing OAS research stack:

| Tool | Best For |
|------|---------|
| `/deepresearch` | OAS native iterative research (9 academic sources) |
| `/swarmresearch` | 5-angle parallel OAS research |
| `/unipat` | **Polymathic cross-disciplinary** research with UniScientist-style rubrics + candidate aggregation |
| `/gemma-swarm` | Raw local model call (no research loop, no aggregation) |

Results land in the shared knowledge base alongside other research outputs.

## Key References

- [UniPat-AI/UniScientist (GitHub)](https://github.com/UniPat-AI/UniScientist)
- [Serper API](https://serper.dev/)
- [Jina Reader API](https://jina.ai/reader/)
- [Ollama OpenAI compatibility](https://ollama.com/blog/openai-compatibility)
- [2026-04-04 Gemma+Claude Swarm v2 Report](../../../results/research/2026-04-04_Gemma-Claude-Agent-Swarm-v2-Research.md)
