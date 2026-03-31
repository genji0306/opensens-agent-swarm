"""OpenSens Agent Swarm Python SDK.

Minimal client for programmatic campaign management, webhook
subscriptions, and template operations.

Usage::

    from opensens_oas import OASClient

    client = OASClient("http://192.168.23.25:8100", api_key="...")
    campaign = client.create_campaign(
        objective="Research quantum dot electrodes",
        template="literature-review",
    )
    print(campaign["campaign_id"])
"""

from opensens_oas.client import OASClient, AsyncOASClient

__all__ = ["OASClient", "AsyncOASClient"]
__version__ = "0.1.0"
