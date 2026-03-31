"""Tests for Leader dispatch routing."""
from shared.models import TaskType
from leader.dispatch import (
    parse_command,
    resolve_route,
    build_node_invoke,
    ROUTING_TABLE,
)


class TestParseCommand:
    def test_slash_command(self):
        cmd, args = parse_command("/research MnO2 nanoparticles")
        assert cmd == "research"
        assert args == "MnO2 nanoparticles"

    def test_slash_no_args(self):
        cmd, args = parse_command("/status")
        assert cmd == "status"
        assert args == ""

    def test_plain_text(self):
        cmd, args = parse_command("Tell me about sensors")
        assert cmd is None
        assert args == "Tell me about sensors"

    def test_multiline_args(self):
        cmd, args = parse_command("/simulate params:\nx=1\ny=2")
        assert cmd == "simulate"
        assert "x=1" in args

    def test_hyphenated_command(self):
        cmd, args = parse_command("/report-data figures for report")
        assert cmd == "report-data"
        assert args == "figures for report"

    def test_bot_mention_command(self):
        cmd, args = parse_command("/help@darklab_bot")
        assert cmd == "help"
        assert args == ""

    def test_case_insensitive(self):
        cmd, args = parse_command("/RESEARCH topic")
        assert cmd == "research"

    def test_empty_string(self):
        cmd, args = parse_command("")
        assert cmd is None
        assert args == ""


class TestResolveRoute:
    def test_all_commands_resolve(self):
        for cmd in ROUTING_TABLE:
            route = resolve_route(cmd)
            assert route is not None, f"Command '{cmd}' should resolve"
            assert route.node in ("academic", "experiment", "leader")
            assert route.skill.startswith("darklab-")

    def test_unknown_command(self):
        assert resolve_route("nonexistent") is None

    def test_telegram_alias_resolves(self):
        route = resolve_route("report_data")
        assert route is not None
        assert route.node == "experiment"
        assert route.skill == "darklab-report-data"

    def test_research_routes_to_academic(self):
        route = resolve_route("research")
        assert route.node == "academic"
        assert route.skill == "darklab-research"
        assert route.task_type == TaskType.RESEARCH

    def test_simulate_routes_to_experiment(self):
        route = resolve_route("simulate")
        assert route.node == "experiment"
        assert route.skill == "darklab-simulation"

    def test_analyze_routes_to_experiment(self):
        route = resolve_route("analyze")
        assert route.node == "experiment"
        assert route.skill == "darklab-analysis"

    def test_synthesize_routes_to_leader(self):
        route = resolve_route("synthesize")
        assert route.node == "leader"


class TestBuildNodeInvoke:
    def test_basic_invoke(self):
        route = resolve_route("research")
        msg = build_node_invoke(route, {"text": "sensor optimization"})
        assert msg["node"] == "darklab-academic"
        assert msg["command"] == "darklab-research"
        assert msg["payload"]["text"] == "sensor optimization"

    def test_invoke_preserves_payload(self):
        route = resolve_route("simulate")
        payload = {"text": "test", "params": {"x": 1}, "n_samples": 100}
        msg = build_node_invoke(route, payload)
        assert msg["payload"]["n_samples"] == 100
