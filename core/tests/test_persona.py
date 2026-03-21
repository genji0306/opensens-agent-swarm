"""Tests for oas_core.persona — persona loader."""
from pathlib import Path
from textwrap import dedent

import pytest

from oas_core.persona import (
    PersonaMeta,
    ROLE_PERSONA_MAP,
    load_persona,
    parse_persona_file,
    _parse_frontmatter,
)


class TestParseFrontmatter:
    def test_basic_frontmatter(self):
        text = dedent("""\
            ---
            name: AI Engineer
            description: Expert AI/ML engineer
            color: blue
            emoji: "🤖"
            vibe: Turns models into features
            ---

            # AI Engineer Agent

            You are an expert.
        """)
        fm, body = _parse_frontmatter(text)
        assert fm["name"] == "AI Engineer"
        assert fm["description"] == "Expert AI/ML engineer"
        assert fm["color"] == "blue"
        assert "AI Engineer Agent" in body

    def test_no_frontmatter(self):
        text = "# Just a heading\n\nSome content."
        fm, body = _parse_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_incomplete_frontmatter(self):
        text = "---\nname: Test\nNo closing delimiter"
        fm, body = _parse_frontmatter(text)
        assert fm == {}


class TestParsePersonaFile:
    def test_parse_with_frontmatter(self, tmp_path):
        persona_file = tmp_path / "test-persona.md"
        persona_file.write_text(dedent("""\
            ---
            name: Test Agent
            description: A test persona
            color: green
            emoji: "🧪"
            vibe: Testing all the things
            ---

            # Test Agent

            ## Core Mission
            Test everything.
        """))

        meta, body = parse_persona_file(persona_file)
        assert meta.name == "Test Agent"
        assert meta.description == "A test persona"
        assert meta.color == "green"
        assert meta.emoji == "🧪"
        assert meta.vibe == "Testing all the things"
        assert "Core Mission" in body

    def test_parse_without_frontmatter(self, tmp_path):
        persona_file = tmp_path / "no-fm.md"
        persona_file.write_text("# Just a heading\n\nContent.")

        meta, body = parse_persona_file(persona_file)
        assert meta.name == "no-fm"  # falls back to stem
        assert "Just a heading" in body

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_persona_file(Path("/nonexistent/persona.md"))


class TestLoadPersona:
    def test_load_known_agent(self, tmp_path):
        # Create a minimal persona file
        eng_dir = tmp_path / "engineering"
        eng_dir.mkdir()
        (eng_dir / "engineering-ai-engineer.md").write_text(dedent("""\
            ---
            name: AI Engineer
            description: Expert AI/ML engineer
            ---

            # AI Engineer

            You are an expert AI engineer.
        """))

        body = load_persona("academic.research", personas_dir=tmp_path)
        assert "AI Engineer" in body
        assert "expert AI engineer" in body

    def test_load_unknown_agent(self, tmp_path):
        body = load_persona("nonexistent.agent", personas_dir=tmp_path)
        assert body == ""

    def test_load_missing_file(self, tmp_path):
        # Map exists but file doesn't
        body = load_persona("academic.research", personas_dir=tmp_path)
        assert body == ""

    def test_load_from_real_framework(self):
        """Test loading from the actual agency-agents framework dir."""
        body = load_persona("academic.research")
        # This file should exist in frameworks/agency-agents/
        if body:
            assert len(body) > 100  # Persona files are substantial


class TestRolePersonaMap:
    def test_all_values_are_paths(self):
        for agent, path in ROLE_PERSONA_MAP.items():
            assert "/" in path, f"Path for {agent} should include category dir"
            assert path.endswith(".md"), f"Path for {agent} should be .md file"

    def test_academic_agents_mapped(self):
        assert "academic.research" in ROLE_PERSONA_MAP
        assert "academic.literature" in ROLE_PERSONA_MAP
        assert "academic.doe" in ROLE_PERSONA_MAP
        assert "academic.paper" in ROLE_PERSONA_MAP

    def test_experiment_agents_mapped(self):
        assert "experiment.simulation" in ROLE_PERSONA_MAP
        assert "experiment.analysis" in ROLE_PERSONA_MAP

    def test_leader_agents_mapped(self):
        assert "leader.dispatch" in ROLE_PERSONA_MAP
        assert "leader.synthesis" in ROLE_PERSONA_MAP


class TestPersonaMeta:
    def test_repr(self):
        meta = PersonaMeta(name="Test", emoji="🧪")
        assert "Test" in repr(meta)
        assert "🧪" in repr(meta)
