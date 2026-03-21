"""Tests for oas_core.middleware.budget — BudgetMiddleware."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oas_core.middleware.budget import BudgetMiddleware
from oas_core.adapters.paperclip import PaperclipError


@pytest.fixture
def mock_paperclip():
    pc = AsyncMock()
    pc.get_agent_budget.return_value = {"budgetMonthlyCents": 10000}
    pc.get_cost_summary.return_value = {"totalCents": 2000}
    pc.report_cost.return_value = {"id": "evt_1"}
    return pc


@pytest.fixture
def middleware(mock_paperclip, agent_id):
    fallback = MagicMock()
    return BudgetMiddleware(
        paperclip=mock_paperclip,
        agent_id=agent_id,
        fallback_record=fallback,
    )


class TestCheckBudget:
    async def test_returns_paperclip_data(self, middleware):
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock):
            result = await middleware.check_budget("req_1", "leader", "leader")
        assert result["source"] == "paperclip"
        assert result["budget_cents"] == 10000
        assert result["spent_cents"] == 2000
        assert result["remaining_cents"] == 8000

    async def test_emits_drvp_budget_check(self, middleware):
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock) as mock_emit:
            await middleware.check_budget("req_1", "leader", "leader")
        # At least one BUDGET_CHECK event
        events = [call.args[0] for call in mock_emit.call_args_list]
        assert any(e.event_type.value == "budget.check" for e in events)

    async def test_warning_at_80_percent(self, middleware, mock_paperclip):
        mock_paperclip.get_cost_summary.return_value = {"totalCents": 8500}
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock) as mock_emit:
            await middleware.check_budget("req_1", "leader", "leader")
        events = [call.args[0] for call in mock_emit.call_args_list]
        assert any(e.event_type.value == "budget.warning" for e in events)

    async def test_exhausted_raises(self, middleware, mock_paperclip):
        mock_paperclip.get_cost_summary.return_value = {"totalCents": 10001}
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="exhausted"):
                await middleware.check_budget("req_1", "leader", "leader")

    async def test_paperclip_error_fallback(self, middleware, mock_paperclip):
        mock_paperclip.get_agent_budget.side_effect = PaperclipError(500, "down")
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock):
            result = await middleware.check_budget("req_1", "leader", "leader")
        assert result["source"] == "file_lock"

    async def test_no_paperclip_returns_file_lock(self, agent_id):
        mw = BudgetMiddleware(paperclip=None, agent_id=agent_id)
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock):
            result = await mw.check_budget("req_1", "leader", "leader")
        assert result["source"] == "file_lock"


class TestReportCost:
    async def test_reports_to_paperclip(self, middleware, mock_paperclip):
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock):
            await middleware.report_cost(
                "req_1", "leader", "leader",
                "anthropic", "claude-sonnet", 100, 50, 0.05,
            )
        mock_paperclip.report_cost.assert_called_once()
        kwargs = mock_paperclip.report_cost.call_args[1]
        assert kwargs["cost_cents"] == 5  # 0.05 * 100, rounded

    async def test_calls_fallback(self, middleware):
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock):
            await middleware.report_cost(
                "req_1", "leader", "leader",
                "anthropic", "claude-sonnet", 100, 50, 0.05,
            )
        middleware._fallback_record.assert_called_once_with(0.05, "anthropic", "claude-sonnet")

    async def test_emits_llm_completed_event(self, middleware):
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock) as mock_emit:
            await middleware.report_cost(
                "req_1", "leader", "leader",
                "anthropic", "claude-sonnet", 100, 50, 0.05,
            )
        events = [call.args[0] for call in mock_emit.call_args_list]
        assert any(e.event_type.value == "llm.call.completed" for e in events)

    async def test_paperclip_error_does_not_raise(self, middleware, mock_paperclip):
        mock_paperclip.report_cost.side_effect = PaperclipError(500, "down")
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock):
            await middleware.report_cost(
                "req_1", "leader", "leader",
                "anthropic", "claude-sonnet", 100, 50, 0.05,
            )
        # Should not raise — fallback still records
        middleware._fallback_record.assert_called_once()

    async def test_minimum_cost_cents_is_one(self, middleware, mock_paperclip):
        with patch("oas_core.middleware.budget.emit", new_callable=AsyncMock):
            await middleware.report_cost(
                "req_1", "leader", "leader",
                "gemini", "gemini-flash", 10, 10, 0.001,
            )
        kwargs = mock_paperclip.report_cost.call_args[1]
        assert kwargs["cost_cents"] >= 1
