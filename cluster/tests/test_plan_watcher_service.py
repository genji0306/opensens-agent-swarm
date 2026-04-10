"""Tests for the automatic plan watcher service."""

from __future__ import annotations

import pytest

from leader.plan_watcher_service import PlanWatcherService
from oas_core.plan_watcher import PlanWatcher
from shared.models import TaskResult


SAMPLE_PLAN = """---
id: 2026-04-05-polymer-watch
title: Polymer watch plan
author: claude-sonnet-4-6
intent: research
mode: hybrid
budget_usd: 2.0
tier: local_only
approvals_required: false
---

# Objective
Watch the plan directory and launch a simple campaign.

# Steps
1. Literature sweep -- collect a few recent degradation mechanisms.
2. Synthesis -- summarize the top risks.
"""


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.calls = []

    async def handle_task(self, task):
        self.calls.append(task)
        return TaskResult(
            task_id=task.task_id,
            agent_name="OrchestratorAgent",
            status="ok",
            result={"action": "campaign_executed"},
        )


def _service(tmp_path, orchestrator, *, enabled: bool = False) -> PlanWatcherService:
    return PlanWatcherService(
        plan_dir=tmp_path,
        data_dir=tmp_path / "data",
        enabled=enabled,
        interval_seconds=0.01,
        watcher=PlanWatcher(tmp_path, stable_seconds=0.0),
        orchestrator_factory=lambda: orchestrator,
        task_id_factory=lambda: "task-fixed",
    )


class TestPlanWatcherService:
    @pytest.mark.asyncio
    async def test_scan_once_processes_plan_and_writes_receipt(self, tmp_path):
        orchestrator = _FakeOrchestrator()
        service = _service(tmp_path, orchestrator)
        plan_path = tmp_path / "2026-04-05T0900_polymer-watch.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")

        first_scan = await service.scan_once()
        second_scan = await service.scan_once()

        assert first_scan["processed_count"] == 0
        assert second_scan["processed_count"] == 1
        assert second_scan["processed"][0]["plan_id"] == "2026-04-05-polymer-watch"
        assert len(orchestrator.calls) == 1
        assert service.status()["receipt_count"] == 1

    @pytest.mark.asyncio
    async def test_duplicate_plan_is_skipped_after_receipt_exists(self, tmp_path):
        orchestrator_a = _FakeOrchestrator()
        service_a = _service(tmp_path, orchestrator_a)
        plan_path = tmp_path / "2026-04-05T0915_polymer-watch.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")

        await service_a.scan_once()
        await service_a.scan_once()

        orchestrator_b = _FakeOrchestrator()
        service_b = _service(tmp_path, orchestrator_b)

        first_scan = await service_b.scan_once()
        second_scan = await service_b.scan_once()

        assert first_scan["skipped_count"] == 0
        assert second_scan["processed_count"] == 0
        assert second_scan["skipped_count"] == 1
        assert second_scan["skipped"][0]["reason"] == "already_processed"
        assert len(orchestrator_b.calls) == 0

    @pytest.mark.asyncio
    async def test_invalid_plan_records_error_receipt(self, tmp_path):
        orchestrator = _FakeOrchestrator()
        service = _service(tmp_path, orchestrator)
        plan_path = tmp_path / "2026-04-05T0930_invalid-plan.md"
        plan_path.write_text("not a valid plan file", encoding="utf-8")

        first_scan = await service.scan_once()
        second_scan = await service.scan_once()

        assert first_scan["error_count"] == 0
        assert second_scan["error_count"] == 1
        assert second_scan["errors"][0]["path"] == str(plan_path)
        assert service.status()["receipt_count"] == 1

    @pytest.mark.asyncio
    async def test_start_and_stop_manage_background_loop(self, tmp_path):
        orchestrator = _FakeOrchestrator()
        service = _service(tmp_path, orchestrator, enabled=True)

        await service.start()
        assert service.running is True

        await service.stop()
        assert service.running is False

    @pytest.mark.asyncio
    async def test_callback_receives_parsed_plan(self, tmp_path):
        orchestrator = _FakeOrchestrator()
        service = _service(tmp_path, orchestrator)
        plan_path = tmp_path / "2026-04-05T0945_callback-test.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")

        # Two scans: first observes, second processes
        await service.scan_once()
        result = await service.scan_once()

        assert result["processed_count"] == 1
        assert len(orchestrator.calls) == 1
        # The task passed to orchestrator should have the plan path
        task = orchestrator.calls[0]
        assert task.payload["plan_path"] == str(plan_path)
        assert task.payload["source"] == "plan_file"

    @pytest.mark.asyncio
    async def test_service_status_reports_mode_and_dir(self, tmp_path):
        orchestrator = _FakeOrchestrator()
        service = _service(tmp_path, orchestrator)

        status = service.status()
        assert status["mode"] == "filesystem"
        assert status["plan_dir"] == str(tmp_path.resolve())
        assert status["running"] is False
        assert status["receipt_count"] == 0
