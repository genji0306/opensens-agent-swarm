"""Thin async LLM client wrappers for Anthropic, OpenAI, Google GenAI, and Perplexity.

Includes per-agent budget enforcement when Paperclip is configured.
Integrates ModelRouter for tiered routing: Anthropic (planning) / Ollama (execution).
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import time
from pathlib import Path
from typing import Any

import structlog

from shared.config import settings
from shared.audit import log_event

logger = structlog.get_logger("darklab.llm")

# Approximate cost per 1K tokens (USD) — conservative estimates
TOKEN_COSTS = {
    "claude-opus-4-6-20260301": {"input": 0.015, "output": 0.075},
    "claude-sonnet-4-6-20260301": {"input": 0.003, "output": 0.015},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gemini-2.0-flash": {"input": 0.0, "output": 0.0},  # free tier
    "gemini-2.5-flash": {"input": 0.0, "output": 0.0},  # free via AIClient
    "claude-sonnet-4-5": {"input": 0.0, "output": 0.0},  # free via AIClient/Kiro
    "llama-3.1-sonar-large-128k-online": {"input": 0.001, "output": 0.001},
    "llama3.1": {"input": 0.0, "output": 0.0},  # local Ollama — free
    "llama3.1:8b": {"input": 0.0, "output": 0.0},  # local Ollama — free
}

# ── Tiered Model Router (singleton) ─────────────────────────────────────────

_model_router: Any = None  # lazy init


def get_model_router():
    """Get or lazily init the ModelRouter singleton."""
    global _model_router
    if _model_router is not None:
        return _model_router
    try:
        from oas_core.model_router import ModelRouter, TierConfig
        _model_router = ModelRouter(TierConfig(
            boost_enabled=settings.boost_enabled,
            boost_daily_limit=settings.boost_daily_limit,
        ))
        logger.info("model_router_initialized", boost_enabled=settings.boost_enabled)
    except ImportError:
        logger.debug("model_router_unavailable", reason="oas_core not installed")
        _model_router = None
    return _model_router


# Credit-exhaustion error patterns from Anthropic API
_CREDIT_ERROR_PATTERNS = (
    "credit balance is too low",
    "billing",
    "insufficient_quota",
    "rate_limit",
)

# Daily budget limits per role (USD)
DAILY_BUDGETS = {
    "leader": 50.0,
    "academic": 30.0,
    "experiment": 20.0,
}


def _budget_file() -> Path:
    """Path to today's spend tracker."""
    today = time.strftime("%Y-%m-%d")
    p = Path(settings.darklab_home) / "logs" / f"spend-{today}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a single LLM call."""
    costs = TOKEN_COSTS.get(model, {"input": 0.003, "output": 0.015})
    return (input_tokens / 1000 * costs["input"]) + (output_tokens / 1000 * costs["output"])


