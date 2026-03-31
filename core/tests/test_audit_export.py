"""Tests for the audit export bundle."""

import json
import zipfile
import pytest
from pathlib import Path

from oas_core.audit_export import export_campaign_audit, verify_audit_bundle
from oas_core.campaign_journal import CampaignJournal


@pytest.fixture
def journal_dir(tmp_path):
    d = tmp_path / "journals"
    d.mkdir()
    return d


@pytest.fixture
def populated_journal(journal_dir):
    journal = CampaignJournal(journal_dir, "camp_audit")
    journal.record("campaign.started", "leader", {"objective": "test", "title": "Audit Test"})
    journal.record("step.started", "academic", {"step": 1, "command": "research"})
    journal.record("step.completed", "academic", {"step": 1, "depends_on": []})
    journal.record("cost.recorded", "academic", {"cost_id": "c1", "cost_usd": 0.05, "step_id": 1})
    journal.record("approval.recorded", "boss", {"approval_id": "ap1", "status": "approved"})
    journal.record("campaign.completed", "leader", {"status": "completed"})
    return journal


class TestAuditExport:
    def test_export_creates_zip(self, journal_dir, populated_journal):
        output = journal_dir / "output" / "audit.zip"
        path = export_campaign_audit("camp_audit", journal_dir, output)

        assert path.exists()
        assert path.suffix == ".zip"

    def test_export_contains_expected_files(self, journal_dir, populated_journal):
        output = journal_dir / "audit.zip"
        path = export_campaign_audit("camp_audit", journal_dir, output)

        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "journal.json" in names
            assert "lineage.json" in names
            assert "costs.json" in names
            assert "approvals.json" in names
            assert "checksums.sha256.json" in names

    def test_export_journal_contents(self, journal_dir, populated_journal):
        output = journal_dir / "audit.zip"
        path = export_campaign_audit("camp_audit", journal_dir, output)

        with zipfile.ZipFile(path) as zf:
            journal_data = json.loads(zf.read("journal.json"))
            assert len(journal_data) == 6

            costs_data = json.loads(zf.read("costs.json"))
            assert len(costs_data) == 1

            approvals_data = json.loads(zf.read("approvals.json"))
            assert len(approvals_data) == 1

    def test_export_integrity_verification(self, journal_dir, populated_journal):
        output = journal_dir / "audit.zip"
        path = export_campaign_audit("camp_audit", journal_dir, output)

        ok, errors = verify_audit_bundle(path)
        assert ok is True
        assert errors == []

    def test_verify_detects_corruption(self, journal_dir, populated_journal, tmp_path):
        output = journal_dir / "audit.zip"
        path = export_campaign_audit("camp_audit", journal_dir, output)

        # Corrupt the zip by modifying a file
        corrupted = tmp_path / "corrupted.zip"
        with zipfile.ZipFile(path) as zf_in:
            with zipfile.ZipFile(corrupted, "w") as zf_out:
                for name in zf_in.namelist():
                    data = zf_in.read(name)
                    if name == "journal.json":
                        data = b'[{"tampered": true}]'
                    zf_out.writestr(name, data)

        ok, errors = verify_audit_bundle(corrupted)
        assert ok is False
        assert len(errors) > 0

    def test_verify_missing_file(self, tmp_path):
        ok, errors = verify_audit_bundle(tmp_path / "nonexistent.zip")
        assert ok is False

    def test_export_empty_journal(self, journal_dir):
        output = journal_dir / "empty_audit.zip"
        path = export_campaign_audit("camp_empty", journal_dir, output)

        with zipfile.ZipFile(path) as zf:
            journal_data = json.loads(zf.read("journal.json"))
            assert journal_data == []

    def test_export_with_extra_data(self, journal_dir, populated_journal):
        output = journal_dir / "extra_audit.zip"
        path = export_campaign_audit(
            "camp_audit", journal_dir, output,
            extra_data={"custom_metrics": {"accuracy": 0.95}},
        )

        with zipfile.ZipFile(path) as zf:
            assert "extra/custom_metrics.json" in zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))
            assert "custom_metrics" in manifest["extra_sections"]
