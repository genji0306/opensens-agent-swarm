"""Tests for oas_core.middleware.audit — AuditMiddleware."""
import json
from pathlib import Path

import pytest

from oas_core.middleware.audit import (
    AuditMiddleware,
    AuditEntry,
    _hash_payload,
)
from oas_core.middleware.summarization import SummarizationMiddleware


class TestHashPayload:
    def test_deterministic(self):
        payload = {"a": 1, "b": "hello"}
        h1 = _hash_payload(payload)
        h2 = _hash_payload(payload)
        assert h1 == h2

    def test_key_order_independent(self):
        h1 = _hash_payload({"a": 1, "b": 2})
        h2 = _hash_payload({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_payloads_differ(self):
        h1 = _hash_payload({"a": 1})
        h2 = _hash_payload({"a": 2})
        assert h1 != h2


class TestAuditEntry:
    def test_to_dict(self):
        entry = AuditEntry(
            event="task_started",
            task_id="t_1",
            agent_name="academic",
            payload_hash="abc123",
            signature="sig456",
        )
        d = entry.to_dict()
        assert d["event"] == "task_started"
        assert d["task_id"] == "t_1"
        assert d["payload_hash"] == "abc123"
        assert d["signature"] == "sig456"
        assert "timestamp" in d

    def test_to_dict_no_signature(self):
        entry = AuditEntry(
            event="task_started",
            task_id="t_1",
            agent_name="academic",
            payload_hash="abc123",
        )
        d = entry.to_dict()
        assert "signature" not in d

    def test_to_dict_with_extra(self):
        entry = AuditEntry(
            event="task_completed",
            task_id="t_1",
            agent_name="academic",
            payload_hash="abc123",
            status="ok",
            artifact_count=3,
        )
        d = entry.to_dict()
        assert d["status"] == "ok"
        assert d["artifact_count"] == 3


class TestAuditMiddleware:
    def test_log_task_start(self, tmp_path):
        audit = AuditMiddleware(log_dir=tmp_path)
        entry = audit.log_task_start("t_1", "academic", {"query": "test"})

        assert entry.event == "task_started"
        assert entry.task_id == "t_1"
        assert entry.payload_hash == _hash_payload({"query": "test"})

        log_file = tmp_path / "audit.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event"] == "task_started"

    def test_log_task_end(self, tmp_path):
        audit = AuditMiddleware(log_dir=tmp_path)
        entry = audit.log_task_end(
            "t_1", "academic", {"result": "ok"},
            status="ok", artifact_count=2,
        )

        assert entry.event == "task_completed"
        assert entry.extra["status"] == "ok"
        assert entry.extra["artifact_count"] == 2

    def test_multiple_entries_appended(self, tmp_path):
        audit = AuditMiddleware(log_dir=tmp_path)
        audit.log_task_start("t_1", "a", {"x": 1})
        audit.log_task_end("t_1", "a", {"y": 2})

        log_file = tmp_path / "audit.jsonl"
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_call_wraps_handler(self, tmp_path):
        audit = AuditMiddleware(log_dir=tmp_path)

        async def handler(payload):
            return {"result": "done", "artifacts": [1, 2]}

        result = await audit("t_1", "academic", {"q": "test"}, handler)
        assert result["result"] == "done"

        log_file = tmp_path / "audit.jsonl"
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2  # start + end

        end_data = json.loads(lines[1])
        assert end_data["status"] == "ok"
        assert end_data["artifact_count"] == 2

    @pytest.mark.asyncio
    async def test_call_logs_error(self, tmp_path):
        audit = AuditMiddleware(log_dir=tmp_path)

        async def handler(payload):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await audit("t_1", "academic", {"q": "test"}, handler)

        log_file = tmp_path / "audit.jsonl"
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2

        end_data = json.loads(lines[1])
        assert end_data["status"] == "error"

    def test_creates_log_dir(self, tmp_path):
        log_dir = tmp_path / "nested" / "audit"
        audit = AuditMiddleware(log_dir=log_dir)
        audit.log_task_start("t_1", "a", {})
        assert log_dir.exists()


class TestSummarizationMiddleware:
    def test_needs_compression_under_limit(self):
        mw = SummarizationMiddleware(max_tokens=1000)
        messages = [{"content": "Hello world"}]
        assert not mw.needs_compression(messages)

    def test_needs_compression_over_limit(self):
        mw = SummarizationMiddleware(max_tokens=10)
        messages = [{"content": "A" * 200}]
        assert mw.needs_compression(messages)

    def test_compress_keeps_recent(self):
        mw = SummarizationMiddleware(max_tokens=100, keep_recent=2)
        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(10)
        ]
        result = mw.compress(messages, "Summary of old messages")

        assert len(result) == 3  # 1 summary + 2 recent
        assert result[0]["role"] == "system"
        assert "Summary of old messages" in result[0]["content"]
        assert result[1]["content"] == "Message 8"
        assert result[2]["content"] == "Message 9"

    def test_compress_few_messages_unchanged(self):
        mw = SummarizationMiddleware(max_tokens=100, keep_recent=5)
        messages = [{"role": "user", "content": "short"}]
        result = mw.compress(messages, "Summary")
        assert result == messages  # unchanged
