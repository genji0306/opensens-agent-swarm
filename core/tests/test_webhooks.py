"""Tests for the webhook event layer."""

import pytest

from oas_core.webhooks.registry import WebhookRegistry, WebhookSubscription
from oas_core.webhooks.dispatcher import WebhookDispatcher


class TestWebhookRegistry:
    def test_create_subscription(self):
        registry = WebhookRegistry()
        sub = registry.create(
            url="https://example.com/hook",
            event_types=["request.completed"],
        )
        assert sub.url == "https://example.com/hook"
        assert sub.active is True
        assert registry.count == 1

    def test_find_matching(self):
        registry = WebhookRegistry()
        registry.create(url="https://a.com", event_types=["request.completed"])
        registry.create(url="https://b.com", event_types=["campaign.step.completed"])
        registry.create(url="https://c.com")  # all events

        matching = registry.find_matching("request.completed")
        assert len(matching) == 2  # a.com + c.com (wildcard)

    def test_inactive_not_matched(self):
        registry = WebhookRegistry()
        sub = registry.create(url="https://a.com", event_types=["request.completed"])
        registry.update(sub.subscription_id, active=False)

        matching = registry.find_matching("request.completed")
        assert len(matching) == 0

    def test_delete_subscription(self):
        registry = WebhookRegistry()
        sub = registry.create(url="https://a.com")
        assert registry.delete(sub.subscription_id) is True
        assert registry.count == 0

    def test_update_subscription(self):
        registry = WebhookRegistry()
        sub = registry.create(url="https://a.com")
        updated = registry.update(sub.subscription_id, url="https://b.com")
        assert updated is not None
        assert updated.url == "https://b.com"

    def test_list_by_company(self):
        registry = WebhookRegistry()
        registry.create(url="https://a.com", company_id="co_1")
        registry.create(url="https://b.com", company_id="co_2")

        co1_subs = registry.list_all(company_id="co_1")
        assert len(co1_subs) == 1

    def test_subscription_to_dict(self):
        sub = WebhookSubscription(url="https://test.com")
        d = sub.to_dict()
        assert d["url"] == "https://test.com"
        assert "subscription_id" in d


class TestWebhookDispatcher:
    @pytest.mark.asyncio
    async def test_dispatch_no_subscribers(self):
        registry = WebhookRegistry()
        dispatcher = WebhookDispatcher(registry)
        results = await dispatcher.dispatch("test.event", {"key": "value"})
        assert results == []

    @pytest.mark.asyncio
    async def test_dispatch_simulated_success(self):
        registry = WebhookRegistry()
        registry.create(url="https://example.com/hook", event_types=["test.event"])
        dispatcher = WebhookDispatcher(registry, max_retries=0)

        results = await dispatcher.dispatch("test.event", {"data": "hello"})
        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_signature_generation(self):
        sig = WebhookDispatcher._sign('{"test": true}', "secret123")
        assert len(sig) == 64  # SHA256 hex digest

    @pytest.mark.asyncio
    async def test_dispatch_multiple_subscribers(self):
        registry = WebhookRegistry()
        registry.create(url="https://a.com/hook")
        registry.create(url="https://b.com/hook")
        dispatcher = WebhookDispatcher(registry, max_retries=0)

        results = await dispatcher.dispatch("any.event", {})
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_delivery_stats_tracked(self):
        registry = WebhookRegistry()
        sub = registry.create(url="https://a.com")
        dispatcher = WebhookDispatcher(registry, max_retries=0)

        await dispatcher.dispatch("test", {})
        assert sub.total_deliveries == 1
        assert sub.successful_deliveries == 1
