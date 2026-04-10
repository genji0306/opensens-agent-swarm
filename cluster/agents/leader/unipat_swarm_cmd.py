"""UniPat Swarm command handler — UniScientist-style polymathic research loop.

Native Python port of the UniScientist agentic research pipeline running
against a local Ollama endpoint (OpenAI-compatible). Produces research-grade
reports using Serper (web + Scholar), Jina (page fetch), code interpreter,
and best-of-N candidate aggregation.

Upstream: https://github.com/UniPat-AI/UniScientist
Adaptation: replaces the upstream 30B vLLM with local Ollama (Gemma 4 E4B).

Usage:
  /unipat <research question>       — full research loop + aggregation
  /unipat status                    — model + tool health
  /unipat rollout <N> <question>    — N candidate rollouts, then merge
  /unipat tools                     — list available research tools
"""
from __future__ import annotations

import io
import json
import logging
import os
import time
from contextlib import redirect_stdout, redirect_stderr
from typing import Any

from shared.models import Task, TaskResult

__all__ = ["handle"]

logger = logging.getLogger("darklab.unipat_swarm_cmd")

# ── Config ──────────────────────────────────────────────────────────

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
UNIPAT_MODEL = os.environ.get("UNIPAT_MODEL", "gemma3:12b")
SERPER_KEY_ID = os.environ.get("SERPER_KEY_ID", "")
JINA_API_KEYS = os.environ.get("JINA_API_KEYS", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

DEFAULT_ROLLOUTS = 3
MAX_ROLLOUTS = 8
MAX_LOOP_STEPS = 8

SYSTEM_PROMPT = """You are an AI scientist. Your job is to solve the user's research problem as accurately as possible.
Use the provided tools wisely to gather missing or uncertain information, verify claims, and obtain relevant evidence. Prefer tool calls when they materially improve correctness, completeness, or confidence.

When you have gathered enough evidence, write a comprehensive research report with:
1. Executive summary (2-3 sentences)
2. Key findings with citations
3. Methodology (which sources and searches you used)
4. Detailed analysis
5. Limitations and future directions
6. References (URLs and titles)

Be thorough but concise. Cite all sources."""

TOOL_DEFS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search Google for web results. Use for general queries, news, and discovery.",
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of search queries (1-3 recommended).",
                    }
                },
                "required": ["queries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "google_scholar",
            "description": "Search Google Scholar for academic papers and citations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of academic search queries.",
                    }
                },
                "required": ["queries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "page_fetch",
            "description": "Fetch and extract clean text content from a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_interpreter",
            "description": "Execute a short Python snippet for computation, data parsing, or analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."}
                },
                "required": ["code"],
            },
        },
    },
]

AVAILABLE_TOOLS = [
    {"name": "web_search", "provider": "Serper API", "description": "Google web search", "requires_env": "SERPER_KEY_ID"},
    {"name": "google_scholar", "provider": "Serper API", "description": "Google Scholar", "requires_env": "SERPER_KEY_ID"},
    {"name": "page_fetch", "provider": "Jina Reader API", "description": "Extract text from URL", "requires_env": "JINA_API_KEYS"},
    {"name": "code_interpreter", "provider": "local Python", "description": "Execute Python snippets", "requires_env": None},
]


# ── Tool Implementations ────────────────────────────────────────────

async def _tool_web_search(queries: list[str]) -> str:
    """Serper web search — returns formatted results."""
    import httpx

    all_results: list[str] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for q in queries[:3]:
            try:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": SERPER_KEY_ID, "Content-Type": "application/json"},
                    json={"q": q, "num": 5},
                )
                resp.raise_for_status()
                data = resp.json()
                for r in data.get("organic", [])[:5]:
                    title = r.get("title", "")
                    link = r.get("link", "")
                    snippet = r.get("snippet", "")
                    all_results.append(f"- [{title}]({link})\n  {snippet}")
            except Exception as exc:
                all_results.append(f"- Search error for '{q}': {exc}")
    return "\n".join(all_results) if all_results else "No results found."


