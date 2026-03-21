"""Tests for pre-dispatch hooks (budget check + issue creation)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from shared.models import Task, TaskType


def _make_task(text: str = "test request", source: str = "picoclaw") -> Task:
    return Task(
        task_id="test-123",
        task_type=TaskType.RESEARCH,
        user_id=0,
        payload={"text": text, "source": source},
    )


class TestPreDispatchHook:
    """Tests for the pre_dispatch_hook function."""

    @pytest.mark.asyncio
    async def test_passes_when_no_middleware(self):
        """Hook should return None (no block) when middleware is not configured."""
        with patch("leader.dispatch._get_budget_mw", return_value=None), \
             patch("leader.dispatch._get_governance", return_value=None):
            from leader.dispatch import pre_dispatch_hook
            task = _make_task()
            result = await pre_dispatch_hook(task, "test request")
            assert result is None

    @pytest.mark.asyncio
    async def test_blocks_on_budget_exhausted(self):
        """Hook should return blocked dict when budget is exhausted."""
        mock_budget = AsyncMock()
        mock_budget.check_budget = AsyncMock(side_effect=RuntimeError("Budget exhausted"))

        with patch("leader.dispatch._get_budget_mw", return_value=mock_budget), \
             patch("leader.dispatch._get_governance", return_value=None):
            from leader.dispatch import pre_dispatch_hook
            task = _make_task()
            result = await pre_dispatch_hook(task, "expensive research")
            assert result is not None
            assert result["blocked"] is True
            assert result["reason"] == "budget_exhausted"

    @pytest.mark.asyncio
    async def test_budget_passes_through(self):
        """Hook should return None when budget check passes."""
        mock_budget = AsyncMock()
        mock_budget.check_budget = AsyncMock(return_value=None)

        with patch("leader.dispatch._get_budget_mw", return_value=mock_budget), \
             patch("leader.dispatch._get_governance", return_value=None):
            from leader.dispatch import pre_dispatch_hook
            task = _make_task()
            result = await pre_dispatch_hook(task, "research request")
            assert result is None
            mock_budget.check_budget.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_issue_for_picoclaw(self):
        """Hook should auto-create a Paperclip issue for PicoClaw requests."""
        mock_gov = AsyncMock()
        mock_gov.open_issue = AsyncMock(return_value={"id": "issue-1", "key": "DL-99"})

        with patch("leader.dispatch._get_budget_mw", return_value=None), \
             patch("leader.dispatch._get_governance", return_value=mock_gov):
            from leader.dispatch import pre_dispatch_hook
            task = _make_task(source="picoclaw")
            result = await pre_dispatch_hook(task, "/research MnO2")
            assert result is None
            mock_gov.open_issue.assert_awaited_once()
            assert task.payload["_issue_id"] == "issue-1"
            assert task.payload["_issue_key"] == "DL-99"

    @pytest.mark.asyncio
    async def test_creates_issue_for_telegram(self):
        """Hook should also create issues for telegram-sourced requests."""
        mock_gov = AsyncMock()
        mock_gov.open_issue = AsyncMock(return_value={"id": "issue-2", "key": "DL-100"})

        with patch("leader.dispatch._get_budget_mw", return_value=None), \
             patch("leader.dispatch._get_governance", return_value=mock_gov):
            from leader.dispatch import pre_dispatch_hook
            task = _make_task(source="telegram")
            await pre_dispatch_hook(task, "some request")
            mock_gov.open_issue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_issue_for_internal_source(self):
        """Hook should NOT create issues for internal/unknown sources."""
        mock_gov = AsyncMock()
        mock_gov.open_issue = AsyncMock()

        with patch("leader.dispatch._get_budget_mw", return_value=None), \
             patch("leader.dispatch._get_governance", return_value=mock_gov):
            from leader.dispatch import pre_dispatch_hook
            task = _make_task(source="internal")
            await pre_dispatch_hook(task, "internal op")
            mock_gov.open_issue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_issue_creation_failure_non_blocking(self):
        """Issue creation failure should NOT block the request."""
        mock_gov = AsyncMock()
        mock_gov.open_issue = AsyncMock(side_effect=Exception("Paperclip offline"))

        with patch("leader.dispatch._get_budget_mw", return_value=None), \
             patch("leader.dispatch._get_governance", return_value=mock_gov):
            from leader.dispatch import pre_dispatch_hook
            task = _make_task(source="picoclaw")
            result = await pre_dispatch_hook(task, "test")
            assert result is None  # Not blocked


class TestHandleWithHooks:
    """Integration tests verifying handle() uses the pre-dispatch hook."""

    @pytest.mark.asyncio
    async def test_handle_blocked_returns_error(self):
        """handle() should return error status when budget is exhausted."""
        mock_budget = AsyncMock()
        mock_budget.check_budget = AsyncMock(side_effect=RuntimeError("No budget"))

        with patch("leader.dispatch._get_budget_mw", return_value=mock_budget), \
             patch("leader.dispatch._get_governance", return_value=None), \
             patch("leader.dispatch._get_audit_mw", return_value=None), \
             patch("leader.dispatch._get_memory_mw", return_value=None):
            from leader.dispatch import handle
            task = _make_task(text="/research test")
            result = await handle(task)
            assert result.status == "error"
            assert result.result["blocked"] is True


class TestBoostCommand:
    """Test /boost command handler in dispatch."""

    @pytest.mark.asyncio
    async def test_boost_status(self):
        from leader.dispatch import _handle_boost_command
        task = _make_task(text="/boost status")
        result = await _handle_boost_command(task, "status")
        assert result.status == "ok"
        assert "boost" in result.result.get("action", "").lower()

    @pytest.mark.asyncio
    async def test_boost_on(self):
        from leader.dispatch import _handle_boost_command
        with patch("leader.dispatch._get_governance", return_value=None):
            task = _make_task(text="/boost on")
            result = await _handle_boost_command(task, "on")
            assert result.result["action"] == "boost_enabled"

    @pytest.mark.asyncio
    async def test_boost_off(self):
        from leader.dispatch import _handle_boost_command
        with patch("leader.dispatch._get_governance", return_value=None):
            task = _make_task(text="/boost off")
            result = await _handle_boost_command(task, "off")
            assert result.result["action"] == "boost_disabled"

    @pytest.mark.asyncio
    async def test_boost_invalid_action(self):
        from leader.dispatch import _handle_boost_command
        task = _make_task(text="/boost maybe")
        result = await _handle_boost_command(task, "maybe")
        assert result.status == "error"
