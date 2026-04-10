"""Tests for plan-file parsing and watcher ingestion."""

from __future__ import annotations

import os

import pytest

from oas_core.plan_file import PlanFile
from oas_core.plan_watcher import PlanWatcher
from oas_core.schemas.campaign import CampaignSchema, CampaignStatus


SAMPLE_PLAN = """---
id: 2026-04-05-graphene-dft-sweep
title: Graphene DFT parameter sweep
author: claude-sonnet-4-6
intent: research
mode: hybrid
budget_usd: 5.0
tier: local_only
approvals_required: true
readiness_threshold: 0.7
research_backends: [deerflow, labclaw, internagent]
synthesis: uniscientist
allow_kairos_followup: true
deadline: 2026-04-05T18:00:00Z
priority: high
tags: [dft, materials, phase-24-demo]
---

# Objective
Run a compact graphene DFT planning workflow with clear constraints.

# Steps
1. **Literature sweep** -- focus on graphene bilayer DFT from the last 24 months.
2. **Parameter extraction** -- pull lattice constants, k-point grids, and XC functionals.
3. **Simulation plan** -- design DOE covering 3 parameters x 4 levels.
4. **Synthesis** -- produce a polymathic report via UniScientist.

# Constraints
- No >$2 cloud calls without approval.
- Must cite at least 15 peer-reviewed sources.

# Success criteria
- Readiness score >= 0.75 on knowledge + experiment dimensions.
- Report accepted by evaluator (quality >= 0.8).
"""


class TestPlanFile:
    def test_from_markdown_parses_frontmatter_and_sections(self):
        plan = PlanFile.from_markdown(SAMPLE_PLAN)

        assert plan.id == "2026-04-05-graphene-dft-sweep"
        assert plan.intent == "research"
        assert plan.mode == "hybrid"
        assert plan.research_backends == ["deerflow", "labclaw", "internagent"]
        assert plan.objective.startswith("Run a compact graphene DFT")
        assert len(plan.steps) == 4
        assert plan.constraints[0].startswith("No >$2 cloud calls")
        assert plan.success_criteria[1].startswith("Report accepted")
        assert len(plan.source_sha256) == 64

    def test_to_campaign_infers_commands_and_metadata(self):
        plan = PlanFile.from_markdown(SAMPLE_PLAN)
        campaign = plan.to_campaign()

        assert campaign.campaign_id == plan.id
        assert campaign.request_id == plan.id
        assert campaign.status == CampaignStatus.PENDING_APPROVAL
        assert [step.command for step in campaign.steps] == [
            "literature",
            "research",
            "doe",
            "synthesize",
        ]
        assert [step.depends_on for step in campaign.steps] == [[], [1], [2], [3]]
        assert campaign.metadata["readiness_threshold"] == 0.7
        assert campaign.metadata["budget_usd"] == 5.0
        assert campaign.metadata["plan_file"]["id"] == plan.id
        assert campaign.steps[0].metadata["command_source"] == "heuristic"

    def test_campaign_schema_from_plan_file(self, tmp_path):
        plan_path = tmp_path / "2026-04-05T0930_graphene-dft-sweep.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")

        campaign = CampaignSchema.from_plan_file(plan_path)

        assert campaign.title == "Graphene DFT parameter sweep"
        assert campaign.metadata["plan_file"]["source_path"] == str(plan_path.resolve())
        assert campaign.steps[-1].command == "synthesize"

    def test_explicit_command_step_is_respected(self):
        text = SAMPLE_PLAN.replace(
            "2. **Parameter extraction** -- pull lattice constants, k-point grids, and XC functionals.",
            "2. /deepresearch parameter extraction for graphene bilayer DFT",
        )
        plan = PlanFile.from_markdown(text)
        campaign = plan.to_campaign()
        assert campaign.steps[1].command == "deepresearch"
        assert campaign.steps[1].metadata["command_source"] == "explicit"

    def test_missing_steps_section_raises(self):
        broken = SAMPLE_PLAN.replace("# Steps\n1. **Literature sweep** -- focus on graphene bilayer DFT from the last 24 months.\n2. **Parameter extraction** -- pull lattice constants, k-point grids, and XC functionals.\n3. **Simulation plan** -- design DOE covering 3 parameters x 4 levels.\n4. **Synthesis** -- produce a polymathic report via UniScientist.\n\n", "")
        with pytest.raises(ValueError, match="Steps section"):
            PlanFile.from_markdown(broken)

    def test_to_campaign_steps_produces_correct_format(self):
        plan = PlanFile.from_markdown(SAMPLE_PLAN)
        steps = plan.to_campaign_steps()

        assert len(steps) == 4
        assert all(isinstance(s, dict) for s in steps)
        assert steps[0]["step"] == 1
        assert steps[0]["depends_on"] == []
        assert steps[1]["depends_on"] == [1]
        assert "command" in steps[0]
        assert "args" in steps[0]

    def test_from_file_reads_from_disk(self, tmp_path):
        plan_path = tmp_path / "2026-04-05T1000_test-plan.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")

        plan = PlanFile.from_file(plan_path)

        assert plan.id == "2026-04-05-graphene-dft-sweep"
        assert plan.source_path == str(plan_path.resolve())

    def test_research_intent_maps_to_research_commands(self):
        """Research intent plans should use research-family commands."""
        plan = PlanFile.from_markdown(SAMPLE_PLAN)
        steps = plan.to_campaign_steps()
        commands = [s["command"] for s in steps]
        # First step should be literature (inferred from step text)
        assert commands[0] == "literature"

    def test_simulate_intent_maps_to_simulate_commands(self):
        """Simulate intent should use simulate as fallback command."""
        sim_plan = SAMPLE_PLAN.replace("intent: research", "intent: simulate")
        sim_plan = sim_plan.replace(
            "1. **Literature sweep** -- focus on graphene bilayer DFT from the last 24 months.",
            "1. **Parameter setup** -- define grid parameters for the simulation.",
        )
        plan = PlanFile.from_markdown(sim_plan)
        steps = plan.to_campaign_steps()
        # First step with no clear keyword match should fallback to intent
        assert steps[0]["command"] == "simulate"

    def test_invalid_yaml_raises_error(self):
        broken = "---\n[invalid yaml\n---\n# Objective\ntest\n# Steps\n1. do thing\n"
        with pytest.raises(Exception):
            PlanFile.from_markdown(broken)

    def test_minimal_plan_only_required_fields(self):
        minimal = """---
id: minimal-plan
title: Minimal plan
author: test
intent: research
---

# Objective
A simple test objective.

# Steps
1. Do the first thing.
"""
        plan = PlanFile.from_markdown(minimal)
        assert plan.id == "minimal-plan"
        assert plan.mode == "sequential"
        assert plan.budget_usd == 0.0
        assert plan.tier == "default"
        assert len(plan.steps) == 1

    def test_missing_required_fields_raises_validation_error(self):
        no_id = """---
title: No ID plan
author: test
intent: research
---

# Objective
Test.

# Steps
1. Do something.
"""
        with pytest.raises(Exception):
            PlanFile.from_markdown(no_id)


