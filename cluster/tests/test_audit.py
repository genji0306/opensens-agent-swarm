"""Tests for shared.audit — append-only JSONL audit logger."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from shared.audit import log_task, log_result, log_event, _write_entry, _audit_path
from shared.models import Task, TaskType, TaskResult


@pytest.fixture(autouse=True)
def audit_dir(tmp_path, monkeypatch):
    """Redirect audit log to a temp directory."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    mock_settings = MagicMock()
    mock_settings.logs_dir = logs_dir
    monkeypatch.setattr("shared.audit.settings", mock_settings)
    return logs_dir


class TestWriteEntry:
    def test_creates_file_on_first_write(self, audit_dir):
        _write_entry({"event": "test"})
        path = audit_dir / "audit.jsonl"
        assert path.exists()

    def test_appends_valid_jsonl(self, audit_dir):
        _write_entry({"event": "first"})
        _write_entry({"event": "second"})
        lines = (audit_dir / "audit.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "first"
        assert json.loads(lines[1])["event"] == "second"

    def test_each_line_is_valid_json(self, audit_dir):
        for i in range(5):
            _write_entry({"event": f"e{i}", "count": i})
        lines = (audit_dir / "audit.jsonl").read_text().strip().split("\n")
        for line in lines:
            parsed = json.loads(line)
            assert "event" in parsed


class TestLogTask:
    def test_logs_task_created_event(self, audit_dir):
        task = Task(
            task_id="t1",
            task_type=TaskType.RESEARCH,
            user_id=42,
            payload={"topic": "quantum"},
        )
        log_task(task)
        lines = (audit_dir / "audit.jsonl").read_text().strip().split("\n")
        entry = json.loads(lines[0])
        assert entry["event"] == "task_created"
        assert entry["task_id"] == "t1"
        assert entry["task_type"] == "research"
        assert entry["user_id"] == 42
        assert "payload_hash" in entry
        assert "timestamp" in entry


class TestLogResult:
    def test_logs_task_completed_event(self, audit_dir):
        result = TaskResult(
            task_id="t1",
            agent_name="ResearchAgent",
            status="ok",
            result={"findings": "none"},
            artifacts=["report.pdf"],
        )
        log_result(result)
        lines = (audit_dir / "audit.jsonl").read_text().strip().split("\n")
        entry = json.loads(lines[0])
        assert entry["event"] == "task_completed"
        assert entry["task_id"] == "t1"
        assert entry["agent_name"] == "ResearchAgent"
        assert entry["status"] == "ok"
        assert entry["artifact_count"] == 1


class TestLogEvent:
    def test_logs_arbitrary_event(self, audit_dir):
        log_event("server_start", host="0.0.0.0", port=8100)
        lines = (audit_dir / "audit.jsonl").read_text().strip().split("\n")
        entry = json.loads(lines[0])
        assert entry["event"] == "server_start"
        assert entry["host"] == "0.0.0.0"
        assert entry["port"] == 8100
        assert "timestamp" in entry
