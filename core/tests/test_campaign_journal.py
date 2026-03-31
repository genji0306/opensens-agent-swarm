"""Tests for the campaign journal."""

import json
import pytest
from pathlib import Path

from oas_core.campaign_journal import (
    CampaignJournal,
    JournalEntry,
    JournalReader,
)


@pytest.fixture
def journal_dir(tmp_path):
    return tmp_path / "journals"


class TestCampaignJournal:
    def test_record_and_read(self, journal_dir):
        journal = CampaignJournal(journal_dir, "camp_1")
        journal.record("campaign.started", "leader", {"objective": "test"})
        journal.record("step.completed", "academic", {"step": 1, "score": 0.85})

        entries = journal.entries()
        assert len(entries) == 2
        assert entries[0].event_type == "campaign.started"
        assert entries[1].event_type == "step.completed"

    def test_hash_chain_integrity(self, journal_dir):
        journal = CampaignJournal(journal_dir, "camp_2")
        journal.record("campaign.started", "leader", {})
        journal.record("step.started", "academic", {"step": 1})
        journal.record("step.completed", "academic", {"step": 1})

        ok, errors = journal.verify()
        assert ok is True
        assert errors == []

    def test_hash_chain_detects_tampering(self, journal_dir):
        journal = CampaignJournal(journal_dir, "camp_3")
        journal.record("campaign.started", "leader", {})
        journal.record("step.completed", "academic", {"step": 1})

        # Tamper with the file
        lines = journal.path.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        entry["payload"]["tampered"] = True
        lines[0] = json.dumps(entry)
        journal.path.write_text("\n".join(lines) + "\n")

        ok, errors = journal.verify()
        assert ok is False
        assert len(errors) > 0

    def test_prev_hash_links(self, journal_dir):
        journal = CampaignJournal(journal_dir, "camp_4")
        e1 = journal.record("a", "leader", {})
        e2 = journal.record("b", "leader", {})

        assert e2.prev_hash == e1.hash

    def test_empty_journal_verify(self, journal_dir):
        journal = CampaignJournal(journal_dir, "camp_empty")
        ok, errors = journal.verify()
        assert ok is True

    def test_entry_count(self, journal_dir):
        journal = CampaignJournal(journal_dir, "camp_5")
        assert journal.entry_count == 0
        journal.record("a", "x", {})
        journal.record("b", "y", {})
        assert journal.entry_count == 2

    def test_journal_entry_to_dict_roundtrip(self):
        entry = JournalEntry("camp_1", "test", "actor", {"key": "val"})
        d = entry.to_dict()
        restored = JournalEntry.from_dict(d)
        assert restored.campaign_id == entry.campaign_id
        assert restored.event_type == entry.event_type
        assert restored.hash == entry.hash

    def test_resume_journal(self, journal_dir):
        """Verify that creating a new CampaignJournal picks up the last hash."""
        j1 = CampaignJournal(journal_dir, "camp_resume")
        e1 = j1.record("start", "leader", {})

        j2 = CampaignJournal(journal_dir, "camp_resume")
        e2 = j2.record("continue", "leader", {})
        assert e2.prev_hash == e1.hash

        ok, errors = j2.verify()
        assert ok is True


class TestJournalReader:
    def test_list_campaigns(self, journal_dir):
        CampaignJournal(journal_dir, "alpha").record("a", "x", {})
        CampaignJournal(journal_dir, "beta").record("b", "y", {})

        reader = JournalReader(journal_dir)
        campaigns = reader.list_campaigns()
        assert "alpha" in campaigns
        assert "beta" in campaigns

    def test_query_by_type(self, journal_dir):
        journal = CampaignJournal(journal_dir, "qtype")
        journal.record("step.started", "academic", {})
        journal.record("step.completed", "academic", {})
        journal.record("cost.recorded", "leader", {})

        reader = JournalReader(journal_dir)
        results = reader.query_by_type("qtype", "cost.recorded")
        assert len(results) == 1

    def test_list_empty_dir(self, tmp_path):
        reader = JournalReader(tmp_path / "nonexistent")
        assert reader.list_campaigns() == []
