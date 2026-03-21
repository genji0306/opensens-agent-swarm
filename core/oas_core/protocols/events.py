"""Unified event schema bridging OpenClaw, Paperclip, and DRVP events.

Maps between the three event systems so Agent Office can display a
merged timeline from all sources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["UnifiedEventSource", "UnifiedEvent"]


class UnifiedEventSource(str, Enum):
    OPENCLAW = "openclaw"
    PAPERCLIP = "paperclip"
    DRVP = "drvp"


# Human-readable summaries for DRVP event types
_DRVP_SUMMARIES: dict[str, str] = {
    "request.created": "Request created",
    "request.routed": "Request routed",
    "request.completed": "Request completed",
    "request.failed": "Request failed",
    "agent.activated": "Agent activated",
    "agent.thinking": "Agent thinking",
    "agent.speaking": "Agent speaking",
    "agent.idle": "Agent idle",
    "agent.error": "Agent error",
    "handoff.started": "Handoff started",
    "handoff.completed": "Handoff completed",
    "tool.call.started": "Tool call started",
    "tool.call.completed": "Tool call completed",
    "tool.call.failed": "Tool call failed",
    "llm.call.started": "LLM call started",
    "llm.call.completed": "LLM call completed",
    "llm.stream.token": "Streaming tokens",
    "memory.read": "Memory read",
    "memory.write": "Memory write",
    "budget.check": "Budget checked",
    "budget.warning": "Budget warning",
    "budget.exhausted": "Budget exhausted",
    "campaign.step.started": "Campaign step started",
    "campaign.step.completed": "Campaign step completed",
    "campaign.approval.required": "Approval required",
    "campaign.approved": "Campaign approved",
}


def _drvp_summary(event_type: str, payload: dict[str, Any]) -> str:
    """Generate a human-readable summary from a DRVP event."""
    base = _DRVP_SUMMARIES.get(event_type, event_type)

    # Enrich with payload details where useful
    if event_type == "tool.call.started" and "tool_name" in payload:
        return f"Tool: {payload['tool_name']}"
    if event_type == "llm.call.completed":
        model = payload.get("model", "")
        cost = payload.get("cost_usd")
        if model and cost is not None:
            return f"LLM call completed ({model}, ${cost:.4f})"
        if model:
            return f"LLM call completed ({model})"
    if event_type == "handoff.started":
        from_a = payload.get("from_agent", "?")
        to_a = payload.get("to_agent", "?")
        return f"Handoff: {from_a} → {to_a}"
    if event_type == "budget.warning":
        pct = payload.get("utilization_percent")
        if pct is not None:
            return f"Budget warning ({pct:.0f}% used)"
    if event_type == "campaign.step.completed":
        step = payload.get("step_number")
        total = payload.get("total_steps")
        if step is not None and total is not None:
            return f"Campaign step {step}/{total} completed"

    return base


# --- OpenClaw stream+phase → event_type mapping ---

_OPENCLAW_LIFECYCLE_MAP: dict[str, tuple[str, str]] = {
    "start": ("agent.activated", "Agent started"),
    "thinking": ("agent.thinking", "Agent thinking"),
    "end": ("agent.idle", "Agent finished"),
    "fallback": ("agent.error", "Agent fallback"),
}


def _openclaw_type_and_summary(
    stream: str, data: dict[str, Any]
) -> tuple[str, str]:
    """Derive a DRVP-compatible event_type and summary from an OpenClaw event."""
    if stream == "lifecycle":
        phase = data.get("phase", "")
        return _OPENCLAW_LIFECYCLE_MAP.get(phase, (f"agent.{phase}", f"Agent {phase}"))
    if stream == "tool":
        phase = data.get("phase", "")
        name = data.get("name", "unknown")
        if phase == "start":
            return "tool.call.started", f"Tool: {name}"
        return "tool.call.completed", f"Tool done: {name}"
    if stream == "assistant":
        text = data.get("text", "")
        snippet = (text[:60] + "...") if len(text) > 60 else text
        return "agent.speaking", f"Agent: {snippet}" if snippet else "Agent speaking"
    if stream == "error":
        msg = data.get("message", "Unknown error")
        return "agent.error", f"Error: {msg[:80]}"
    return f"openclaw.{stream}", stream


# --- Paperclip event type mapping ---

_PAPERCLIP_TYPE_MAP: dict[str, tuple[str, str]] = {
    "issue.created": ("campaign.step.started", "Issue created"),
    "issue.status_changed": ("campaign.step.completed", "Issue status changed"),
    "issue.assigned": ("agent.activated", "Issue assigned"),
    "heartbeat_run.started": ("agent.activated", "Heartbeat run started"),
    "heartbeat_run.completed": ("agent.idle", "Heartbeat run completed"),
    "heartbeat_run.failed": ("agent.error", "Heartbeat run failed"),
    "cost_event.created": ("budget.check", "Cost recorded"),
    "approval.requested": ("campaign.approval.required", "Approval requested"),
    "approval.resolved": ("campaign.approved", "Approval resolved"),
    "activity.created": ("request.routed", "Activity logged"),
}


def _paperclip_type_and_summary(
    evt_type: str, payload: dict[str, Any]
) -> tuple[str, str]:
    """Map a Paperclip event type + payload to a DRVP-compatible type and summary."""
    mapped = _PAPERCLIP_TYPE_MAP.get(evt_type)
    if mapped:
        drvp_type, base_summary = mapped
    else:
        drvp_type = f"paperclip.{evt_type}"
        base_summary = evt_type.replace(".", " ").replace("_", " ").title()

    # Enrich summary from payload
    identifier = payload.get("issueIdentifier") or payload.get("identifier", "")
    title = payload.get("title", "")
    status = payload.get("status", "")

    if identifier and title:
        return drvp_type, f"{identifier}: {title}"
    if identifier and status:
        return drvp_type, f"{identifier} → {status}"
    if identifier:
        return drvp_type, f"{base_summary} ({identifier})"

    return drvp_type, base_summary


class UnifiedEvent(BaseModel):
    """Normalised event that Agent Office can render regardless of source."""

    event_id: str
    timestamp: datetime
    source: UnifiedEventSource
    event_type: str
    agent_name: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    issue_id: str | None = None

    @classmethod
    def from_drvp(cls, drvp_event: Any) -> UnifiedEvent:
        """Create a UnifiedEvent from a DRVPEvent instance.

        Accepts either a DRVPEvent Pydantic model or a dict with the same shape.
        """
        if isinstance(drvp_event, dict):
            event_type = drvp_event.get("event_type", "")
            # Handle enum values
            if hasattr(event_type, "value"):
                event_type = event_type.value
            payload = drvp_event.get("payload", {})
            return cls(
                event_id=drvp_event.get("event_id", ""),
                timestamp=drvp_event.get("timestamp", datetime.now(timezone.utc)),
                source=UnifiedEventSource.DRVP,
                event_type=event_type,
                agent_name=drvp_event.get("agent_name", ""),
                summary=_drvp_summary(event_type, payload),
                metadata=payload,
                request_id=drvp_event.get("request_id"),
                issue_id=drvp_event.get("issue_id"),
            )

        # Pydantic model path
        event_type_val = drvp_event.event_type
        if hasattr(event_type_val, "value"):
            event_type_val = event_type_val.value
        return cls(
            event_id=drvp_event.event_id,
            timestamp=drvp_event.timestamp,
            source=UnifiedEventSource.DRVP,
            event_type=event_type_val,
            agent_name=drvp_event.agent_name,
            summary=_drvp_summary(event_type_val, drvp_event.payload),
            metadata=drvp_event.payload,
            request_id=drvp_event.request_id,
            issue_id=drvp_event.issue_id,
        )

    @classmethod
    def from_openclaw(cls, event: dict[str, Any]) -> UnifiedEvent:
        """Map an OpenClaw agent event to UnifiedEvent.

        Expected shape (AgentEventPayload from gateway/types.ts)::

            {
                "runId": str,
                "seq": int,
                "stream": "lifecycle" | "tool" | "assistant" | "error",
                "ts": int,         # Unix millis
                "data": dict,
                "sessionKey": str | None,
                "agentName": str | None,  # enriched by caller
            }
        """
        stream = event.get("stream", "")
        data = event.get("data", {})
        ts_ms = event.get("ts", 0)
        run_id = event.get("runId", "")
        agent = event.get("agentName", "") or event.get("agent_name", "")

        event_type, summary = _openclaw_type_and_summary(stream, data)

        return cls(
            event_id=f"oc_{run_id}_{event.get('seq', 0)}",
            timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc),
            source=UnifiedEventSource.OPENCLAW,
            event_type=event_type,
            agent_name=agent,
            summary=summary,
            metadata=data,
            request_id=event.get("sessionKey") or run_id or None,
        )

    @classmethod
    def from_paperclip(cls, event: dict[str, Any]) -> UnifiedEvent:
        """Map a Paperclip LiveEvent to UnifiedEvent.

        Expected shape (PaperclipLiveEvent from paperclip-types.ts)::

            {
                "id": int,
                "companyId": str,
                "type": str,
                "createdAt": str,   # ISO 8601
                "payload": dict,
            }
        """
        payload = event.get("payload", {})
        evt_type = event.get("type", "")
        created_at = event.get("createdAt", "")

        if created_at:
            try:
                ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        mapped_type, summary = _paperclip_type_and_summary(evt_type, payload)

        return cls(
            event_id=f"pc_{event.get('id', '')}",
            timestamp=ts,
            source=UnifiedEventSource.PAPERCLIP,
            event_type=mapped_type,
            agent_name=payload.get("agentName", "") or payload.get("agent_name", ""),
            summary=summary,
            metadata=payload,
            request_id=payload.get("requestId") or payload.get("request_id"),
            issue_id=payload.get("issueIdentifier") or payload.get("issue_id"),
        )