async def _tool_google_scholar(queries: list[str]) -> str:
    """Serper Scholar search — returns formatted academic results."""
    import httpx

    all_results: list[str] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for q in queries[:3]:
            try:
                resp = await client.post(
                    "https://google.serper.dev/scholar",
                    headers={"X-API-KEY": SERPER_KEY_ID, "Content-Type": "application/json"},
                    json={"q": q, "num": 5},
                )
                resp.raise_for_status()
                data = resp.json()
                for r in data.get("organic", [])[:5]:
                    title = r.get("title", "")
                    link = r.get("link", "")
                    snippet = r.get("snippet", "")
                    year = r.get("year", "")
                    cited_raw = r.get("citedBy", 0)
                    cited = cited_raw.get("total", 0) if isinstance(cited_raw, dict) else cited_raw
                    all_results.append(
                        f"- [{title}]({link}) ({year}, cited: {cited})\n  {snippet}"
                    )
            except Exception as exc:
                all_results.append(f"- Scholar error for '{q}': {exc}")
    return "\n".join(all_results) if all_results else "No scholar results found."


async def _tool_page_fetch(url: str) -> str:
    """Jina Reader — extract clean markdown from a URL."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"https://r.jina.ai/{url}",
                headers={"Authorization": f"Bearer {JINA_API_KEYS}"},
            )
            resp.raise_for_status()
            text = resp.text
            # Truncate to first 6000 chars to stay within context budget
            return text[:6000] if len(text) > 6000 else text
    except Exception as exc:
        return f"Page fetch error: {exc}"


def _tool_code_interpreter(code: str) -> str:
    """Sandboxed Python execution — captures stdout, blocks dangerous ops."""
    forbidden = ["import os", "import sys", "import subprocess", "open(", "__import__", "eval(", "exec("]
    for kw in forbidden:
        if kw in code:
            return f"Blocked: '{kw}' is not allowed in sandboxed execution."

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(code, {"__builtins__": {"print": print, "range": range, "len": len, "sum": sum,
                                          "min": min, "max": max, "sorted": sorted, "enumerate": enumerate,
                                          "zip": zip, "map": map, "filter": filter, "str": str,
                                          "int": int, "float": float, "list": list, "dict": dict,
                                          "set": set, "tuple": tuple, "round": round, "abs": abs,
                                          "True": True, "False": False, "None": None}})
        output = stdout_buf.getvalue()
        return output if output else "(executed successfully, no output)"
    except Exception as exc:
        return f"Execution error: {exc}"


async def _execute_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a tool call by name and return the result string."""
    if name == "web_search":
        return await _tool_web_search(arguments.get("queries", []))
    elif name == "google_scholar":
        return await _tool_google_scholar(arguments.get("queries", []))
    elif name == "page_fetch":
        return await _tool_page_fetch(arguments.get("url", ""))
    elif name == "code_interpreter":
        return _tool_code_interpreter(arguments.get("code", ""))
    return f"Unknown tool: {name}"


# ── Agentic Research Loop ───────────────────────────────────────────

async def _run_research_loop(question: str) -> dict[str, Any]:
    """Run a single UniScientist-style research rollout.

    Loop: send messages + tools to Gemma → if tool_calls, execute and append
    results → repeat until model returns a final report (content, no tool_calls)
    or MAX_LOOP_STEPS is reached.
    """
    import httpx

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tool_calls_log: list[dict[str, str]] = []
    loop_step = 0

    async with httpx.AsyncClient(timeout=300.0) as client:
        while loop_step < MAX_LOOP_STEPS:
            loop_step += 1
            logger.info("unipat_loop_step: %d", loop_step)

            payload: dict[str, Any] = {
                "model": UNIPAT_MODEL,
                "messages": messages,
                "tools": TOOL_DEFS,
                "tool_choice": "auto",
                "max_tokens": 4096,
            }

            try:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/v1/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error("unipat_llm_error: %s", exc)
                return {"output": f"LLM call failed at step {loop_step}: {exc}",
                        "tool_calls": tool_calls_log, "steps": loop_step, "error": True}

            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")

            # If the model returned tool calls, execute them
            calls = msg.get("tool_calls")
            if calls:
                # Append assistant message with tool calls
                messages.append(msg)
                for tc in calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    try:
                        fn_args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        fn_args = {}

                    logger.info("unipat_tool_call: %s(%s)", fn_name, list(fn_args.keys()))
                    result_str = await _execute_tool_call(fn_name, fn_args)
                    tool_calls_log.append({"tool": fn_name, "args_keys": list(fn_args.keys()),
                                           "result_preview": result_str[:200]})

                    # Append tool result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{loop_step}"),
                        "content": result_str[:8000],
                    })
                continue  # Next loop iteration — model will see tool results

            # Model returned content (the final report) — we're done
            content = msg.get("content", "")
            if content:
                return {"output": content, "tool_calls": tool_calls_log,
                        "steps": loop_step, "error": False}

            # Edge case: no content and no tool calls — force finish
            break

    return {"output": "(Loop exhausted — model did not produce a final report)",
            "tool_calls": tool_calls_log, "steps": loop_step, "error": True}


