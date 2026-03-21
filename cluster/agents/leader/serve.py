"""DarkLab Leader HTTP server — FastAPI wrapper around leader agents.

Exposes dispatch, synthesis, and media_gen handlers as webhook endpoints
so Liaison Broker (or any HTTP client) can invoke darklab agents.

Usage:
  python -m leader.serve              # start on :8100
  python -m leader.serve --port 8200  # custom port
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from typing import Any

import httpx
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from pydantic import BaseModel, Field

__all__ = ["app", "main"]

from shared.models import Task, TaskType, TaskResult
from shared.audit import log_task, log_result, log_event
from shared.logging_setup import setup_logging, request_id_var
from leader.dispatch import handle as dispatch_handle, parse_command, ROUTING_TABLE
from leader.synthesis import handle as synthesis_handle
from leader.media_gen import handle as media_gen_handle

logger = structlog.get_logger("darklab.serve")

app = FastAPI(title="DarkLab Leader", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5180",
        "http://192.168.23.25:5180",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def inject_request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    request_id_var.set(rid)
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    return response


# --- Request / Response models for the webhook API ---

class WebhookRequest(BaseModel):
    """Incoming webhook from Liaison Broker or direct HTTP call."""
    text: str = ""
    user_id: int = 0
    reply_url: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    task_type: str | None = None


class BoostToggleRequest(BaseModel):
    enabled: bool = True


class ServiceHealth(BaseModel):
    name: str
    status: str  # "ok" | "error" | "timeout"
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    role: str = "leader"
    agents: list[str] = ["dispatch", "synthesis", "media_gen"]
    commands: list[str] = []
    services: list[ServiceHealth] = []
    swarm_available: bool = False


async def _check_service(name: str, url: str, timeout: float = 5.0) -> ServiceHealth:
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            latency = round((time.monotonic() - start) * 1000, 1)
            if resp.status_code < 400:
                return ServiceHealth(name=name, status="ok", latency_ms=latency)
            return ServiceHealth(name=name, status="error", latency_ms=latency,
                                 error=f"HTTP {resp.status_code}")
    except httpx.TimeoutException:
        return ServiceHealth(name=name, status="timeout", error="Connection timed out")
    except Exception as e:
        return ServiceHealth(name=name, status="error", error=str(e))


# --- Endpoints ---

@app.get("/health")
async def health() -> HealthResponse:
    from shared.config import settings

    checks = []
    if settings.academic_host:
        checks.append(_check_service(
            "academic", f"http://{settings.academic_host}:{settings.academic_port}/health"))
    if settings.experiment_host:
        checks.append(_check_service(
            "experiment", f"http://{settings.experiment_host}:{settings.experiment_port}/health"))
    if settings.litellm_base_url:
        checks.append(_check_service("litellm", f"{settings.litellm_base_url}/health"))
    if settings.paperclip_url:
        checks.append(_check_service("paperclip", f"{settings.paperclip_url}/api/health"))

    services = list(await asyncio.gather(*checks)) if checks else []
    all_ok = all(s.status == "ok" for s in services)
    any_ok = any(s.status == "ok" for s in services)
    overall = "ok" if (all_ok or not services) else ("degraded" if any_ok else "down")

    # Check swarm availability
    try:
        from oas_core.swarm import SWARM_AVAILABLE
        swarm_ok = SWARM_AVAILABLE
    except ImportError:
        swarm_ok = False

    return HealthResponse(
        status=overall,
        commands=sorted(ROUTING_TABLE.keys()),
        services=services,
        swarm_available=swarm_ok,
    )


# --- DRVP SSE Relay ---

_drvp_redis: Any = None


async def _get_drvp_redis():
    """Lazy-init async Redis client for DRVP Pub/Sub."""
    global _drvp_redis
    if _drvp_redis is None:
        try:
            import redis.asyncio as aioredis
            from shared.config import settings
            _drvp_redis = aioredis.from_url(settings.redis_url)
        except Exception as exc:
            logger.error("drvp_redis_init_failed", error=str(exc))
            raise HTTPException(503, "Redis unavailable for DRVP relay")
    return _drvp_redis


@app.get("/drvp/events/{company_id}")
async def drvp_sse(company_id: str, request: Request):
    """Stream DRVP events as Server-Sent Events.

    Subscribes to Redis Pub/Sub channel ``drvp:{company_id}`` and relays
    each message to the browser as an SSE frame. Sends keepalive comments
    every second when idle. Cleans up on client disconnect.
    """
    redis = await _get_drvp_redis()

    async def event_generator():
        pubsub = redis.pubsub()
        channel = f"drvp:{company_id}"
        await pubsub.subscribe(channel)
        logger.info("drvp_sse_connected", company_id=company_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0,
                )
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
                else:
                    # Keepalive to prevent proxy/browser timeouts
                    yield ": keepalive\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            logger.info("drvp_sse_disconnected", company_id=company_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/dispatch")
async def dispatch(req: WebhookRequest) -> dict:
    """Main entry point — routes slash commands or plans campaigns.

    Liaison Broker POSTs here for messages starting with darklab commands.
    """
    task = _build_task(req, TaskType.PLAN)
    log_task(task)

    result = await dispatch_handle(task)
    log_result(result)

    response = result.model_dump(mode="json")

    # If reply_url provided, POST result back to Liaison Broker
    if req.reply_url:
        await _reply(req.reply_url, response)

    return response


@app.post("/synthesize")
async def synthesize(req: WebhookRequest) -> dict:
    """Invoke synthesis agent directly."""
    task = _build_task(req, TaskType.SYNTHESIZE)
    log_task(task)

    result = await synthesis_handle(task)
    log_result(result)

    response = result.model_dump(mode="json")
    if req.reply_url:
        await _reply(req.reply_url, response)
    return response


@app.post("/media")
async def media_gen(req: WebhookRequest) -> dict:
    """Invoke media generation agent directly."""
    task = _build_task(req, TaskType.MEDIA_GEN)
    log_task(task)

    result = await media_gen_handle(task)
    log_result(result)

    response = result.model_dump(mode="json")
    if req.reply_url:
        await _reply(req.reply_url, response)
    return response


@app.post("/task")
async def generic_task(req: WebhookRequest) -> dict:
    """Generic task endpoint — auto-routes based on text or task_type.

    Used by Academic/Experiment nodes to call back to Leader,
    or for direct API invocation.
    """
    # Determine task type from explicit field or by parsing command
    if req.task_type:
        try:
            tt = TaskType(req.task_type)
        except ValueError:
            raise HTTPException(400, f"Unknown task_type: {req.task_type}")
    else:
        command, _ = parse_command(req.text)
        if command == "synthesize":
            tt = TaskType.SYNTHESIZE
        elif command == "report":
            tt = TaskType.MEDIA_GEN
        else:
            tt = TaskType.PLAN

    task = _build_task(req, tt)
    log_task(task)

    if tt == TaskType.SYNTHESIZE:
        result = await synthesis_handle(task)
    elif tt == TaskType.MEDIA_GEN:
        result = await media_gen_handle(task)
    else:
        result = await dispatch_handle(task)

    log_result(result)
    response = result.model_dump(mode="json")
    if req.reply_url:
        await _reply(req.reply_url, response)
    return response


# --- Cluster config endpoints ---

@app.get("/config/boost")
async def boost_status() -> dict:
    """Get current boost tier configuration and usage stats."""
    from shared.config import settings
    from shared.llm_client import get_model_router

    router = get_model_router()
    if router:
        return {
            "enabled": router.config.boost_enabled,
            "model": router.config.boost_model,
            "daily_limit": router.config.boost_daily_limit,
            "today_calls": router._boost_today_count,
            "credits_exhausted": router.config.credits_exhausted,
            "aiclient_configured": bool(settings.aiclient_base_url),
        }
    return {
        "enabled": settings.boost_enabled,
        "model": "gemini-2.5-flash",
        "daily_limit": settings.boost_daily_limit,
        "today_calls": 0,
        "credits_exhausted": False,
        "aiclient_configured": bool(settings.aiclient_base_url),
    }


@app.post("/config/boost")
async def toggle_boost(req: BoostToggleRequest) -> dict:
    """Toggle boost tier on/off."""
    from shared.config import settings
    from shared.llm_client import get_model_router

    enabled = req.enabled

    settings.boost_enabled = enabled  # type: ignore[misc]
    router = get_model_router()
    if router:
        router.config.boost_enabled = enabled

    log_event("boost_toggled", enabled=enabled)
    return {"enabled": enabled}


@app.get("/config/browser")
async def browser_config() -> dict:
    """Get browser agent security configuration."""
    from shared.config import settings
    return {
        "allowed_domains": sorted(settings.browser_domain_allowlist),
        "max_steps": settings.browser_max_steps,
        "headless": settings.browser_headless,
    }


# --- Helpers ---

def _build_task(req: WebhookRequest, task_type: TaskType) -> Task:
    """Convert a webhook request into a Task."""
    payload = {**req.payload, "text": req.text}
    return Task(
        task_id=uuid.uuid4().hex[:12],
        task_type=task_type,
        user_id=req.user_id,
        payload=payload,
    )


async def _reply(reply_url: str, data: dict) -> None:
    """POST result back to Liaison Broker reply endpoint."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(reply_url, json=data)
            logger.info("reply_sent", url=reply_url, status=resp.status_code)
    except Exception as e:
        logger.error("reply_failed", url=reply_url, error=str(e))


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="DarkLab Leader HTTP Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    setup_logging()

    # Initialize Paperclip budget middleware if configured
    from shared.config import settings
    if settings.paperclip_url and settings.paperclip_api_key:
        from shared.llm_client import init_budget_middleware
        init_budget_middleware(
            paperclip_url=settings.paperclip_url,
            paperclip_api_key=settings.paperclip_api_key,
            paperclip_company_id=settings.paperclip_company_id,
            paperclip_agent_id=settings.paperclip_agent_id,
        )

    log_event("server_start", host=args.host, port=args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
