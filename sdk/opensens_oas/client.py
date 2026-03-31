"""OAS Python SDK client — sync and async HTTP client for campaign management."""

from __future__ import annotations

import json
import logging
from typing import Any

__all__ = ["OASClient", "AsyncOASClient", "OASError"]

logger = logging.getLogger("opensens_oas")


class OASError(Exception):
    """Error from the OAS API."""

    def __init__(self, message: str, status_code: int = 0, detail: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class OASClient:
    """Synchronous OAS API client.

    Usage::

        client = OASClient("http://192.168.23.25:8100", api_key="...")
        campaigns = client.list_campaigns()
        result = client.create_campaign(objective="quantum dots")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        *,
        timeout: float = 30.0,
        http_client: Any | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._http = http_client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a synchronous HTTP request."""
        url = f"{self._base_url}{path}"
        if self._http:
            if method == "GET":
                resp = self._http.get(url, headers=self._headers(), timeout=self._timeout)
            elif method == "POST":
                resp = self._http.post(
                    url, json=body, headers=self._headers(), timeout=self._timeout
                )
            elif method == "DELETE":
                resp = self._http.delete(url, headers=self._headers(), timeout=self._timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if resp.status_code >= 400:
                raise OASError(
                    f"API error: {resp.status_code}",
                    status_code=resp.status_code,
                    detail=resp.text[:500],
                )
            return resp.json() if resp.text else {}

        # No HTTP client — return stub for testing
        return {"status": "ok", "method": method, "path": path}

    # --- Campaign Operations ---

    def create_campaign(
        self,
        objective: str,
        *,
        template: str = "",
        priority: str = "normal",
        budget_limit_usd: float | None = None,
    ) -> dict[str, Any]:
        """Create a new campaign."""
        body: dict[str, Any] = {"objective": objective, "priority": priority}
        if template:
            body["template"] = template
        if budget_limit_usd is not None:
            body["budget_limit_usd"] = budget_limit_usd
        return self._request("POST", "/campaign", body)

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Get campaign details."""
        return self._request("GET", f"/campaign/{campaign_id}")

    def list_campaigns(self, limit: int = 50) -> dict[str, Any]:
        """List recent campaigns."""
        return self._request("GET", f"/campaigns?limit={limit}")

    def cancel_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Cancel a running campaign."""
        return self._request("POST", f"/campaign/{campaign_id}/cancel", {})

    # --- Dispatch ---

    def dispatch(self, text: str) -> dict[str, Any]:
        """Send a text command to the dispatcher."""
        return self._request("POST", "/dispatch", {"text": text})

    # --- Templates ---

    def list_templates(self) -> dict[str, Any]:
        """List available campaign templates."""
        return self._request("GET", "/templates")

    # --- Webhooks ---

    def subscribe_webhook(
        self,
        url: str,
        event_types: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a webhook subscription."""
        body: dict[str, Any] = {"url": url}
        if event_types:
            body["event_types"] = event_types
        if description:
            body["description"] = description
        return self._request("POST", "/webhooks", body)

    def list_webhooks(self) -> dict[str, Any]:
        """List webhook subscriptions."""
        return self._request("GET", "/webhooks")

    def delete_webhook(self, subscription_id: str) -> dict[str, Any]:
        """Delete a webhook subscription."""
        return self._request("DELETE", f"/webhooks/{subscription_id}")

    # --- Results ---

    def get_results(self, limit: int = 20) -> dict[str, Any]:
        """Get recent research results."""
        return self._request("GET", f"/results?limit={limit}")

    # --- Health ---

    def health(self) -> dict[str, Any]:
        """Check API health."""
        return self._request("GET", "/health")


class AsyncOASClient:
    """Asynchronous OAS API client.

    Usage::

        async with AsyncOASClient("http://localhost:8100", api_key="...") as client:
            result = await client.create_campaign(objective="quantum dots")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        *,
        timeout: float = 30.0,
        http_client: Any | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._http = http_client

    async def __aenter__(self) -> AsyncOASClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an async HTTP request."""
        url = f"{self._base_url}{path}"
        if self._http:
            if method == "GET":
                resp = await self._http.get(url, headers=self._headers(), timeout=self._timeout)
            elif method == "POST":
                resp = await self._http.post(
                    url, json=body, headers=self._headers(), timeout=self._timeout
                )
            elif method == "DELETE":
                resp = await self._http.delete(url, headers=self._headers(), timeout=self._timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if resp.status_code >= 400:
                raise OASError(
                    f"API error: {resp.status_code}",
                    status_code=resp.status_code,
                    detail=resp.text[:500],
                )
            return resp.json() if resp.text else {}

        return {"status": "ok", "method": method, "path": path}

    async def create_campaign(self, objective: str, **kwargs: Any) -> dict[str, Any]:
        body: dict[str, Any] = {"objective": objective, **kwargs}
        return await self._request("POST", "/campaign", body)

    async def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/campaign/{campaign_id}")

    async def dispatch(self, text: str) -> dict[str, Any]:
        return await self._request("POST", "/dispatch", {"text": text})

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")