# ── Handler ─────────────────────────────────────────────────────────

async def handle(task: Task) -> TaskResult:
    """Handle /unipat command."""
    text = (task.payload.get("text") or "").strip()
    args = (task.payload.get("args") or "").strip()
    body = args or text

    if not body or body in ("status", "/unipat"):
        return await _handle_status(task)

    parts = body.split(None, 1)
    verb = parts[0].lower().lstrip("/")

    if verb == "status":
        return await _handle_status(task)
    if verb == "tools":
        return _handle_tools(task)
    if verb == "rollout":
        rest = parts[1] if len(parts) > 1 else ""
        rollout_parts = rest.split(None, 1)
        try:
            n = int(rollout_parts[0]) if rollout_parts else DEFAULT_ROLLOUTS
        except ValueError:
            n = DEFAULT_ROLLOUTS
        question = rollout_parts[1] if len(rollout_parts) > 1 else ""
        if not question:
            return _error(task, "usage: /unipat rollout <N> <question>")
        return await _handle_research(task, question, rollouts=min(max(n, 1), MAX_ROLLOUTS))

    # Default: single-rollout research loop
    return await _handle_research(task, body, rollouts=1)


# ── Operations ──────────────────────────────────────────────────────

async def _handle_status(task: Task) -> TaskResult:
    """Report UniPat research-loop health: model + tools + env vars."""
    try:
        import httpx
    except ImportError:
        return _error(task, "httpx not installed")

    ollama_ok = False
    ollama_models: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            ollama_ok = True
            ollama_models = [m.get("name", "") for m in data.get("models", [])]
    except Exception as exc:
        logger.warning("ollama_unreachable: %s", exc)

    tool_availability = {
        "web_search": bool(SERPER_KEY_ID),
        "google_scholar": bool(SERPER_KEY_ID),
        "page_fetch": bool(JINA_API_KEYS),
        "code_interpreter": True,
    }
    ready = ollama_ok and UNIPAT_MODEL in ollama_models and tool_availability["web_search"]

    return TaskResult(
        task_id=task.task_id,
        agent_name="unipat-swarm",
        status="ok",
        result={
            "ready": ready,
            "ollama_endpoint": OLLAMA_BASE_URL,
            "ollama_healthy": ollama_ok,
            "model": UNIPAT_MODEL,
            "model_installed": UNIPAT_MODEL in ollama_models,
            "available_models": ollama_models[:10],
            "tool_availability": tool_availability,
            "env_configured": {
                "SERPER_KEY_ID": bool(SERPER_KEY_ID),
                "JINA_API_KEYS": bool(JINA_API_KEYS),
                "OPENROUTER_API_KEY": bool(OPENROUTER_API_KEY),
            },
            "upstream": "https://github.com/UniPat-AI/UniScientist",
        },
    )


def _handle_tools(task: Task) -> TaskResult:
    """List available UniScientist research tools with configuration status."""
    tools_status = []
    for tool in AVAILABLE_TOOLS:
        env_var = tool["requires_env"]
        configured = True if env_var is None else bool(os.environ.get(env_var))
        tools_status.append({**tool, "configured": configured})

    return TaskResult(
        task_id=task.task_id,
        agent_name="unipat-swarm",
        status="ok",
        result={
            "tools": tools_status,
            "total": len(tools_status),
            "configured": sum(1 for t in tools_status if t["configured"]),
        },
    )