class TestPlanWatcher:
    def test_scan_waits_until_file_is_stable(self, tmp_path):
        plan_path = tmp_path / "2026-04-05T0930_graphene-dft-sweep.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")
        watcher = PlanWatcher(tmp_path, stable_seconds=0.5)

        assert watcher.scan(now_monotonic=0.0) == []
        assert watcher.scan(now_monotonic=0.4) == []
        assert watcher.scan(now_monotonic=0.6) == [plan_path.resolve()]
        assert watcher.scan(now_monotonic=1.0) == []

    def test_scan_requeues_file_after_change(self, tmp_path):
        plan_path = tmp_path / "2026-04-05T0930_graphene-dft-sweep.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")
        watcher = PlanWatcher(tmp_path, stable_seconds=0.5)

        watcher.scan(now_monotonic=0.0)
        watcher.scan(now_monotonic=0.6)

        plan_path.write_text(SAMPLE_PLAN + "\n", encoding="utf-8")
        stat = plan_path.stat()
        os.utime(plan_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

        assert watcher.scan(now_monotonic=0.7) == []
        assert watcher.scan(now_monotonic=1.3) == [plan_path.resolve()]

    def test_load_ready_campaigns(self, tmp_path):
        plan_path = tmp_path / "2026-04-05T0930_graphene-dft-sweep.md"
        plan_path.write_text(SAMPLE_PLAN, encoding="utf-8")
        watcher = PlanWatcher(tmp_path, stable_seconds=0.5)

        watcher.scan(now_monotonic=0.0)
        campaigns = watcher.load_ready_campaigns(now_monotonic=0.6)

        assert len(campaigns) == 1
        assert campaigns[0].campaign_id == "2026-04-05-graphene-dft-sweep"

    def test_ignores_temp_files(self, tmp_path):
        temp_path = tmp_path / "draft-plan.md.tmp"
        temp_path.write_text(SAMPLE_PLAN, encoding="utf-8")
        watcher = PlanWatcher(tmp_path, stable_seconds=0.1)

        assert watcher.scan(now_monotonic=1.0) == []
