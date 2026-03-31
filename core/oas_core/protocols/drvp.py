"""Dynamic Request Visualization Protocol (DRVP).

Defines the event schema and emission function that allows any OAS
request to be visualised in real-time on both Agent Office and the
Paperclip dashboard.

Events are published to Redis Pub/Sub (``drvp:{company_id}``) and
persisted via the Paperclip REST API.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["DRVPEventType", "DRVPEvent", "emit", "configure"]

logger = logging.getLogger("oas.protocols.drvp")


class DRVPEventType(str, Enum):
    # Request lifecycle
    REQUEST_CREATED = "request.created"
    REQUEST_ROUTED = "request.routed"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"

    # Agent lifecycle
    AGENT_ACTIVATED = "agent.activated"
    AGENT_THINKING = "agent.thinking"
    AGENT_SPEAKING = "agent.speaking"
    AGENT_IDLE = "agent.idle"
    AGENT_ERROR = "agent.error"

    # Handoff
    HANDOFF_STARTED = "handoff.started"
    HANDOFF_COMPLETED = "handoff.completed"

    # Tool usage
    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_COMPLETED = "tool.call.completed"
    TOOL_CALL_FAILED = "tool.call.failed"

    # LLM calls
    LLM_CALL_STARTED = "llm.call.started"
    LLM_CALL_COMPLETED = "llm.call.completed"
    LLM_CALL_BOOSTED = "llm.call.boosted"
    LLM_STREAM_TOKEN = "llm.stream.token"

    # Memory
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"

    # Budget
    BUDGET_CHECK = "budget.check"
    BUDGET_WARNING = "budget.warning"
    BUDGET_EXHAUSTED = "budget.exhausted"

    # Browser
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_ACTION = "browser.action"
    BROWSER_BLOCKED = "browser.blocked"

    # Campaign
    CAMPAIGN_STEP_STARTED = "campaign.step.started"
    CAMPAIGN_STEP_COMPLETED = "campaign.step.completed"
    CAMPAIGN_APPROVAL_REQUIRED = "campaign.approval.required"
    CAMPAIGN_APPROVED = "campaign.approved"

    # RL training lifecycle
    RL_ROLLOUT_COLLECTED = "rl.rollout.collected"
    RL_TRAINING_STEP = "rl.training.step"
    RL_CHECKPOINT_SAVED = "rl.checkpoint.saved"
    RL_EVALUATION_COMPLETED = "rl.evaluation.completed"
    RL_CHECKPOINT_PROMOTED = "rl.checkpoint.promoted"
    RL_CHECKPOINT_ROLLED_BACK = "rl.checkpoint.rolledback"

    # TurboQuant memory
    MEMORY_POOL_STATUS = "memory.pool.status"
    MEMORY_POOL_EVICTION = "memory.pool.eviction"
    MEMORY_COMPRESSION_STATS = "memory.compression.stats"

    # Deep Research lifecycle
    DEEP_RESEARCH_STARTED = "deep_research.started"
    DEEP_RESEARCH_ITERATION = "deep_research.iteration"
    DEEP_RESEARCH_SEARCH = "deep_research.search"
    DEEP_RESEARCH_SCORED = "deep_research.scored"
    DEEP_RESEARCH_COMPLETED = "deep_research.completed"

    # Debate lifecycle
    DEBATE_STARTED = "debate.started"
    DEBATE_ROUND_COMPLETED = "debate.round.completed"
    DEBATE_COMPLETED = "debate.completed"
    DEBATE_TRANSCRIPT_READY = "debate.transcript.ready"

    # Decision engine
    DECISION_RECOMMENDED = "decision.recommended"
    READINESS_SCORED = "readiness.scored"
    CAMPAIGN_REFLECTION_COMPLETED = "campaign.reflection.completed"
    UNCERTAINTY_ROUTING = "uncertainty.routing"


class DRVPEvent(BaseModel):
    """A single DRVP event emitted by the OAS middleware pipeline."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    event_type: DRVPEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str  # Groups all events for one user request
    task_id: str | None = None  # DarkLab task ID
    issue_id: str | None = None  # Paperclip issue identifier (e.g. "DL-47")
    agent_name: str  # Which agent emitted this event
    device: str  # "leader" | "academic" | "experiment"
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_event_id: str | None = None  # For nested events


# --- Module-level transport backends (set by configure()) ---

_redis_client: Any = None
_paperclip_client: Any = None  # PaperclipClient instance
_company_id: str = ""

# Rate limiter: at most 1 LLM_STREAM_TOKEN event per agent per 500ms
_last_stream_emit: dict[str, float] = {}
_STREAM_TOKEN_INTERVAL = 0.5


def configure(
    *,
    redis_client: Any = None,
    paperclip_client: Any = None,
    company_id: str = "",
) -> None:
    """Configure the DRVP emitter with transport backends.

    Call once at startup. Either backend can be None (skipped).
    """
    global _redis_client, _paperclip_client, _company_id
    _redis_client = redis_client
    _paperclip_client = paperclip_client
    _company_id = company_id


async def emit(event: DRVPEvent) -> None:
    """Publish a DRVP event to Redis Pub/Sub and Paperclip activity log.

    - Redis: publishes JSON to channel ``drvp:{company_id}``
    - Paperclip: POSTs to ``/api/companies/:companyId/activity``
    - ``LLM_STREAM_TOKEN`` events are rate-limited to 1 per 500ms per agent.
    """
    # Rate-limit stream tokens
    if event.event_type == DRVPEventType.LLM_STREAM_TOKEN:
        now = time.monotonic()
        key = event.agent_name
        last = _last_stream_emit.get(key, 0.0)
        if now - last < _STREAM_TOKEN_INTERVAL:
            return
        _last_stream_emit[key] = now

    event_json = event.model_dump_json()

    # Publish to Redis (fire-and-forget on error)
    if _redis_client is not None:
        try:
            channel = f"drvp:{_company_id}"
            await _redis_client.publish(channel, event_json)
        except Exception as exc:
            logger.warning("drvp_redis_publish_failed", exc_info=exc)

    # Persist to Paperclip activity log
    if _paperclip_client is not None:
        try:
            await _paperclip_client.log_activity(
                action=f"drvp.{event.event_type.value}",
                entity_type="drvp_event",
                entity_id=event.event_id,
                details={
                    "request_id": event.request_id,
                    "task_id": event.task_id,
                    "agent_name": event.agent_name,
                    "device": event.device,
                    "payload": event.payload,
                },
            )
        except Exception as exc:
            logger.warning("drvp_paperclip_persist_failed", exc_info=exc)