async def _handle_research(task: Task, question: str, rollouts: int = 1) -> TaskResult:
    """Execute the UniScientist agentic research loop against local Ollama.

    Native port of the upstream loop:
      1. Send question + tools to Gemma (local Ollama)
      2. Model calls tools iteratively (search, scholar, page_fetch, code)
      3. Model writes final research report
      4. Repeat for N rollouts
      5. If N > 1, aggregate via a final synthesis call
    """
    try:
        import httpx  # noqa: F401
    except ImportError:
        return _error(task, "httpx not installed")

    if not SERPER_KEY_ID:
        return _error(task, "SERPER_KEY_ID not configured — run /unipat status")

    # Emit DRVP start event (best-effort)
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        await emit(DRVPEvent(
            event_type=DRVPEventType.DEEP_RESEARCH_STARTED,
            request_id=task.task_id,
            agent_name="unipat-swarm",
            device="leader",
            payload={"question": question[:200], "rollouts": rollouts, "model": UNIPAT_MODEL},
        ))
    except Exception:
        pass

    start = time.monotonic()
    candidates: list[dict[str, Any]] = []
    total_tool_calls = 0

    for i in range(rollouts):
        logger.info("unipat_rollout: %d/%d", i + 1, rollouts)
        result = await _run_research_loop(question)
        candidates.append(result)
        total_tool_calls += len(result.get("tool_calls", []))

    duration = time.monotonic() - start

    # If multiple rollouts, aggregate; otherwise use the single result
    if rollouts > 1 and len(candidates) > 1:
        final_output = await _aggregate_candidates(question, candidates)
    else:
        final_output = candidates[0].get("output", "")

    any_error = any(c.get("error") for c in candidates)

    # Emit DRVP completion (best-effort)
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        await emit(DRVPEvent(
            event_type=DRVPEventType.DEEP_RESEARCH_COMPLETED,
            request_id=task.task_id,
            agent_name="unipat-swarm",
            device="leader",
            payload={"rollouts": rollouts, "tool_calls": total_tool_calls,
                     "duration": round(duration, 1)},
        ))
    except Exception:
        pass

    return TaskResult(
        task_id=task.task_id,
        agent_name="unipat-swarm",
        status="ok" if not any_error else "partial",
        result={
            "question": question,
            "output": final_output,
            "rollouts_completed": len(candidates),
            "total_tool_calls": total_tool_calls,
            "rollout_steps": [c.get("steps", 0) for c in candidates],
            "tool_calls_log": [tc for c in candidates for tc in c.get("tool_calls", [])][:30],
            "model": UNIPAT_MODEL,
            "duration_seconds": round(duration, 1),
        },
    )


async def _aggregate_candidates(question: str, candidates: list[dict[str, Any]]) -> str:
    """Aggregate N candidate reports into a single consolidated report."""
    import httpx

    reports = []
    for i, c in enumerate(candidates):
        reports.append(f"## Candidate {i + 1}\n\n{c.get('output', '(empty)')[:3000]}")
    combined = "\n\n---\n\n".join(reports)

    prompt = (
        f"You are given {len(candidates)} candidate research reports for the question:\n"
        f'"{question}"\n\n'
        f"Synthesize the best parts of each into a single, comprehensive, well-structured report. "
        f"Remove duplicates, resolve contradictions, and produce a polished final answer.\n\n"
        f"{combined}"
    )

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/v1/chat/completions",
                json={
                    "model": UNIPAT_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a scientific report editor. Synthesize multiple candidate reports into one polished report."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", combined)
    except Exception as exc:
        logger.error("unipat_aggregate_error: %s", exc)
        return combined


def _error(task: Task, message: str) -> TaskResult:
    return TaskResult(
        task_id=task.task_id,
        agent_name="unipat-swarm",
        status="error",
        result={"error": message},
    )


if __name__ == "__main__":
    from shared.node_bridge import run_agent

    run_agent(handle, agent_name="UniPatSwarm")
