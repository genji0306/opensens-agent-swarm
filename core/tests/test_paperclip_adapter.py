"""Tests for oas_core.adapters.paperclip — Paperclip REST client."""
import json

import httpx
import pytest

from oas_core.adapters.paperclip import PaperclipClient, PaperclipError


def _mock_transport(handler):
    """Create an httpx MockTransport from a request handler."""
    return httpx.MockTransport(handler)


class TestPaperclipClient:
    @pytest.fixture
    def client(self, company_id):
        return PaperclipClient(
            base_url="http://paperclip.test",
            api_key="test-key",
            company_id=company_id,
        )

    async def test_report_cost(self, client, company_id):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"id": "evt_1"})

        client._client = httpx.AsyncClient(
            base_url="http://paperclip.test",
            transport=_mock_transport(handler),
        )

        result = await client.report_cost(
            agent_id="agent_1", provider="anthropic", model="claude-sonnet",
            input_tokens=100, output_tokens=50, cost_cents=5,
        )
        assert result == {"id": "evt_1"}
        assert f"/api/companies/{company_id}/cost-events" in captured["url"]
        assert captured["body"]["agentId"] == "agent_1"
        assert captured["body"]["costCents"] == 5
        await client.close()

    async def test_create_issue(self, client, company_id):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(201, json={"id": "ISS-1", "key": "DL-1"})

        client._client = httpx.AsyncClient(
            base_url="http://paperclip.test",
            transport=_mock_transport(handler),
        )

        result = await client.create_issue("Test issue", description="desc")
        assert result["key"] == "DL-1"
        assert captured["body"]["title"] == "Test issue"
        assert captured["body"]["description"] == "desc"
        await client.close()

    async def test_get_agent_budget(self, client):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": "agent_1", "budgetMonthlyCents": 5000,
            })

        client._client = httpx.AsyncClient(
            base_url="http://paperclip.test",
            transport=_mock_transport(handler),
        )

        result = await client.get_agent_budget("agent_1")
        assert result["budgetMonthlyCents"] == 5000
        await client.close()

    async def test_error_raises_paperclip_error(self, client):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="Forbidden")

        client._client = httpx.AsyncClient(
            base_url="http://paperclip.test",
            transport=_mock_transport(handler),
        )

        with pytest.raises(PaperclipError) as exc_info:
            await client.report_cost(
                agent_id="a", provider="x", model="y",
                input_tokens=0, output_tokens=0, cost_cents=0,
            )
        assert exc_info.value.status_code == 403
        await client.close()

    async def test_log_activity(self, client, company_id):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": "act_1"})

        client._client = httpx.AsyncClient(
            base_url="http://paperclip.test",
            transport=_mock_transport(handler),
        )

        result = await client.log_activity(
            action="test.action", entity_type="task", entity_id="t_1",
            agent_id="agent_1", details={"foo": "bar"},
        )
        assert captured["body"]["action"] == "test.action"
        assert captured["body"]["agentId"] == "agent_1"
        assert captured["body"]["details"] == {"foo": "bar"}
        await client.close()

    async def test_bearer_token_header(self, client):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={})

        client._client = httpx.AsyncClient(
            base_url="http://paperclip.test",
            headers={"Authorization": "Bearer test-key", "Content-Type": "application/json"},
            transport=_mock_transport(handler),
        )

        await client.get_dashboard()
        assert captured["auth"] == "Bearer test-key"
        await client.close()
