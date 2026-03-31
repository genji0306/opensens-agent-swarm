"""Campaign persistence — checkpoint save/restore for campaign resume.

Persists campaign state after each step completion so that interrupted
campaigns can be resumed from the last checkpoint. Uses JSONL files
as the primary store with an optional Redis backend.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oas_core.schemas.campaign import CampaignSchema, CampaignStatus

__all__ = ["CampaignStore", "get_campaign_store"]

logger = logging.getLogger("oas.schemas.persistence")


class CampaignStore:
    """Persistent campaign state store.

    Saves campaign checkpoints to disk (JSONL) after each step completion.
    Supports listing active campaigns and restoring from checkpoint for resume.

    Usage::

        store = CampaignStore(base_dir=Path("~/.darklab/campaigns"))
        await store.save(campaign)
        campaign = await store.load(campaign_id)
        active = await store.list_active()
    """

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = Path.home() / ".darklab" / "campaigns"
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _campaign_path(self, campaign_id: str) -> Path:
        return self._base_dir / f"{campaign_id}.json"

    async def save(self, campaign: CampaignSchema) -> None:
        """Save campaign checkpoint to disk."""
        path = self._campaign_path(campaign.campaign_id)
        data = campaign.to_checkpoint()
        path.write_text(json.dumps(data, default=str, indent=2))
        logger.debug(
            "campaign_saved",
            extra={"campaign_id": campaign.campaign_id, "status": campaign.status.value},
        )

    async def load(self, campaign_id: str) -> CampaignSchema | None:
        """Load campaign from checkpoint."""
        path = self._campaign_path(campaign_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return CampaignSchema.from_checkpoint(data)
        except Exception as e:
            logger.warning("campaign_load_failed", extra={"campaign_id": campaign_id, "error": str(e)})
            return None

    async def delete(self, campaign_id: str) -> bool:
        """Delete a campaign checkpoint."""
        path = self._campaign_path(campaign_id)
        if path.exists():
            path.unlink()
            return True
        return False

    async def list_active(self) -> list[CampaignSchema]:
        """List all campaigns that are not in a terminal state."""
        terminal = {CampaignStatus.COMPLETED, CampaignStatus.FAILED, CampaignStatus.CANCELLED}
        result = []
        for path in self._base_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                campaign = CampaignSchema.from_checkpoint(data)
                if campaign.status not in terminal:
                    result.append(campaign)
            except Exception:
                continue
        return sorted(result, key=lambda c: c.updated_at, reverse=True)

    async def list_all(self, *, limit: int = 50) -> list[CampaignSchema]:
        """List all campaigns, most recent first."""
        result = []
        for path in sorted(self._base_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(result) >= limit:
                break
            try:
                data = json.loads(path.read_text())
                result.append(CampaignSchema.from_checkpoint(data))
            except Exception:
                continue
        return result

    async def find_by_request_id(self, request_id: str) -> CampaignSchema | None:
        """Find a campaign by its request ID."""
        for path in self._base_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                if data.get("request_id") == request_id:
                    return CampaignSchema.from_checkpoint(data)
            except Exception:
                continue
        return None


_store: CampaignStore | None = None


def get_campaign_store(base_dir: Path | None = None) -> CampaignStore:
    """Get the singleton campaign store."""
    global _store
    if _store is None:
        _store = CampaignStore(base_dir)
    return _store
