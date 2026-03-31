"""Webhook dispatcher — async delivery with HMAC signatures and retry.

Delivers webhook payloads to subscriber URLs with:
- HMAC-SHA256 signature in X-OAS-Signature header
- Exponential backoff retry (1s, 5s, 30s, 5m)
- Dead letter log for permanently failed deliveries
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from oas_core.webhooks.registry import WebhookRegistry, WebhookSubscription

__all__ = ["WebhookDispatcher"]

logger = logging.getLogger("oas.webhooks.dispatcher")

_RETRY_DELAYS = [1.0, 5.0, 30.0, 300.0]  # seconds
_MAX_RETRIES = 4


@dataclass
class DeliveryResult:
    """Result of a single webhook delivery attempt."""

    subscription_id: str
    url: str
    status_code: int = 0
    success: bool = False
    error: str = ""
    attempts: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class DeadLetterEntry:
    """A permanently failed delivery."""

    subscription_id: str
    event_type: str
    payload: dict[str, Any]
    error: str
    attempts: int
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class WebhookDispatcher:
    """Delivers webhook events to registered subscribers.

    Usage::

        dispatcher = WebhookDispatcher(registry, http_client=httpx_client)
        results = await dispatcher.dispatch("request.completed", {
            "request_id": "req_123",
            "status": "ok",
        })
    """

    def __init__(
        self,
        registry: WebhookRegistry,
        *,
        http_client: Any | None = None,
        max_retries: int = _MAX_RETRIES,
    ):
        self._registry = registry
        self._http = http_client
        self._max_retries = max_retries
        self._dead_letters: list[DeadLetterEntry] = []

    async def dispatch(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        request_id: str = "",
    ) -> list[DeliveryResult]:
        """Dispatch an event to all matching subscribers."""
        subscribers = self._registry.find_matching(event_type)
        if not subscribers:
            return []

        envelope = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "payload": payload,
        }

        tasks = [
            self._deliver(sub, envelope)
            for sub in subscribers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        delivery_results = []
        for r in results:
            if isinstance(r, DeliveryResult):
                delivery_results.append(r)
            elif isinstance(r, Exception):
                logger.warning("webhook_dispatch_error", extra={"error": str(r)})

        return delivery_results

    async def _deliver(
        self,
        subscription: WebhookSubscription,
        envelope: dict[str, Any],
    ) -> DeliveryResult:
        """Deliver to a single subscriber with retries."""
        body = json.dumps(envelope, default=str)
        signature = self._sign(body, subscription.secret)

        for attempt in range(self._max_retries + 1):
            try:
                status_code = await self._send_http(
                    subscription.url,
                    body,
                    signature,
                )

                subscription.total_deliveries += 1

                if 200 <= status_code < 300:
                    subscription.successful_deliveries += 1
                    return DeliveryResult(
                        subscription_id=subscription.subscription_id,
                        url=subscription.url,
                        status_code=status_code,
                        success=True,
                        attempts=attempt + 1,
                    )

                # Non-2xx: retry
                if attempt < self._max_retries:
                    delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                    await asyncio.sleep(delay)

            except Exception as e:
                subscription.total_deliveries += 1
                if attempt < self._max_retries:
                    delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                    await asyncio.sleep(delay)
                else:
                    subscription.failed_deliveries += 1
                    self._dead_letters.append(DeadLetterEntry(
                        subscription_id=subscription.subscription_id,
                        event_type=envelope.get("event_type", ""),
                        payload=envelope.get("payload", {}),
                        error=str(e)[:200],
                        attempts=attempt + 1,
                    ))
                    return DeliveryResult(
                        subscription_id=subscription.subscription_id,
                        url=subscription.url,
                        success=False,
                        error=str(e)[:200],
                        attempts=attempt + 1,
                    )

        # All retries exhausted with non-2xx
        subscription.failed_deliveries += 1
        self._dead_letters.append(DeadLetterEntry(
            subscription_id=subscription.subscription_id,
            event_type=envelope.get("event_type", ""),
            payload=envelope.get("payload", {}),
            error=f"Non-2xx after {self._max_retries + 1} attempts",
            attempts=self._max_retries + 1,
        ))
        return DeliveryResult(
            subscription_id=subscription.subscription_id,
            url=subscription.url,
            success=False,
            error="max_retries_exhausted",
            attempts=self._max_retries + 1,
        )

    async def _send_http(self, url: str, body: str, signature: str) -> int:
        """Send HTTP POST. Returns status code."""
        headers = {
            "Content-Type": "application/json",
            "X-OAS-Signature": f"sha256={signature}",
            "User-Agent": "OAS-Webhook/1.0",
        }

        if self._http:
            resp = await self._http.post(url, content=body, headers=headers)
            return resp.status_code

        # No HTTP client — simulate success for testing
        logger.debug("webhook_simulated", extra={"url": url})
        return 200

    @staticmethod
    def _sign(body: str, secret: str) -> str:
        """HMAC-SHA256 signature."""
        return hmac.new(
            secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()

    @property
    def dead_letter_count(self) -> int:
        return len(self._dead_letters)

    def get_dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent dead letter entries."""
        entries = self._dead_letters[-limit:]
        return [
            {
                "subscription_id": e.subscription_id,
                "event_type": e.event_type,
                "error": e.error,
                "attempts": e.attempts,
                "timestamp": e.timestamp,
            }
            for e in entries
        ]
