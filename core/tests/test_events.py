"""Tests for oas_core.protocols.events — UnifiedEvent schema."""
from datetime import datetime, timezone

import pytest

from oas_core.protocols.drvp import DRVPEvent, DRVPEventType
from oas_core.protocols.events import UnifiedEvent, UnifiedEventSource


def _make_drvp_event(
    event_type=DRVPEventType.AGENT_ACTIVATED,
    payload=None,
    **kwargs,
):
    return DRVPEvent(
        event_type=event_type,
        request_id="req_test",
        agent_name="test_agent",
        device="leader",
        payload=payload or {},
        **kwargs,
    )


class TestFromDrvp:
    def test_basic_conversion(self):
        drvp = _make_drvp_event()
        unified = UnifiedEvent.from_drvp(drvp)

        assert unified.source == UnifiedEventSource.DRVP
        assert unified.event_type == "agent.activated"
        assert unified.agent_name == "test_agent"
        assert unified.request_id == "req_test"
        assert unified.event_id == drvp.event_id

    def test_summary_generated(self):
        drvp = _make_drvp_event(DRVPEventType.AGENT_THINKING)
        unified = UnifiedEvent.from_drvp(drvp)
        assert unified.summary == "Agent thinking"

    def test_tool_call_summary(self):
        drvp = _make_drvp_event(
            DRVPEventType.TOOL_CALL_STARTED,
            payload={"tool_name": "perplexity_search"},
        )
        unified = UnifiedEvent.from_drvp(drvp)
        assert unified.summary == "Tool: perplexity_search"

    def test_llm_call_summary_with_cost(self):
        drvp = _make_drvp_event(
            DRVPEventType.LLM_CALL_COMPLETED,
            payload={"model": "claude-sonnet-4-6", "cost_usd": 0.034},
        )
        unified = UnifiedEvent.from_drvp(drvp)
        assert "claude-sonnet-4-6" in unified.summary
        assert "$0.0340" in unified.summary

    def test_handoff_summary(self):
        drvp = _make_drvp_event(
            DRVPEventType.HANDOFF_STARTED,
            payload={"from_agent": "leader", "to_agent": "academic"},
        )
        unified = UnifiedEvent.from_drvp(drvp)
        assert "leader" in unified.summary
        assert "academic" in unified.summary

    def test_budget_warning_summary(self):
        drvp = _make_drvp_event(
            DRVPEventType.BUDGET_WARNING,
            payload={"utilization_percent": 91.7},
        )
        unified = UnifiedEvent.from_drvp(drvp)
        assert "92%" in unified.summary  # rounded

    def test_campaign_step_summary(self):
        drvp = _make_drvp_event(
            DRVPEventType.CAMPAIGN_STEP_COMPLETED,
            payload={"step_number": 2, "total_steps": 5},
        )
        unified = UnifiedEvent.from_drvp(drvp)
        assert "2/5" in unified.summary

    def test_metadata_is_payload(self):
        drvp = _make_drvp_event(payload={"key": "value"})
        unified = UnifiedEvent.from_drvp(drvp)
        assert unified.metadata == {"key": "value"}

    def test_issue_id_preserved(self):
        drvp = _make_drvp_event(issue_id="DL-47")
        unified = UnifiedEvent.from_drvp(drvp)
        assert unified.issue_id == "DL-47"

    def test_from_dict(self):
        """from_drvp also accepts a plain dict."""
        d = {
            "event_id": "evt_abc",
            "event_type": "request.created",
            "timestamp": datetime.now(timezone.utc),
            "request_id": "req_1",
            "agent_name": "leader",
            "device": "leader",
            "payload": {"source": "telegram"},
        }
        unified = UnifiedEvent.from_drvp(d)
        assert unified.source == UnifiedEventSource.DRVP
        assert unified.event_type == "request.created"
        assert unified.summary == "Request created"

    def test_timestamp_preserved(self):
        ts = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        drvp = _make_drvp_event()
        drvp.timestamp = ts
        unified = UnifiedEvent.from_drvp(drvp)
        assert unified.timestamp == ts


