"""Webhook subscription registry — CRUD for webhook endpoints."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = ["WebhookRegistry", "WebhookSubscription"]

logger = logging.getLogger("oas.webhooks.registry")


@dataclass
class WebhookSubscription:
    """A webhook subscription targeting an external URL."""

    subscription_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    url: str = ""
    event_types: list[str] = field(default_factory=list)  # empty = all events
    secret: str = field(default_factory=lambda: secrets.token_hex(32))
    active: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    description: str = ""
    company_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # Delivery stats
    total_deliveries: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0

    def matches_event(self, event_type: str) -> bool:
        """Check if this subscription should receive an event type."""
        if not self.active:
            return False
        if not self.event_types:
            return True  # subscribed to all events
        return event_type in self.event_types

    def to_dict(self) -> dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "url": self.url,
            "event_types": self.event_types,
            "active": self.active,
            "created_at": self.created_at,
            "description": self.description,
            "company_id": self.company_id,
            "total_deliveries": self.total_deliveries,
            "successful_deliveries": self.successful_deliveries,
            "failed_deliveries": self.failed_deliveries,
        }


class WebhookRegistry:
    """Manages webhook subscriptions.

    Usage::

        registry = WebhookRegistry()
        sub = registry.create(
            url="https://example.com/webhook",
            event_types=["request.completed", "campaign.step.completed"],
        )
        # Later
        matching = registry.find_matching("request.completed")
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, WebhookSubscription] = {}

    def create(
        self,
        url: str,
        event_types: list[str] | None = None,
        *,
        description: str = "",
        company_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WebhookSubscription:
        """Create a new webhook subscription."""
        sub = WebhookSubscription(
            url=url,
            event_types=event_types or [],
            description=description,
            company_id=company_id,
            metadata=metadata or {},
        )
        self._subscriptions[sub.subscription_id] = sub
        logger.info(
            "webhook_created",
            extra={"id": sub.subscription_id, "url": url, "events": event_types},
        )
        return sub

    def get(self, subscription_id: str) -> WebhookSubscription | None:
        return self._subscriptions.get(subscription_id)

    def update(
        self,
        subscription_id: str,
        *,
        url: str | None = None,
        event_types: list[str] | None = None,
        active: bool | None = None,
        description: str | None = None,
    ) -> WebhookSubscription | None:
        """Update an existing subscription."""
        sub = self._subscriptions.get(subscription_id)
        if not sub:
            return None
        if url is not None:
            sub.url = url
        if event_types is not None:
            sub.event_types = event_types
        if active is not None:
            sub.active = active
        if description is not None:
            sub.description = description
        return sub

    def delete(self, subscription_id: str) -> bool:
        """Delete a subscription."""
        return self._subscriptions.pop(subscription_id, None) is not None

    def find_matching(self, event_type: str) -> list[WebhookSubscription]:
        """Find all active subscriptions matching an event type."""
        return [
            sub for sub in self._subscriptions.values()
            if sub.matches_event(event_type)
        ]

    def list_all(self, company_id: str = "") -> list[WebhookSubscription]:
        """List all subscriptions, optionally filtered by company."""
        if company_id:
            return [
                s for s in self._subscriptions.values()
                if s.company_id == company_id
            ]
        return list(self._subscriptions.values())

    @property
    def count(self) -> int:
        return len(self._subscriptions)
