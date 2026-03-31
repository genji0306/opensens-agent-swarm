"""Tests for the campaign template library."""

import pytest
from pathlib import Path

from oas_core.campaign_templates import (
    CampaignTemplate,
    TemplateRegistry,
    TemplateStep,
    YAML_AVAILABLE,
)


def _make_template(name="test-template"):
    return CampaignTemplate(
        name=name,
        description="A test template",
        category="research",
        tags=["test"],
        steps=[
            TemplateStep(step=1, command="research", args_template="{objective}"),
            TemplateStep(step=2, command="synthesize", args_template="synthesize {objective}", depends_on=[1]),
        ],
    )


class TestCampaignTemplate:
    def test_instantiate_basic(self):
        template = _make_template()
        campaign = template.instantiate("quantum dots")

        assert campaign.objective == "quantum dots"
        assert len(campaign.steps) == 2
        assert campaign.steps[0].command == "research"
        assert campaign.steps[0].args == "quantum dots"
        assert campaign.steps[1].args == "synthesize quantum dots"

    def test_instantiate_with_overrides(self):
        template = _make_template()
        campaign = template.instantiate("EIT", overrides={
            "title": "Custom Title",
            "step_2": {"args": "custom args"},
        })

        assert campaign.title == "Custom Title"
        assert campaign.steps[1].args == "custom args"

    def test_template_metadata(self):
        template = _make_template()
        campaign = template.instantiate("test")
        assert campaign.metadata["template"] == "test-template"
        assert campaign.metadata["category"] == "research"

    def test_dependencies_preserved(self):
        template = _make_template()
        campaign = template.instantiate("test")
        assert campaign.steps[1].depends_on == [1]


class TestTemplateRegistry:
    def test_register_and_get(self):
        registry = TemplateRegistry()
        template = _make_template()
        registry.register(template)

        assert registry.get("test-template") is not None
        assert registry.count == 1

    def test_list_templates(self):
        registry = TemplateRegistry()
        registry.register(_make_template("a"))
        registry.register(_make_template("b"))

        templates = registry.list()
        assert len(templates) == 2

    def test_list_by_category(self):
        registry = TemplateRegistry()
        t1 = _make_template("a")
        t1.category = "research"
        t2 = _make_template("b")
        t2.category = "simulation"
        registry.register(t1)
        registry.register(t2)

        assert len(registry.list_by_category("research")) == 1
        assert len(registry.list_by_category("simulation")) == 1

    def test_instantiate_by_name(self):
        registry = TemplateRegistry()
        registry.register(_make_template())

        campaign = registry.instantiate("test-template", "quantum sensors")
        assert campaign.objective == "quantum sensors"

    def test_instantiate_missing_raises(self):
        registry = TemplateRegistry()
        with pytest.raises(KeyError):
            registry.instantiate("nonexistent", "test")

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
    def test_load_from_dir(self, tmp_path):
        # Create a YAML template
        yaml_content = """
name: yaml-test
description: Test template from YAML
category: test
steps:
  - step: 1
    command: research
    args_template: "{objective}"
"""
        (tmp_path / "test.yaml").write_text(yaml_content)

        registry = TemplateRegistry()
        count = registry.load_from_dir(tmp_path)
        assert count == 1
        assert registry.get("yaml-test") is not None

    def test_load_from_nonexistent_dir(self, tmp_path):
        registry = TemplateRegistry()
        count = registry.load_from_dir(tmp_path / "missing")
        assert count == 0

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
    def test_load_real_templates(self):
        """Load the actual built-in templates from cluster/templates/."""
        templates_dir = Path(__file__).parent.parent.parent / "cluster" / "templates"
        if not templates_dir.exists():
            pytest.skip("cluster/templates not found")

        registry = TemplateRegistry()
        count = registry.load_from_dir(templates_dir)
        assert count >= 3  # literature-review, hypothesis-test, full-pipeline, simulation-validate