class TestFromOpenclaw:
    def test_lifecycle_start(self):
        event = {
            "runId": "run_123",
            "seq": 1,
            "stream": "lifecycle",
            "ts": 1710763200000,  # 2024-03-18 12:00:00 UTC
            "data": {"phase": "start"},
            "agentName": "academic",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.source == UnifiedEventSource.OPENCLAW
        assert unified.event_type == "agent.activated"
        assert unified.agent_name == "academic"
        assert unified.summary == "Agent started"
        assert unified.event_id == "oc_run_123_1"

    def test_lifecycle_thinking(self):
        event = {
            "runId": "run_123",
            "seq": 2,
            "stream": "lifecycle",
            "ts": 1710763200000,
            "data": {"phase": "thinking"},
            "agentName": "academic",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.event_type == "agent.thinking"

    def test_lifecycle_end(self):
        event = {
            "runId": "run_123",
            "seq": 3,
            "stream": "lifecycle",
            "ts": 1710763200000,
            "data": {"phase": "end"},
            "agentName": "academic",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.event_type == "agent.idle"

    def test_lifecycle_fallback(self):
        event = {
            "runId": "run_123",
            "seq": 4,
            "stream": "lifecycle",
            "ts": 1710763200000,
            "data": {"phase": "fallback"},
            "agentName": "leader",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.event_type == "agent.error"

    def test_tool_start(self):
        event = {
            "runId": "run_456",
            "seq": 5,
            "stream": "tool",
            "ts": 1710763200000,
            "data": {"phase": "start", "name": "perplexity_search"},
            "agentName": "academic",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.event_type == "tool.call.started"
        assert "perplexity_search" in unified.summary

    def test_tool_end(self):
        event = {
            "runId": "run_456",
            "seq": 6,
            "stream": "tool",
            "ts": 1710763200000,
            "data": {"phase": "end", "name": "perplexity_search"},
            "agentName": "academic",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.event_type == "tool.call.completed"

    def test_assistant_speaking(self):
        event = {
            "runId": "run_789",
            "seq": 7,
            "stream": "assistant",
            "ts": 1710763200000,
            "data": {"text": "Here are the results of the literature search."},
            "agentName": "academic",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.event_type == "agent.speaking"
        assert "literature search" in unified.summary

    def test_assistant_long_text_truncated(self):
        event = {
            "runId": "run_789",
            "seq": 8,
            "stream": "assistant",
            "ts": 1710763200000,
            "data": {"text": "A" * 100},
            "agentName": "academic",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.summary.endswith("...")
        assert len(unified.summary) < 80

    def test_error_stream(self):
        event = {
            "runId": "run_err",
            "seq": 1,
            "stream": "error",
            "ts": 1710763200000,
            "data": {"message": "API rate limit exceeded"},
            "agentName": "experiment",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.event_type == "agent.error"
        assert "rate limit" in unified.summary

    def test_timestamp_from_ts_millis(self):
        event = {
            "runId": "run_ts",
            "seq": 1,
            "stream": "lifecycle",
            "ts": 1710763200000,
            "data": {"phase": "start"},
            "agentName": "leader",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.timestamp.year >= 2024

    def test_request_id_from_session_key(self):
        event = {
            "runId": "run_sk",
            "seq": 1,
            "stream": "lifecycle",
            "ts": 0,
            "data": {"phase": "start"},
            "sessionKey": "session_abc",
            "agentName": "leader",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.request_id == "session_abc"

    def test_agent_name_fallback(self):
        event = {
            "runId": "run_fb",
            "seq": 1,
            "stream": "lifecycle",
            "ts": 0,
            "data": {"phase": "start"},
            "agent_name": "fallback_agent",
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.agent_name == "fallback_agent"

    def test_unknown_stream(self):
        event = {
            "runId": "run_unk",
            "seq": 1,
            "stream": "custom_stream",
            "ts": 0,
            "data": {},
        }
        unified = UnifiedEvent.from_openclaw(event)
        assert unified.event_type == "openclaw.custom_stream"


class TestFromPaperclip:
    def test_issue_created(self):
        event = {
            "id": 42,
            "companyId": "comp_dl",
            "type": "issue.created",
            "createdAt": "2026-03-18T12:00:00Z",
            "payload": {
                "issueIdentifier": "DL-47",
                "title": "Research quantum sensors",
                "agentName": "academic",
            },
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.source == UnifiedEventSource.PAPERCLIP
        assert unified.event_type == "campaign.step.started"
        assert unified.event_id == "pc_42"
        assert unified.issue_id == "DL-47"
        assert "DL-47" in unified.summary
        assert "quantum sensors" in unified.summary

    def test_issue_status_changed(self):
        event = {
            "id": 43,
            "companyId": "comp_dl",
            "type": "issue.status_changed",
            "createdAt": "2026-03-18T12:05:00Z",
            "payload": {
                "issueIdentifier": "DL-47",
                "status": "in_progress",
                "agentName": "academic",
            },
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.event_type == "campaign.step.completed"
        assert "DL-47" in unified.summary
        assert "in_progress" in unified.summary

    def test_heartbeat_run_started(self):
        event = {
            "id": 100,
            "companyId": "comp_dl",
            "type": "heartbeat_run.started",
            "createdAt": "2026-03-18T12:10:00Z",
            "payload": {"agentName": "experiment"},
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.event_type == "agent.activated"
        assert unified.agent_name == "experiment"

    def test_cost_event(self):
        event = {
            "id": 200,
            "companyId": "comp_dl",
            "type": "cost_event.created",
            "createdAt": "2026-03-18T12:15:00Z",
            "payload": {"agentName": "leader", "costCents": 5},
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.event_type == "budget.check"

    def test_approval_requested(self):
        event = {
            "id": 300,
            "companyId": "comp_dl",
            "type": "approval.requested",
            "createdAt": "2026-03-18T12:20:00Z",
            "payload": {"agentName": "leader"},
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.event_type == "campaign.approval.required"

    def test_unknown_type_graceful(self):
        event = {
            "id": 999,
            "companyId": "comp_dl",
            "type": "some.new.event",
            "createdAt": "2026-03-18T12:30:00Z",
            "payload": {},
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.event_type == "paperclip.some.new.event"

    def test_timestamp_parsing(self):
        event = {
            "id": 1,
            "companyId": "comp_dl",
            "type": "activity.created",
            "createdAt": "2026-03-18T12:00:00+00:00",
            "payload": {"agentName": "leader"},
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.timestamp.year == 2026
        assert unified.timestamp.month == 3

    def test_missing_created_at(self):
        event = {
            "id": 2,
            "companyId": "comp_dl",
            "type": "activity.created",
            "payload": {"agentName": "leader"},
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.timestamp is not None

    def test_request_id_from_payload(self):
        event = {
            "id": 3,
            "companyId": "comp_dl",
            "type": "issue.created",
            "createdAt": "2026-03-18T12:00:00Z",
            "payload": {
                "requestId": "req_abc",
                "agentName": "leader",
            },
        }
        unified = UnifiedEvent.from_paperclip(event)
        assert unified.request_id == "req_abc"
