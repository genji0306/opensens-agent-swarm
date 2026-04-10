"""Tests for the KairosDaemon dispatch handler and daemon lifecycle."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models import Task, TaskResult, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(text: str = "status") -> Task:
    return Task(task_type=TaskType.KAIROS, payload={"text": text})


def _mock_heartbeat_snapshot(
    *,
    budget_blocked: bool = False,
    budget_ratio: float = 0.05,
    stuck_campaigns: int = 0,
    dev_reachable: bool = True,
) -> MagicMock:
    snap = MagicMock()
    snap.budget_blocked = budget_blocked
    snap.budget_ratio = budget_ratio
    snap.stuck_campaigns = stuck_campaigns
    snap.dev_reachable = dev_reachable
    snap.expired_leases = 0
    snap.timestamp = 1700000000.0
    snap.actions_taken = []
    snap.to_dict.return_value = {
        "timestamp": 1700000000.0,
        "budget_blocked": budget_blocked,
        "budget_ratio": budget_ratio,
        "expired_leases": 0,
        "stuck_campaigns": stuck_campaigns,
        "dev_reachable": dev_reachable,
        "actions_taken": [],
    }
    return snap


# ---------------------------------------------------------------------------
# Tests: handle() dispatch
# ---------------------------------------------------------------------------

class TestHandleStatus:
    @pytest.mark.asyncio
    async def test_handle_status_returns_ok(self):
        """Status subcommand returns daemon status."""
        # Reset module singleton
        import leader.kairos as mod
        mod._daemon = None

        result = await mod.handle(_make_task("status"))

        assert result.status == "ok"
        assert result.result["action"] == "kairos_status"
        assert "running" in result.result
        assert "KAIROS Daemon Status" in result.result["output"]


class TestHandleAutodream:
    @pytest.mark.asyncio
    async def test_handle_autodream_returns_result(self):
        """autodream subcommand triggers consolidation and returns result."""
        import leader.kairos as mod
        mod._daemon = None

        mock_autodream = MagicMock()
        mock_autodream.consolidate.return_value = {
            "entries_before": 10,
            "entries_after": 8,
            "deduplicated": 2,
            "pruned": 0,
            "merged": 0,
            "succeeded": True,
            "duration_s": 0.5,
        }

        with patch("leader.kairos.KairosDaemon._ensure_components") as ensure, \
             patch("leader.kairos._emit_drvp", new_callable=AsyncMock):
            ensure.return_value = None
            daemon = mod.KairosDaemon()
            daemon._autodream = mock_autodream
            # Inject temporary daemon
            mod._daemon = daemon

            result = await mod.handle(_make_task("autodream"))
            mod._daemon = None

        assert result.status == "ok"
        assert result.result["action"] == "kairos_autodream"
        assert result.result.get("entries_before") == 10


# ---------------------------------------------------------------------------
# Tests: heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_returns_status(self):
        """Heartbeat returns snapshot with budget, stuck campaigns."""
        import leader.kairos as mod

        snap = _mock_heartbeat_snapshot()
        mock_hb = AsyncMock()
        mock_hb.scan = AsyncMock(return_value=snap)

        daemon = mod.KairosDaemon()
        daemon._heartbeat = mock_hb

        with patch("leader.kairos._emit_drvp", new_callable=AsyncMock):
            result = await daemon.run_heartbeat()

        assert result["budget_blocked"] is False
        assert result["budget_ratio"] == 0.05
        mock_hb.scan.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_heartbeat_emits_drvp_event(self):
        """Heartbeat emits kairos.heartbeat.tick DRVP event."""
        import leader.kairos as mod

        snap = _mock_heartbeat_snapshot()
        mock_hb = AsyncMock()
        mock_hb.scan = AsyncMock(return_value=snap)

        daemon = mod.KairosDaemon()
        daemon._heartbeat = mock_hb

        with patch("leader.kairos._emit_drvp", new_callable=AsyncMock) as emit:
            await daemon.run_heartbeat()

        emit.assert_awaited_once()
        call_args = emit.call_args
        assert call_args[0][0] == "kairos.heartbeat.tick"


# ---------------------------------------------------------------------------
# Tests: autoDream
# ---------------------------------------------------------------------------

class TestAutodream:
    @pytest.mark.asyncio
    async def test_autodream_stub_counts_entries(self):
        """autoDream stub scans KB and reports entry counts."""
        import leader.kairos as mod

        mock_ad = MagicMock()
        mock_ad.consolidate.return_value = {
            "entries_before": 15,
            "entries_after": 12,
            "deduplicated": 3,
            "pruned": 0,
            "merged": 0,
            "succeeded": True,
            "duration_s": 0.2,
        }

        daemon = mod.KairosDaemon()
        daemon._autodream = mock_ad

        with patch("leader.kairos._emit_drvp", new_callable=AsyncMock):
            result = await daemon.run_autodream()

        assert result["entries_before"] == 15
        assert result["deduplicated"] == 3
        mock_ad.consolidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_autodream_emits_drvp_events(self):
        """autoDream emits started + completed DRVP events."""
        import leader.kairos as mod

        mock_ad = MagicMock()
        mock_ad.consolidate.return_value = {
            "entries_before": 5,
            "entries_after": 5,
            "deduplicated": 0,
            "succeeded": True,
        }

        daemon = mod.KairosDaemon()
        daemon._autodream = mock_ad

        with patch("leader.kairos._emit_drvp", new_callable=AsyncMock) as emit:
            await daemon.run_autodream()

        assert emit.await_count == 2
        event_types = [c[0][0] for c in emit.call_args_list]
        assert "kairos.autodream.started" in event_types
        assert "kairos.autodream.completed" in event_types


# ---------------------------------------------------------------------------
# Tests: proactive suggestions
# ---------------------------------------------------------------------------

class TestProactiveSuggest:
    @pytest.mark.asyncio
    async def test_proactive_suggest_finds_gaps(self):
        """Proactive scan finds knowledge gaps from KB."""
        import leader.kairos as mod

        mock_suggestion = MagicMock()
        mock_suggestion.to_dict.return_value = {
            "kind": "research_gap",
            "topic": "MnO2 sensors",
            "rationale": "Only 1 source(s), need >= 3",
            "priority": 3,
        }

        mock_suggester = MagicMock()
        mock_suggester.scan.return_value = [mock_suggestion]

        daemon = mod.KairosDaemon()
        daemon._suggester = mock_suggester

        with patch("leader.kairos._emit_drvp", new_callable=AsyncMock):
            result = await daemon.run_proactive_suggest()

        assert result["suggestions_found"] == 1
        assert result["suggestions"][0]["kind"] == "research_gap"

    @pytest.mark.asyncio
    async def test_proactive_emits_drvp_event(self):
        """Proactive scan emits kairos.proactive.suggested event."""
        import leader.kairos as mod

        mock_suggestion = MagicMock()
        mock_suggestion.to_dict.return_value = {
            "kind": "low_confidence",
            "topic": "EIT sensors",
        }

        mock_suggester = MagicMock()
        mock_suggester.scan.return_value = [mock_suggestion]

        daemon = mod.KairosDaemon()
        daemon._suggester = mock_suggester

        with patch("leader.kairos._emit_drvp", new_callable=AsyncMock) as emit:
            await daemon.run_proactive_suggest()

        emit.assert_awaited_once()
        assert emit.call_args[0][0] == "kairos.proactive.suggested"


# ---------------------------------------------------------------------------
# Tests: idle budget gate
# ---------------------------------------------------------------------------

class TestIdleBudgetGate:
    @pytest.mark.asyncio
    async def test_idle_budget_blocks_when_over_threshold(self):
        """Daemon tick is blocked when budget ratio exceeds idle cap."""
        import leader.kairos as mod

        blocked_snap = _mock_heartbeat_snapshot(budget_blocked=True, budget_ratio=0.35)
        mock_hb = AsyncMock()
        mock_hb.scan = AsyncMock(return_value=blocked_snap)

        daemon = mod.KairosDaemon()
        daemon._heartbeat = mock_hb
        daemon._suggester = MagicMock()
        daemon._autodream = MagicMock()
        daemon._running = True

        with patch("leader.kairos._emit_drvp", new_callable=AsyncMock) as emit:
            await daemon._tick()

        # Should emit heartbeat tick + blocked, but NOT proactive suggestion
        event_types = [c[0][0] for c in emit.call_args_list]
        assert "kairos.blocked" in event_types
        # Proactive scan should not run when blocked
        daemon._suggester.scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_idle_budget_allows_when_under_threshold(self):
        """Daemon tick proceeds normally when under budget."""
        import leader.kairos as mod

        ok_snap = _mock_heartbeat_snapshot(budget_blocked=False, budget_ratio=0.05)
        mock_hb = AsyncMock()
        mock_hb.scan = AsyncMock(return_value=ok_snap)

        mock_suggester = MagicMock()
        mock_suggester.scan.return_value = []

        daemon = mod.KairosDaemon()
        daemon._heartbeat = mock_hb
        daemon._suggester = mock_suggester
        daemon._autodream = MagicMock()
        daemon._running = True

        with patch("leader.kairos._emit_drvp", new_callable=AsyncMock):
            await daemon._tick()

        # Proactive scan should run when not blocked
        mock_suggester.scan.assert_called_once()
