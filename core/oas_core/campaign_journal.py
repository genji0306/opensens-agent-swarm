"""Campaign journal — append-only event log with hash chain.

Records every state transition, decision, reflection, cost event, and
approval for a campaign. Each entry includes a SHA-256 hash of the
previous entry for tamper detection.

Files are stored as JSONL at ``{base_dir}/{campaign_id}.journal.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["CampaignJournal", "JournalEntry", "JournalReader"]

logger = logging.getLogger("oas.campaign_journal")

_GENESIS_HASH = "0" * 64  # SHA-256 of nothing — first entry's prev_hash


class JournalEntry:
    """A single journal entry with hash chain link."""

    __slots__ = (
        "timestamp",
        "campaign_id",
        "event_type",
        "actor",
        "payload",
        "prev_hash",
        "hash",
    )

    def __init__(
        self,
        campaign_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        prev_hash: str = _GENESIS_HASH,
    ):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.campaign_id = campaign_id
        self.event_type = event_type
        self.actor = actor
        self.payload = payload
        self.prev_hash = prev_hash
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """SHA-256 of (prev_hash + timestamp + event_type + actor + payload)."""
        content = (
            self.prev_hash
            + self.timestamp
            + self.event_type
            + self.actor
            + json.dumps(self.payload, sort_keys=True, default=str)
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "campaign_id": self.campaign_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalEntry:
        entry = cls.__new__(cls)
        entry.timestamp = data["timestamp"]
        entry.campaign_id = data["campaign_id"]
        entry.event_type = data["event_type"]
        entry.actor = data["actor"]
        entry.payload = data.get("payload", {})
        entry.prev_hash = data["prev_hash"]
        entry.hash = data["hash"]
        return entry


class CampaignJournal:
    """Append-only JSONL journal for a single campaign.

    Usage::

        journal = CampaignJournal(Path("/data/journals"), "camp_abc123")
        journal.record("campaign.started", "leader", {"objective": "..."})
        journal.record("step.completed", "academic", {"step": 1, "score": 0.85})

        # Verify integrity
        ok, errors = journal.verify()
    """

    def __init__(self, base_dir: Path, campaign_id: str):
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._campaign_id = campaign_id
        self._path = base_dir / f"{campaign_id}.journal.jsonl"
        self._last_hash = self._load_last_hash()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def campaign_id(self) -> str:
        return self._campaign_id

    def _load_last_hash(self) -> str:
        """Load the hash of the last entry, or genesis hash if empty."""
        if not self._path.exists():
            return _GENESIS_HASH
        last_line = ""
        try:
            with open(self._path) as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
            if last_line:
                data = json.loads(last_line)
                return data.get("hash", _GENESIS_HASH)
        except Exception:
            pass
        return _GENESIS_HASH

    def record(
        self,
        event_type: str,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> JournalEntry:
        """Append a new entry to the journal."""
        entry = JournalEntry(
            campaign_id=self._campaign_id,
            event_type=event_type,
            actor=actor,
            payload=payload or {},
            prev_hash=self._last_hash,
        )

        with open(self._path, "a") as f:
            f.write(json.dumps(entry.to_dict(), default=str) + "\n")

        self._last_hash = entry.hash
        logger.debug(
            "journal_entry",
            extra={
                "campaign_id": self._campaign_id,
                "event_type": event_type,
                "actor": actor,
            },
        )
        return entry

    def entries(self) -> list[JournalEntry]:
        """Read all journal entries."""
        if not self._path.exists():
            return []
        results: list[JournalEntry] = []
        with open(self._path) as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    results.append(JournalEntry.from_dict(json.loads(stripped)))
        return results

    def verify(self) -> tuple[bool, list[str]]:
        """Verify the hash chain integrity. Returns (ok, error_messages)."""
        entries = self.entries()
        if not entries:
            return True, []

        errors: list[str] = []
        expected_prev = _GENESIS_HASH

        for i, entry in enumerate(entries):
            # Check prev_hash links
            if entry.prev_hash != expected_prev:
                errors.append(
                    f"Entry {i}: prev_hash mismatch "
                    f"(expected {expected_prev[:12]}..., got {entry.prev_hash[:12]}...)"
                )

            # Recompute hash to verify integrity
            recomputed = JournalEntry(
                campaign_id=entry.campaign_id,
                event_type=entry.event_type,
                actor=entry.actor,
                payload=entry.payload,
                prev_hash=entry.prev_hash,
            )
            # Override timestamp to match original for hash recomputation
            recomputed.timestamp = entry.timestamp
            recomputed.hash = recomputed._compute_hash()
            if recomputed.hash != entry.hash:
                errors.append(
                    f"Entry {i}: hash mismatch "
                    f"(expected {recomputed.hash[:12]}..., got {entry.hash[:12]}...)"
                )

            expected_prev = entry.hash

        return len(errors) == 0, errors

    @property
    def entry_count(self) -> int:
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path) as f:
            for line in f:
                if line.strip():
                    count += 1
        return count


class JournalReader:
    """Query journal entries across campaigns."""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

    def list_campaigns(self) -> list[str]:
        """List all campaign IDs that have journals."""
        if not self._base_dir.exists():
            return []
        return [
            p.stem.replace(".journal", "")
            for p in self._base_dir.glob("*.journal.jsonl")
        ]

    def read(self, campaign_id: str) -> list[JournalEntry]:
        """Read all entries for a campaign."""
        journal = CampaignJournal(self._base_dir, campaign_id)
        return journal.entries()

    def query_by_type(
        self, campaign_id: str, event_type: str
    ) -> list[JournalEntry]:
        """Filter entries by event type."""
        return [e for e in self.read(campaign_id) if e.event_type == event_type]

    def query_by_time_range(
        self,
        campaign_id: str,
        start: str,
        end: str,
    ) -> list[JournalEntry]:
        """Filter entries by ISO timestamp range."""
        return [
            e
            for e in self.read(campaign_id)
            if start <= e.timestamp <= end
        ]
