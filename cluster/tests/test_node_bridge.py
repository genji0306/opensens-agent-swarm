"""Tests for the OpenClaw node-host bridge (shared/node_bridge.py)."""
import json
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from shared.models import Task, TaskResult, TaskType
from shared.node_bridge import run_agent


def _sync_handler(task: Task) -> TaskResult:
    return TaskResult(
        task_id=task.task_id,
        agent_name="TestAgent",
        status="ok",
        result={"echo": task.payload.get("text", "")},
    )


async def _async_handler(task: Task) -> TaskResult:
    return TaskResult(
        task_id=task.task_id,
        agent_name="AsyncTestAgent",
        status="ok",
        result={"echo": task.payload.get("text", "")},
    )


def _failing_handler(task: Task) -> TaskResult:
    raise ValueError("Something went wrong")


class TestRunAgentFromArgv:
    def test_sync_handler_with_argv(self, capsys):
        task_json = json.dumps({
            "task_type": "research",
            "payload": {"text": "hello"},
        })
        with patch.object(sys, "argv", ["agent", task_json]), \
             patch("shared.node_bridge.log_task"), \
             patch("shared.node_bridge.log_result"):
            run_agent(_sync_handler, agent_name="TestAgent")

        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "ok"
        assert output["result"]["echo"] == "hello"

    def test_async_handler_with_argv(self, capsys):
        task_json = json.dumps({
            "task_type": "simulate",
            "payload": {"text": "async test"},
        })
        with patch.object(sys, "argv", ["agent", task_json]), \
             patch("shared.node_bridge.log_task"), \
             patch("shared.node_bridge.log_result"):
            run_agent(_async_handler, agent_name="AsyncTestAgent")

        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "ok"
        assert output["result"]["echo"] == "async test"
        assert output["agent_name"] == "AsyncTestAgent"


class TestRunAgentFromStdin:
    def test_reads_from_stdin(self, capsys):
        task_json = json.dumps({
            "task_type": "analyze",
            "payload": {"data": "test.csv"},
        })
        with patch.object(sys, "argv", ["agent"]), \
             patch("sys.stdin", StringIO(task_json)), \
             patch("shared.node_bridge.log_task"), \
             patch("shared.node_bridge.log_result"):
            run_agent(_sync_handler, agent_name="TestAgent")

        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "ok"


class TestRunAgentErrors:
    def test_invalid_json(self, capsys):
        with patch.object(sys, "argv", ["agent", "not valid json"]), \
             patch("shared.node_bridge.log_task"), \
             patch("shared.node_bridge.log_result"):
            run_agent(_sync_handler, agent_name="TestAgent")

        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "json_parse_error"
        assert "Invalid JSON" in output["result"]["error"]

    def test_empty_input(self, capsys):
        with patch.object(sys, "argv", ["agent"]), \
             patch("sys.stdin", StringIO("")), \
             patch("shared.node_bridge.log_task"), \
             patch("shared.node_bridge.log_result"):
            run_agent(_sync_handler, agent_name="TestAgent")

        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "empty_input"

    def test_handler_exception(self, capsys):
        task_json = json.dumps({"task_type": "research", "payload": {}})
        with patch.object(sys, "argv", ["agent", task_json]), \
             patch("shared.node_bridge.log_task"), \
             patch("shared.node_bridge.log_result"):
            run_agent(_failing_handler, agent_name="FailAgent")

        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "agent_error"
        assert "ValueError" in output["result"]["error"]
