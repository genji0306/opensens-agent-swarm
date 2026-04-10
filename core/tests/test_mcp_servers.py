"""Unit tests for the OAS MCP servers.

Covers model-router and openviking-memory without spinning up the stdio
transport — tests the pure routing/memory logic and the server factory
to ensure tool registration stays consistent with the schemas.
"""
from __future__ import annotations

import pytest


def _mcp_sdk_available() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


_MCP_INSTALLED = _mcp_sdk_available()


def test_model_router_list_tiers_shape():
    """TIER_TABLE must contain all 7 tiers with required keys."""
    from oas_core.mcp.model_router import TIER_TABLE

    assert len(TIER_TABLE) == 7
    required_keys = {"tier", "location", "gate", "cost_class"}
    tiers_seen = set()
    for entry in TIER_TABLE:
        assert required_keys <= set(entry.keys())
        tiers_seen.add(entry["tier"])

    expected_tiers = {
        "PLANNING_LOCAL",
        "REASONING_LOCAL",
        "WORKER_LOCAL",
        "CODE_LOCAL",
        "RL_EVOLVED",
        "CLAUDE_SONNET",
        "CLAUDE_OPUS",
    }
    assert tiers_seen == expected_tiers


def test_model_router_route_task_defaults():
    """Default routing: RESEARCH → REASONING_LOCAL, SIMULATE → CODE_LOCAL."""
    from oas_core.mcp.model_router import _route_task

    r = _route_task("RESEARCH", {})
    assert r["chosen_tier"] == "REASONING_LOCAL"
    assert r["would_escalate_to_sonnet"] is False
    assert r["would_request_opus"] is False

    r = _route_task("SIMULATE", {})
    assert r["chosen_tier"] == "CODE_LOCAL"


def test_model_router_confidential_blocks_cloud():
    """Confidential missions never route to cloud tiers."""
    from oas_core.mcp.model_router import _route_task

    # PERPLEXITY default is CLAUDE_SONNET — must be blocked
    r = _route_task("PERPLEXITY", {"confidential": True})
    assert r["chosen_tier"] not in {"CLAUDE_SONNET", "CLAUDE_OPUS"}
    assert "confidential" in r["reason"].lower()


def test_model_router_dev_unreachable_fallback():
    """DEV unreachable → DEV-bound tasks fall back to Leader PLANNING_LOCAL."""
    from oas_core.mcp.model_router import _route_task

    r = _route_task("RESEARCH", {"dev_reachable": False})
    assert r["chosen_tier"] == "PLANNING_LOCAL"
    assert "unreachable" in r["reason"].lower()


def test_model_router_prior_failure_escalates_to_sonnet():
    """Local tier failure escalates to Sonnet if budget allows."""
    from oas_core.mcp.model_router import _route_task

    r = _route_task(
        "RESEARCH",
        {"prior_tier_failed": True, "budget_remaining_usd": 10.0},
    )
    assert r["chosen_tier"] == "CLAUDE_SONNET"
    assert r["would_escalate_to_sonnet"] is True


def test_model_router_prior_failure_no_budget_blocks():
    """Local tier failure but exhausted budget → mission stays blocked."""
    from oas_core.mcp.model_router import _route_task

    r = _route_task(
        "RESEARCH",
        {"prior_tier_failed": True, "budget_remaining_usd": 0.0},
    )
    assert r["chosen_tier"] != "CLAUDE_SONNET"
    assert "budget" in r["reason"].lower()


def test_model_router_policy_rules_present():
    """All 4 policy rules must be exposed."""
    from oas_core.mcp.model_router import POLICY_RULES

    names = {r["name"] for r in POLICY_RULES}
    assert names == {
        "OpusGateRule",
        "SonnetBudgetRule",
        "IdleBudgetRule",
        "ConfidentialRule",
    }


def test_model_router_new_phase25_task_types():
    """Phase 25 task types (WIKI_*, EVAL_*) route to local tiers."""
    from oas_core.mcp.model_router import _route_task

    for tt in ("WIKI_COMPILE", "WIKI_LINT", "EVAL_RUN", "EVAL_REPORT"):
        r = _route_task(tt, {})
        assert r["chosen_tier"] == "PLANNING_LOCAL"
        assert r["would_request_opus"] is False


def test_openviking_memory_stub_roundtrip():
    """StubMemoryStore supports write, read, search, list."""
    from oas_core.mcp.openviking_memory import StubMemoryStore

    store = StubMemoryStore()
    e1 = store.write("sess-1", "BMIM-BF4 conductivity is high", ["ionic-liquid"], tier=1)
    e2 = store.write("sess-1", "PEDOT:PSS electrode study", ["electrode"], tier=0)
    e3 = store.write("sess-2", "Graphene membrane results", ["membrane"], tier=1)

    assert e1["id"] != e2["id"] != e3["id"]

    # Read by session + tiers
    read_sess1_all = store.read("sess-1", [0, 1])
    assert len(read_sess1_all) == 2

    read_sess1_hot = store.read("sess-1", [0])
    assert len(read_sess1_hot) == 1
    assert read_sess1_hot[0]["content"] == "PEDOT:PSS electrode study"

    # Search
    results = store.search("ionic", limit=5)
    assert len(results) == 1
    assert "BMIM" in results[0]["content"]

    # List sessions
    sessions = store.list_sessions(limit=10)
    assert len(sessions) == 2
    assert {s["session_id"] for s in sessions} == {"sess-1", "sess-2"}

    # Session context
    ctx = store.session_context("sess-1")
    assert ctx["entry_count"] == 2
    assert "ionic-liquid" in ctx["tags"]
    assert "electrode" in ctx["tags"]


def test_openviking_memory_search_limit():
    """search() respects the limit argument."""
    from oas_core.mcp.openviking_memory import StubMemoryStore

    store = StubMemoryStore()
    for i in range(10):
        store.write("sess-x", f"finding {i} about lithium", [], tier=1)

    results = store.search("lithium", limit=3)
    assert len(results) == 3


@pytest.mark.skipif(not _MCP_INSTALLED, reason="mcp SDK not installed")
def test_model_router_server_factory():
    """create_server() returns a usable Server instance."""
    from oas_core.mcp.model_router import create_server

    server = create_server()
    assert server is not None
    assert hasattr(server, "run")


@pytest.mark.skipif(not _MCP_INSTALLED, reason="mcp SDK not installed")
def test_openviking_memory_server_factory():
    """create_server() for openviking-memory returns a usable Server instance."""
    from oas_core.mcp.openviking_memory import create_server

    server = create_server()
    assert server is not None
    assert hasattr(server, "run")
