"""Tests for oas_core.middleware.governance — issue tracking and approval gates."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oas_core.middleware.governance import GovernanceMiddleware


@pytest.fixture
def mock_paperclip():
    client = MagicMock()
    client.create_issue = AsyncMock(return_value={"id": "iss_1", "key": "DL-42"})
    client.log_activity = AsyncMock(return_value={"id": "act_1"})
    client.create_approval = AsyncMock(return_value={"id": "apr_1", "status": "pending"})
    client.get_approval = AsyncMock(return_value={"id": "apr_1", "status": "approved"})
    return client


@pytest.fixture
def gov(mock_paperclip):
    return GovernanceMiddleware(
        paperclip=mock_paperclip,
        agent_id="agt_leader",
        approval_timeout=1.0,
        approval_poll_interval=0.1,
    )


@pytest.fixture
def gov_no_paperclip():
    return GovernanceMiddleware(paperclip=None, agent_id="agt_leader")


class TestOpenIssue:
    async def test_creates_issue(self, gov, mock_paperclip):
        with patch("oas_core.middleware.governance.emit", new_callable=AsyncMock):
            issue = await gov.open_issue(
                request_id="req_1",
                title="Research quantum sensors",
                agent_name="leader",
                device="leader",
            )

        assert issue["id"] == "iss_1"
        assert issue["key"] == "DL-42"
        mock_paperclip.create_issue.assert_called_once()
        call_kwargs = mock_paperclip.create_issue.call_args
        assert call_kwargs.kwargs["status"] == "in_progress"

    async def test_returns_none_without_paperclip(self, gov_no_paperclip):
        issue = await gov_no_paperclip.open_issue(
            request_id="req_1",
            title="Test",
            agent_name="leader",
            device="leader",
        )
        assert issue is None

    async def test_handles_paperclip_error(self, gov, mock_paperclip):
        from oas_core.adapters.paperclip import PaperclipError
        mock_paperclip.create_issue = AsyncMock(
            side_effect=PaperclipError(500, "Internal error")
        )

        with patch("oas_core.middleware.governance.emit", new_callable=AsyncMock):
            issue = await gov.open_issue(
                request_id="req_1",
                title="Test",
                agent_name="leader",
                device="leader",
            )
        assert issue is None


class TestUpdateIssueStatus:
    async def test_logs_activity(self, gov, mock_paperclip):
        await gov.update_issue_status("iss_1", "in_progress")
        mock_paperclip.log_activity.assert_called_once()
        call_args = mock_paperclip.log_activity.call_args
        assert call_args.kwargs["action"] == "issue.status.in_progress"

    async def test_noop_without_paperclip(self, gov_no_paperclip):
        await gov_no_paperclip.update_issue_status("iss_1", "done")
        # Should not raise


class TestCloseIssue:
    async def test_logs_done_status(self, gov, mock_paperclip):
        with patch("oas_core.middleware.governance.emit", new_callable=AsyncMock):
            await gov.close_issue("iss_1", "Results summary", request_id="req_1")

        mock_paperclip.log_activity.assert_called_once()
        call_args = mock_paperclip.log_activity.call_args
        assert "done" in call_args.kwargs["action"]
        assert call_args.kwargs["details"]["result_summary"] == "Results summary"


class TestCampaignApproval:
    async def test_single_step_auto_approved(self, gov):
        plan = [{"step": 1, "command": "research", "args": "quantum"}]
        result = await gov.request_campaign_approval("req_1", plan)
        assert result["approved"] is True
        assert result["reason"] == "single_step_auto"

    async def test_multi_step_creates_approval(self, gov, mock_paperclip):
        plan = [
            {"step": 1, "command": "research", "args": "quantum"},
            {"step": 2, "command": "simulate", "args": "model"},
        ]

        with patch("oas_core.middleware.governance.emit", new_callable=AsyncMock):
            result = await gov.request_campaign_approval("req_1", plan)

        assert result["approved"] is True
        assert result["approval_id"] == "apr_1"
        mock_paperclip.create_approval.assert_called_once()

    async def test_rejected_approval(self, gov, mock_paperclip):
        mock_paperclip.get_approval = AsyncMock(
            return_value={"id": "apr_1", "status": "rejected"}
        )
        plan = [
            {"step": 1, "command": "research", "args": "a"},
            {"step": 2, "command": "analyze", "args": "b"},
        ]

        with patch("oas_core.middleware.governance.emit", new_callable=AsyncMock):
            result = await gov.request_campaign_approval("req_1", plan)

        assert result["approved"] is False
        assert result["reason"] == "rejected"

    async def test_timeout_returns_timeout(self, gov, mock_paperclip):
        mock_paperclip.get_approval = AsyncMock(
            return_value={"id": "apr_1", "status": "pending"}
        )
        gov._approval_timeout = 0.2
        gov._poll_interval = 0.05

        plan = [
            {"step": 1, "command": "research", "args": "a"},
            {"step": 2, "command": "analyze", "args": "b"},
        ]

        with patch("oas_core.middleware.governance.emit", new_callable=AsyncMock):
            result = await gov.request_campaign_approval("req_1", plan)

        assert result["approved"] is False
        assert result["reason"] == "timeout"

    async def test_no_paperclip_auto_approves(self, gov_no_paperclip):
        plan = [
            {"step": 1, "command": "research", "args": "a"},
            {"step": 2, "command": "analyze", "args": "b"},
        ]
        result = await gov_no_paperclip.request_campaign_approval("req_1", plan)
        assert result["approved"] is True
        assert result["reason"] == "paperclip_unavailable"

    async def test_paperclip_error_fails_closed(self, gov, mock_paperclip):
        from oas_core.adapters.paperclip import PaperclipError
        mock_paperclip.create_approval = AsyncMock(
            side_effect=PaperclipError(500, "Server error")
        )
        plan = [
            {"step": 1, "command": "research", "args": "a"},
            {"step": 2, "command": "analyze", "args": "b"},
        ]

        with patch("oas_core.middleware.governance.emit", new_callable=AsyncMock):
            result = await gov.request_campaign_approval("req_1", plan)

        assert result["approved"] is False
        assert "fail_closed" in result["reason"]
