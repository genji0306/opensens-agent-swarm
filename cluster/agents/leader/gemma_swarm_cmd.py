"""Gemma Swarm command handler — local Ollama-hosted Gemma workers.

Routes /gemma-swarm commands to a local Ollama endpoint (OpenAI-compatible).
Provides chat, status, model pull, and micro-benchmark operations for
on-device Gemma 4 (or Gemma 3 QAT fallback) workers running on the Leader.

Usage:
  /gemma-swarm <prompt>           — chat completion against local Gemma
  /gemma-swarm status             — list available models + endpoint health
  /gemma-swarm pull <model>       — download a Gemma model via Ollama
  /gemma-swarm bench              — simple tokens/sec benchmark
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from shared.models import Task, TaskResult

__all__ = ["handle"]

logger = logging.getLogger("darklab.gemma_swarm_cmd")

# ── Config ──────────────────────────────────────────────────────────

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("GEMMA_DEFAULT_MODEL", "gemma3:4b")
BENCH_PROMPT = (
    "Summarize in three sentences why the Apple Neural Engine is useful "
    "for running small language models on-device."
)

# Preferred models in priority order (first one that exists wins for defaults)
PREFERRED_MODELS = [
    "gemma4:e4b",       # Gemma 4 PLE edge (when Ollama ships it)
    "gemma4:e2b",
    "gemma3:12b",       # Current QAT default for quality workers
    "gemma3:4b",        # Current QAT default for light workers
    "gemma3:27b",
]


# ── Handler ─────────────────────────────────────────────────────────

async def handle(task: Task) -> TaskResult:
    """Handle /gemma-swarm command."""
    text = (task.payload.get("text") or "").strip()
    args = (task.payload.get("args") or "").strip()
    body = args or text

    if not body or body in ("status", "/gemma-swarm"):
        return await _handle_status(task)

    parts = body.split(None, 1)
    verb = parts[0].lower().lstrip("/")

    if verb == "status":
        return await _handle_status(task)
    if verb == "bench" or verb == "benchmark":
        return await _handle_bench(task, parts[1] if len(parts) > 1 else DEFAULT_MODEL)
    if verb == "pull":
        model_name = parts[1].strip() if len(parts) > 1 else DEFAULT_MODEL
        return await _handle_pull(task, model_name)

    # Default: chat completion against default model
    return await _handle_chat(task, body)


# ── Operations ──────────────────────────────────────────────────────

async def _handle_status(task: Task) -> TaskResult:
    """Report Ollama endpoint health and available Gemma models."""
    try:
        import httpx
    except ImportError:
        return _error(task, "httpx not installed; install via `uv pip install httpx`")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return TaskResult(
            task_id=task.task_id,
            agent_name="gemma-swarm",
            status="error",
            result={
                "error": f"Ollama unreachable at {OLLAMA_BASE_URL}: {exc}",
                "endpoint": OLLAMA_BASE_URL,
                "hint": "Start Ollama with `ollama serve` and verify with `ollama list`.",
            },
        )

    models = data.get("models", [])
    gemma_models = [m for m in models if "gemma" in m.get("name", "").lower()]

    return TaskResult(
        task_id=task.task_id,
        agent_name="gemma-swarm",
        status="ok",
        result={
            "endpoint": OLLAMA_BASE_URL,
            "endpoint_healthy": True,
            "total_models": len(models),
            "gemma_models": [
                {
                    "name": m.get("name"),
                    "size_gb": round(m.get("size", 0) / 1e9, 2),
                    "modified_at": m.get("modified_at"),
                }
                for m in gemma_models
            ],
            "default_model": DEFAULT_MODEL,
            "preferred_order": PREFERRED_MODELS,
        },
    )


async def _handle_chat(task: Task, prompt: str, model: str | None = None) -> TaskResult:
    """Run a chat completion against the local Ollama endpoint."""
    try:
        import httpx
    except ImportError:
        return _error(task, "httpx not installed")

    model = model or DEFAULT_MODEL

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return _error(task, f"Ollama chat failed: {exc}")
    duration = time.monotonic() - start

    choices = data.get("choices", [])
    content = choices[0].get("message", {}).get("content", "") if choices else ""
    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    tok_per_sec = (completion_tokens / duration) if duration > 0 and completion_tokens else None

    return TaskResult(
        task_id=task.task_id,
        agent_name="gemma-swarm",
        status="ok",
        result={
            "model": model,
            "output": content,
            "duration_seconds": round(duration, 2),
            "tokens": usage,
            "tokens_per_second": round(tok_per_sec, 1) if tok_per_sec else None,
            "endpoint": OLLAMA_BASE_URL,
        },
    )


async def _handle_bench(task: Task, model: str) -> TaskResult:
    """Quick micro-benchmark: run BENCH_PROMPT and report tokens/sec."""
    result = await _handle_chat(task, BENCH_PROMPT, model=model)
    if result.status == "ok":
        result.result["benchmark_prompt"] = BENCH_PROMPT
        result.result["benchmark_mode"] = True
    return result


async def _handle_pull(task: Task, model: str) -> TaskResult:
    """Trigger an Ollama model pull. Returns immediately — streams in background."""
    try:
        import httpx
    except ImportError:
        return _error(task, "httpx not installed")

    # /api/pull streams status; we consume the stream and summarize.
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=1800.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"name": model, "stream": True},
            ) as resp:
                resp.raise_for_status()
                final_status = "unknown"
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                        final_status = msg.get("status", final_status)
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:
        return _error(task, f"Ollama pull failed: {exc}")
    duration = time.monotonic() - start

    return TaskResult(
        task_id=task.task_id,
        agent_name="gemma-swarm",
        status="ok",
        result={
            "model": model,
            "final_status": final_status,
            "duration_seconds": round(duration, 1),
            "endpoint": OLLAMA_BASE_URL,
        },
    )


def _error(task: Task, message: str) -> TaskResult:
    return TaskResult(
        task_id=task.task_id,
        agent_name="gemma-swarm",
        status="error",
        result={"error": message},
    )


if __name__ == "__main__":
    from shared.node_bridge import run_agent

    run_agent(handle, agent_name="GemmaSwarm")