def _check_and_record_spend(cost_usd: float, provider: str, model: str) -> None:
    """Atomically check budget and record spend under a single file lock.

    Prevents TOCTOU race where two concurrent calls both pass the budget
    check and then both record, exceeding the limit.
    """
    role = settings.darklab_role
    limit = DAILY_BUDGETS.get(role, 30.0)
    bf = _budget_file()
    bf.touch(exist_ok=True)

    with open(bf, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            content = f.read()
            data = json.loads(content) if content.strip() else {"total_usd": 0.0, "calls": []}
            current_spend = data.get("total_usd", 0.0)

            if current_spend >= limit:
                raise RuntimeError(
                    f"Daily budget exceeded for role '{role}': "
                    f"${current_spend:.2f} / ${limit:.2f}. "
                    "Pause and request Boss approval to increase."
                )

            data["total_usd"] = current_spend + cost_usd
            data["calls"].append({
                "ts": time.time(),
                "provider": provider,
                "model": model,
                "cost_usd": round(cost_usd, 6),
            })
            f.seek(0)
            f.truncate()
            f.write(json.dumps(data, indent=2))
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# --- Optional Paperclip budget middleware (set by init_budget_middleware) ---

_budget_middleware: Any = None


def init_budget_middleware(
    paperclip_url: str,
    paperclip_api_key: str,
    paperclip_company_id: str,
    paperclip_agent_id: str,
) -> None:
    """Initialize the Paperclip budget middleware. Call once at startup."""
    global _budget_middleware
    from oas_core.adapters.paperclip import PaperclipClient
    from oas_core.middleware.budget import BudgetMiddleware

    client = PaperclipClient(
        base_url=paperclip_url,
        api_key=paperclip_api_key,
        company_id=paperclip_company_id,
    )
    _budget_middleware = BudgetMiddleware(
        paperclip=client,
        agent_id=paperclip_agent_id,
        fallback_record=_check_and_record_spend,
    )


async def _record_spend(
    cost: float, provider: str, model: str, in_tok: int, out_tok: int,
) -> None:
    """Record spend via Paperclip middleware (if active) or local file lock."""
    if _budget_middleware:
        from shared.logging_setup import request_id_var
        rid = request_id_var.get() or "unknown"
        await _budget_middleware.report_cost(
            request_id=rid,
            agent_name=settings.darklab_role,
            device=settings.darklab_role,
            provider=provider,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )
    else:
        _check_and_record_spend(cost, provider, model)


async def call_litellm(
    prompt: str,
    system: str = "",
    model: str = "plan",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Route through LiteLLM proxy using OpenAI-compatible API.

    Model names map to LiteLLM aliases (e.g. "plan", "search", "synthesis").
    Detects Anthropic credit exhaustion and marks the router for auto-fallback.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key="litellm",
        base_url=settings.litellm_base_url,
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as exc:
        err_msg = str(exc).lower()
        if any(pat in err_msg for pat in _CREDIT_ERROR_PATTERNS):
            router = get_model_router()
            if router:
                router.mark_credits_exhausted()
                logger.warning("credits_exhausted_detected", model=model, error=str(exc))
                # Retry with Ollama fallback
                return await call_litellm(
                    prompt, system, "llama3.1", max_tokens=min(max_tokens, 4096),
                    temperature=temperature,
                )
        raise

    text = response.choices[0].message.content or ""

    in_tok = response.usage.prompt_tokens if response.usage else 0
    out_tok = response.usage.completion_tokens if response.usage else 0
    cost = _estimate_cost(model, in_tok, out_tok)
    await _record_spend(cost, "litellm", model, in_tok, out_tok)
    log_event("llm_call", provider="litellm", model=model,
              input_tokens=in_tok, output_tokens=out_tok, cost_usd=round(cost, 6))
    return text


async def call_anthropic(
    prompt: str,
    system: str = "",
    model: str = "claude-sonnet-4-6-20260301",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    # Route through LiteLLM if configured
    if settings.litellm_base_url:
        return await call_litellm(prompt, system, model, max_tokens, temperature)

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    if temperature > 0:
        kwargs["temperature"] = temperature

    response = await client.messages.create(**kwargs)
    text = response.content[0].text

    in_tok = response.usage.input_tokens
    out_tok = response.usage.output_tokens
    cost = _estimate_cost(model, in_tok, out_tok)
    await _record_spend(cost, "anthropic", model, in_tok, out_tok)
    log_event("llm_call", provider="anthropic", model=model,
              input_tokens=in_tok, output_tokens=out_tok, cost_usd=round(cost, 6))
    return text


async def call_openai(
    prompt: str,
    system: str = "",
    model: str = "gpt-4o",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    # Route through LiteLLM if configured
    if settings.litellm_base_url:
        return await call_litellm(prompt, system, model, max_tokens, temperature)

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = response.choices[0].message.content or ""

    in_tok = response.usage.prompt_tokens if response.usage else 0
    out_tok = response.usage.completion_tokens if response.usage else 0
    cost = _estimate_cost(model, in_tok, out_tok)
    await _record_spend(cost, "openai", model, in_tok, out_tok)
    log_event("llm_call", provider="openai", model=model,
              input_tokens=in_tok, output_tokens=out_tok, cost_usd=round(cost, 6))
    return text


async def call_gemini(
    prompt: str,
    model: str = "gemini-2.0-flash",
) -> str:
    import google.generativeai as genai

    genai.configure(api_key=settings.google_ai_api_key)
    gm = genai.GenerativeModel(model)
    response = await asyncio.to_thread(gm.generate_content, prompt)

    # Estimate tokens from text length (Gemini SDK may not expose token counts)
    est_in = len(prompt.split()) * 2
    est_out = len(response.text.split()) * 2
    cost = _estimate_cost(model, est_in, est_out)
    await _record_spend(cost, "gemini", model, est_in, est_out)
    log_event("llm_call", provider="gemini", model=model,
              input_tokens=est_in, output_tokens=est_out, cost_usd=round(cost, 6))
    return response.text


async def call_perplexity(
    query: str,
    model: str = "llama-3.1-sonar-large-128k-online",
) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {settings.perplexity_api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": query}],
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()

    text = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])

    # Extract token usage if available in response
    usage = data.get("usage", {})
    in_tok = usage.get("prompt_tokens", len(query.split()) * 2)
    out_tok = usage.get("completion_tokens", len(text.split()) * 2)
    cost = _estimate_cost(model, in_tok, out_tok)
    await _record_spend(cost, "perplexity", model, in_tok, out_tok)
    log_event("llm_call", provider="perplexity", model=model,
              input_tokens=in_tok, output_tokens=out_tok, cost_usd=round(cost, 6))
    return {"text": text, "citations": citations}


async def call_aiclient(
    prompt: str,
    system: str = "",
    model: str = "gemini-2.5-flash",
    max_tokens: int = 8192,
    temperature: float = 0.0,
) -> str:
    """Call AIClient-2-API (client-account boost tier). Zero cost.

    Uses free client OAuth tokens (Gemini CLI, Kiro, Codex) via the
    AIClient-2-API proxy.  Falls back gracefully if the service is
    unavailable.
    """
    if not settings.aiclient_base_url:
        raise RuntimeError("AIClient-2-API not configured (AICLIENT_BASE_URL empty)")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.aiclient_api_key,
        base_url=settings.aiclient_base_url,
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = response.choices[0].message.content or ""

    in_tok = response.usage.prompt_tokens if response.usage else 0
    out_tok = response.usage.completion_tokens if response.usage else 0
    # AIClient calls are free — record zero cost but still audit
    await _record_spend(0.0, "aiclient", model, in_tok, out_tok)
    log_event("llm_call", provider="aiclient", model=model,
              input_tokens=in_tok, output_tokens=out_tok, cost_usd=0.0,
              boosted=True)
    return text


async def call_multi_ai(
    prompt: str,
    system: str = "",
    providers: list[str] | None = None,
) -> dict[str, str]:
    """Call multiple AI providers and return all responses for cross-validation."""
    if providers is None:
        providers = ["anthropic"]

    results = {}
    for provider in providers:
        try:
            if provider == "anthropic" and settings.anthropic_api_key:
                results["anthropic"] = await call_anthropic(prompt, system=system)
            elif provider == "openai" and settings.openai_api_key:
                results["openai"] = await call_openai(prompt, system=system)
            elif provider == "gemini" and settings.google_ai_api_key:
                results["gemini"] = await call_gemini(prompt)
        except Exception as e:
            logger.warning("provider_failed", provider=provider, error=str(e))
            results[provider] = f"ERROR: {e}"

    return results


# ── Tiered Routed Call ───────────────────────────────────────────────────────


async def call_routed(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.0,
    *,
    force_planning: bool = False,
    force_execution: bool = False,
    force_boost: bool = False,
    task_type: str | None = None,
) -> str:
    """Smart LLM call that routes to the correct tier automatically.

    Protocol:
      1. Classifies the request as PLANNING, EXECUTION, or BOOST
      2. PLANNING → Anthropic Claude via LiteLLM (detailed, expensive)
      3. EXECUTION → Ollama llama3.1:8b via LiteLLM (free, slower)
      4. BOOST → Claude/Gemini via AIClient-2-API (free client accounts)
      5. If Anthropic credits exhaust → BOOST (if enabled) → EXECUTION

    Args:
        prompt: The user prompt.
        system: System message.
        max_tokens: Max output tokens.
        temperature: Sampling temperature.
        force_planning: Force Anthropic regardless of classification.
        force_execution: Force Ollama regardless of classification.
        force_boost: Force AIClient regardless of classification.
        task_type: DarkLab TaskType for boost eligibility (e.g. "RESEARCH").
    """
    router = get_model_router()

    if router is None:
        # No router available — use existing call_anthropic (which routes via LiteLLM)
        return await call_anthropic(prompt, system, max_tokens=max_tokens, temperature=temperature)

    from oas_core.model_router import ModelTier

    force_tier = None
    if force_boost:
        force_tier = ModelTier.BOOST
    elif force_planning:
        force_tier = ModelTier.PLANNING
    elif force_execution:
        force_tier = ModelTier.EXECUTION

    decision = router.route(
        prompt, system, force_tier=force_tier, task_type=task_type,
    )

    logger.info(
        "routed_call",
        tier=decision.tier.value,
        model=decision.model,
        reason=decision.reason,
        forced_fallback=decision.forced_fallback,
    )

    # BOOST tier → call AIClient-2-API with graceful fallback
    if decision.tier == ModelTier.BOOST:
        try:
            return await call_aiclient(
                prompt,
                system=system,
                model=decision.model,
                max_tokens=decision.max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            logger.warning(
                "boost_fallback_to_execution",
                error=str(exc),
                model=decision.model,
            )
            # Fall through to execution tier
            return await call_litellm(
                prompt,
                system=system,
                model=router.config.execution_model,
                max_tokens=router.config.execution_max_tokens,
                temperature=temperature,
            )

    return await call_litellm(
        prompt,
        system=system,
        model=decision.model,
        max_tokens=decision.max_tokens,
        temperature=temperature,
    )
