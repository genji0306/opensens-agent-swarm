"""Paperclip REST client for OAS Core.

Used by the OAS middleware pipeline to report cost events, create issues,
request approvals, and query agent budgets. Authenticates via agent API key
(Bearer token in Authorization header).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

__all__ = ["PaperclipClient", "PaperclipError"]

logger = logging.getLogger("oas.adapters.paperclip")


class PaperclipError(Exception):
    """Raised when a Paperclip API call fails."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Paperclip {status_code}: {detail}")


class PaperclipClient:
    """Async client for the Paperclip REST API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        company_id: str,
        *,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.company_id = company_id
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        client = await self._get_client()
        resp = await client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise PaperclipError(resp.status_code, detail)
        return resp.json() if resp.content else {}

    # --- Cost Events ---

    async def report_cost(
        self,
        agent_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_cents: int,
        *,
        issue_id: str | None = None,
        project_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> dict:
        """POST /api/companies/:companyId/cost-events"""
        body: dict[str, Any] = {
            "agentId": agent_id,
            "provider": provider,
            "model": model,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "costCents": cost_cents,
            "occurredAt": (occurred_at or datetime.now(timezone.utc)).isoformat(),
        }
        if issue_id:
            body["issueId"] = issue_id
        if project_id:
            body["projectId"] = project_id
        return await self._request(
            "POST", f"/api/companies/{self.company_id}/cost-events", json=body
        )

    async def get_cost_summary(
        self,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """GET /api/companies/:companyId/costs/summary"""
        params: dict[str, str] = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return await self._request(
            "GET", f"/api/companies/{self.company_id}/costs/summary", params=params
        )

    # --- Issues ---

    async def create_issue(
        self,
        title: str,
        *,
        description: str | None = None,
        assignee_agent_id: str | None = None,
        goal_id: str | None = None,
        priority: str = "medium",
        status: str = "backlog",
    ) -> dict:
        """POST /api/companies/:companyId/issues"""
        body: dict[str, Any] = {"title": title, "priority": priority, "status": status}
        if description:
            body["description"] = description
        if assignee_agent_id:
            body["assigneeAgentId"] = assignee_agent_id
        if goal_id:
            body["goalId"] = goal_id
        return await self._request(
            "POST", f"/api/companies/{self.company_id}/issues", json=body
        )

    # --- Approvals ---

    async def create_approval(
        self,
        approval_type: str,
        requested_by_agent_id: str,
        payload: dict,
        *,
        issue_ids: list[str] | None = None,
    ) -> dict:
        """POST /api/companies/:companyId/approvals"""
        body: dict[str, Any] = {
            "type": approval_type,
            "requestedByAgentId": requested_by_agent_id,
            "payload": payload,
        }
        if issue_ids:
            body["issueIds"] = issue_ids
        return await self._request(
            "POST", f"/api/companies/{self.company_id}/approvals", json=body
        )

    async def get_approval(self, approval_id: str) -> dict:
        """GET /api/approvals/:approvalId"""
        return await self._request("GET", f"/api/approvals/{approval_id}")

    # --- Agent / Budget ---

    async def get_agent_budget(self, agent_id: str) -> dict:
        """GET /api/agents/:agentId — returns agent record with budget fields."""
        return await self._request("GET", f"/api/agents/{agent_id}")

    # --- Dashboard ---

    async def get_dashboard(self) -> dict:
        """GET /api/companies/:companyId/dashboard"""
        return await self._request(
            "GET", f"/api/companies/{self.company_id}/dashboard"
        )

    # --- Activity Log ---

    # --- Goals (Research Program Hierarchy) ---

    async def create_goal(
        self,
        title: str,
        level: str,
        *,
        description: str | None = None,
        parent_id: str | None = None,
        owner_agent_id: str | None = None,
        target_date: str | None = None,
    ) -> dict:
        """POST /api/companies/:companyId/goals

        Create a goal in the research program hierarchy.

        Args:
            title: Goal title
            level: "objective" | "milestone" | "task"
            description: Detailed description
            parent_id: Parent goal ID (for nesting)
            owner_agent_id: Agent responsible for this goal
            target_date: ISO date for target completion
        """
        body: dict[str, Any] = {"title": title, "level": level}
        if description:
            body["description"] = description
        if parent_id:
            body["parentId"] = parent_id
        if owner_agent_id:
            body["ownerAgentId"] = owner_agent_id
        if target_date:
            body["targetDate"] = target_date
        return await self._request(
            "POST", f"/api/companies/{self.company_id}/goals", json=body
        )

    async def get_goals(
        self,
        *,
        parent_id: str | None = None,
        level: str | None = None,
    ) -> list[dict]:
        """GET /api/companies/:companyId/goals

        List goals, optionally filtered by parent or level.
        """
        params: dict[str, str] = {}
        if parent_id:
            params["parentId"] = parent_id
        if level:
            params["level"] = level
        result = await self._request(
            "GET", f"/api/companies/{self.company_id}/goals", params=params
        )
        return result.get("goals", result) if isinstance(result, dict) else result

    async def update_goal(
        self,
        goal_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        title: str | None = None,
    ) -> dict:
        """PATCH /api/companies/:companyId/goals/:goalId"""
        body: dict[str, Any] = {}
        if status:
            body["status"] = status
        if progress is not None:
            body["progress"] = progress
        if title:
            body["title"] = title
        return await self._request(
            "PATCH", f"/api/companies/{self.company_id}/goals/{goal_id}", json=body
        )

    async def link_issue_to_goal(self, issue_id: str, goal_id: str) -> dict:
        """Link an existing issue to a goal in the hierarchy."""
        return await self._request(
            "POST",
            f"/api/companies/{self.company_id}/goals/{goal_id}/issues",
            json={"issueId": issue_id},
        )

    # --- Issues (additional) ---

    async def get_issues(
        self,
        *,
        status: str | None = None,
        assignee_agent_id: str | None = None,
    ) -> list[dict]:
        """GET /api/companies/:companyId/issues"""
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if assignee_agent_id:
            params["assigneeAgentId"] = assignee_agent_id
        result = await self._request(
            "GET", f"/api/companies/{self.company_id}/issues", params=params
        )
        return result.get("issues", result) if isinstance(result, dict) else result

    async def update_issue(
        self,
        issue_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        description: str | None = None,
    ) -> dict:
        """PATCH /api/companies/:companyId/issues/:issueId"""
        body: dict[str, Any] = {}
        if status:
            body["status"] = status
        if title:
            body["title"] = title
        if description:
            body["description"] = description
        return await self._request(
            "PATCH", f"/api/companies/{self.company_id}/issues/{issue_id}", json=body
        )

    async def get_costs_by_agent(self) -> list[dict]:
        """GET /api/companies/:companyId/costs/by-agent"""
        result = await self._request(
            "GET", f"/api/companies/{self.company_id}/costs/by-agent"
        )
        return result if isinstance(result, list) else result.get("agents", [])

    # --- Activity Log ---

    async def log_activity(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        *,
        actor_id: str | None = None,
        agent_id: str | None = None,
        details: dict | None = None,
    ) -> dict:
        """POST /api/companies/:companyId/activity"""
        body: dict[str, Any] = {
            "actorType": "agent",
            "actorId": actor_id or agent_id or "system",
            "action": action,
            "entityType": entity_type,
            "entityId": entity_id,
        }
        if agent_id:
            body["agentId"] = agent_id
        if details:
            body["details"] = details
        return await self._request(
            "POST", f"/api/companies/{self.company_id}/activity", json=body
        )
