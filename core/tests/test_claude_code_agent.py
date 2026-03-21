"""Tests for oas_core.subagents.claude_code — Claude Code sub-agent."""
import pytest

from oas_core.subagents.claude_code import ClaudeCodeAgent, ClaudeCodeResult
from oas_core.protocols.drvp import configure


@pytest.fixture(autouse=True)
def disable_drvp():
    configure(company_id="test", redis_client=None, paperclip_client=None)


class TestClaudeCodeResult:
    def test_success(self):
        r = ClaudeCodeResult(exit_code=0, output="Done")
        assert r.success is True

    def test_failure(self):
        r = ClaudeCodeResult(exit_code=1, output="Error")
        assert r.success is False

    def test_to_dict(self):
        r = ClaudeCodeResult(
            exit_code=0,
            output="output",
            cost_usd=0.05,
            session_id="sess_1",
            files_changed=["main.py"],
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["cost_usd"] == 0.05
        assert d["files_changed"] == ["main.py"]


class TestClaudeCodeAgent:
    def test_build_command_basic(self):
        agent = ClaudeCodeAgent()
        cmd = agent._build_command("Analyze code", None)
        assert cmd[0] == "claude"
        assert "--print" in cmd
        assert "--prompt" in cmd
        assert "Analyze code" in cmd

    def test_build_command_with_model(self):
        agent = ClaudeCodeAgent(model="claude-sonnet-4-6-20260301")
        cmd = agent._build_command("test", None)
        assert "--model" in cmd
        assert "claude-sonnet-4-6-20260301" in cmd

    def test_build_command_with_system_prompt(self):
        agent = ClaudeCodeAgent()
        cmd = agent._build_command("test", "You are a firmware expert")
        assert "--system-prompt" in cmd
        assert "You are a firmware expert" in cmd

    def test_build_command_with_max_turns(self):
        agent = ClaudeCodeAgent(max_turns=5)
        cmd = agent._build_command("test", None)
        assert "--max-turns" in cmd
        assert "5" in cmd

    def test_build_command_with_allowed_tools(self):
        agent = ClaudeCodeAgent(allowed_tools=["Read", "Grep"])
        cmd = agent._build_command("test", None)
        assert "--allowedTools" in cmd
        assert "Read" in cmd
        assert "Grep" in cmd

    def test_parse_output_with_json(self):
        agent = ClaudeCodeAgent()
        result = ClaudeCodeResult(exit_code=0, output="")
        output = 'Some text\n{"cost_usd": 0.03, "session_id": "s1", "files_changed": ["a.py"]}\nMore text'
        result = agent._parse_output(result, output)
        assert result.cost_usd == 0.03
        assert result.session_id == "s1"
        assert result.files_changed == ["a.py"]

    def test_parse_output_no_json(self):
        agent = ClaudeCodeAgent()
        result = ClaudeCodeResult(exit_code=0, output="")
        result = agent._parse_output(result, "Plain text output")
        assert result.cost_usd is None
        assert result.session_id is None

    @pytest.mark.asyncio
    async def test_run_not_found(self):
        """Claude Code CLI not found returns error result."""
        agent = ClaudeCodeAgent(claude_bin="/nonexistent/claude")
        result = await agent.run("test prompt")
        assert result.exit_code == 127
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_check_available_not_found(self):
        agent = ClaudeCodeAgent(claude_bin="/nonexistent/claude")
        available = await agent.check_available()
        assert available is False
