"""Tests for shared data models."""
import json
from datetime import datetime, timezone

from shared.models import Task, TaskResult, TaskType, AgentInfo


class TestTaskType:
    def test_all_types_exist(self):
        expected = {
            "research", "literature", "doe", "paper", "perplexity",
            "simulate", "analyze", "synthetic", "report_data", "autoresearch",
            "deerflow",
            "plan", "synthesize", "media_gen", "notebooklm",
            "debate", "rl_train",
            "deep_research", "parameter_golf", "swarm_research",
            "turboq_status",
            "results", "schedule", "full_swarm", "turbo_swarm",
            "paper_review",
            "dft",
            "ane_research",
            "gemma_swarm",
            "unipat_swarm",
            "orchestrate",
            "kairos",
            "wiki_compile",
            "wiki_lint",
            "eval_run",
            "eval_report",
            "status",
        }
        actual = {t.value for t in TaskType}
        assert actual == expected

    def test_string_enum(self):
        assert TaskType.RESEARCH == "research"
        assert str(TaskType.SIMULATE) == "TaskType.SIMULATE"


class TestTask:
    def test_defaults(self):
        t = Task(task_type=TaskType.RESEARCH)
        assert t.task_type == TaskType.RESEARCH
        assert len(t.task_id) == 12
        assert t.user_id == 0
        assert t.payload == {}
        assert t.signature is None
        assert t.parent_task_id is None
        assert isinstance(t.created_at, datetime)

    def test_custom_fields(self):
        t = Task(
            task_id="abc123",
            task_type=TaskType.ANALYZE,
            user_id=42,
            payload={"data": "test.csv"},
            parent_task_id="parent_001",
        )
        assert t.task_id == "abc123"
        assert t.user_id == 42
        assert t.payload["data"] == "test.csv"
        assert t.parent_task_id == "parent_001"

    def test_json_roundtrip(self):
        t = Task(task_type=TaskType.SIMULATE, payload={"x": 1.5})
        data = json.loads(t.model_dump_json())
        t2 = Task(**data)
        assert t2.task_type == t.task_type
        assert t2.payload == t.payload
        assert t2.task_id == t.task_id


class TestTaskResult:
    def test_minimal(self):
        r = TaskResult(
            task_id="t001",
            agent_name="TestAgent",
            status="ok",
        )
        assert r.task_id == "t001"
        assert r.result == {}
        assert r.artifacts == []
        assert r.payload_hash is None

    def test_with_artifacts(self):
        r = TaskResult(
            task_id="t002",
            agent_name="SimAgent",
            status="ok",
            result={"mean": 3.14},
            artifacts=["/tmp/out.json"],
            payload_hash="abc123",
        )
        assert len(r.artifacts) == 1
        assert r.result["mean"] == 3.14

    def test_json_roundtrip(self):
        r = TaskResult(
            task_id="t003",
            agent_name="TestAgent",
            status="error",
            result={"error": "something broke"},
        )
        data = json.loads(r.model_dump_json())
        r2 = TaskResult(**data)
        assert r2.status == "error"
        assert r2.result["error"] == "something broke"


class TestAgentInfo:
    def test_creation(self):
        info = AgentInfo(
            name="AcademicAgent",
            description="Research agent",
            device="academic",
            task_types=[TaskType.RESEARCH, TaskType.LITERATURE],
            ai_services=["anthropic", "perplexity"],
        )
        assert info.device == "academic"
        assert len(info.task_types) == 2
        assert "anthropic" in info.ai_services
