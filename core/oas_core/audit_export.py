"""Audit export bundle — one-command campaign audit trail export.

Collects campaign journal, lineage graph, cost attributions, approval
records, and DRVP events into a single ZIP file with SHA-256 checksum
manifest for integrity verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oas_core.campaign_journal import CampaignJournal, JournalReader
from oas_core.lineage import LineageGraph

__all__ = ["export_campaign_audit", "AuditBundle"]

logger = logging.getLogger("oas.audit_export")


class AuditBundle:
    """Collected audit data for a campaign."""

    def __init__(self, campaign_id: str):
        self.campaign_id = campaign_id
        self.journal_entries: list[dict[str, Any]] = []
        self.lineage_graph: dict[str, Any] = {}
        self.cost_attributions: list[dict[str, Any]] = []
        self.approval_records: list[dict[str, Any]] = []
        self.drvp_events: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {
            "campaign_id": campaign_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
        }


def export_campaign_audit(
    campaign_id: str,
    journal_dir: Path,
    output_path: Path | None = None,
    extra_data: dict[str, Any] | None = None,
) -> Path:
    """Export a complete audit trail for a campaign as a ZIP file.

    Args:
        campaign_id: The campaign to export.
        journal_dir: Directory containing campaign journals.
        output_path: Where to write the ZIP (default: temp file).
        extra_data: Optional additional data sections to include.

    Returns:
        Path to the created ZIP file.
    """
    bundle = AuditBundle(campaign_id)

    # 1. Load journal entries
    journal = CampaignJournal(journal_dir, campaign_id)
    bundle.journal_entries = [e.to_dict() for e in journal.entries()]

    # 2. Verify journal integrity
    ok, errors = journal.verify()
    bundle.metadata["journal_integrity"] = {
        "valid": ok,
        "errors": errors,
        "entry_count": len(bundle.journal_entries),
    }

    # 3. Build lineage graph from journal
    graph = LineageGraph()
    graph.build_from_journal(bundle.journal_entries)
    bundle.lineage_graph = graph.to_json()

    # 4. Extract cost and approval records from journal
    for entry in bundle.journal_entries:
        event_type = entry.get("event_type", "")
        if event_type == "cost.recorded":
            bundle.cost_attributions.append(entry)
        elif event_type in ("approval.recorded", "approval.requested"):
            bundle.approval_records.append(entry)

    # 5. Include extra data
    if extra_data:
        bundle.metadata["extra_sections"] = list(extra_data.keys())

    # 6. Write ZIP
    if output_path is None:
        output_path = Path(tempfile.mkdtemp()) / f"audit_{campaign_id}.zip"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write each section
        sections = {
            "manifest.json": bundle.metadata,
            "journal.json": bundle.journal_entries,
            "lineage.json": bundle.lineage_graph,
            "costs.json": bundle.cost_attributions,
            "approvals.json": bundle.approval_records,
        }

        if extra_data:
            for key, data in extra_data.items():
                sections[f"extra/{key}.json"] = data

        for filename, data in sections.items():
            content = json.dumps(data, indent=2, default=str).encode()
            checksums[filename] = hashlib.sha256(content).hexdigest()
            zf.writestr(filename, content)

        # Write checksum manifest last
        checksum_content = json.dumps(checksums, indent=2).encode()
        zf.writestr("checksums.sha256.json", checksum_content)

    logger.info(
        "audit_exported",
        extra={
            "campaign_id": campaign_id,
            "path": str(output_path),
            "entries": len(bundle.journal_entries),
            "files": len(checksums),
        },
    )

    return output_path


def verify_audit_bundle(zip_path: Path) -> tuple[bool, list[str]]:
    """Verify the integrity of an exported audit bundle.

    Returns (ok, error_messages).
    """
    errors: list[str] = []

    if not zip_path.exists():
        return False, ["ZIP file does not exist"]

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Read checksums
        try:
            checksum_data = json.loads(zf.read("checksums.sha256.json"))
        except KeyError:
            return False, ["Missing checksums.sha256.json"]

        # Verify each file
        for filename, expected_hash in checksum_data.items():
            try:
                content = zf.read(filename)
                actual_hash = hashlib.sha256(content).hexdigest()
                if actual_hash != expected_hash:
                    errors.append(
                        f"{filename}: hash mismatch "
                        f"(expected {expected_hash[:12]}..., got {actual_hash[:12]}...)"
                    )
            except KeyError:
                errors.append(f"{filename}: missing from archive")

    return len(errors) == 0, errors
