"""MiroShark simulation engine client.

Wraps the MiroShark backend API to generate multi-agent debates
for synthetic RL training data. Supports configuring debate scenarios,
running simulations, and extracting structured transcripts.
"""
from __future__ import annotations

import logging
from typing import Any

__all__ = ["MiroSharkAdapter", "MIROSHARK_AVAILABLE"]

logger = logging.getLogger("oas.adapters.miroshark")

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

MIROSHARK_AVAILABLE = _AIOHTTP_AVAILABLE

# Predefined debate scenario configs
DEBATE_SCENARIOS: dict[str, dict[str, Any]] = {
    "peer-review": {
        "description": "Simulate hostile peer reviewers evaluating a research paper",
        "agent_types": ["domain_expert", "methodologist", "contrarian", "journal_reviewer"],
        "default_agents": 8,
        "default_rounds": 15,
    },
    "hypothesis": {
        "description": "Agents argue for and against a research hypothesis",
        "agent_types": ["domain_expert", "contrarian", "cross_domain", "synthesizer"],
        "default_agents": 12,
        "default_rounds": 10,
    },
    "methodology": {
        "description": "Challenge statistical validity and experimental design",
        "agent_types": ["methodologist", "domain_expert", "contrarian"],
        "default_agents": 10,
        "default_rounds": 10,
    },
    "literature-dispute": {
        "description": "Debate conflicting findings from different papers",
        "agent_types": ["domain_expert", "cross_domain", "synthesizer"],
        "default_agents": 15,
        "default_rounds": 12,
    },
    "cross-domain": {
        "description": "Challenge applicability of findings across domains",
        "agent_types": ["domain_expert", "cross_domain", "contrarian", "synthesizer"],
        "default_agents": 12,
        "default_rounds": 10,
    },
    "budget": {
        "description": "Debate resource allocation for a research proposal",
        "agent_types": ["domain_expert", "methodologist", "synthesizer"],
        "default_agents": 8,
        "default_rounds": 8,
    },
}


class MiroSharkAdapter:
    """Client for the MiroShark simulation backend.

    Usage::

        adapter = MiroSharkAdapter(base_url="http://localhost:5001")
        sim = await adapter.create_simulation(
            topic="CRISPR off-target effects are under-reported",
            scenario="peer-review",
            rounds=15,
        )
        result = await adapter.run_simulation(sim["simulation_id"])
        transcript = await adapter.get_transcript(sim["simulation_id"])
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 600.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def create_simulation(
        self,
        topic: str,
        *,
        scenario: str = "hypothesis",
        num_agents: int | None = None,
        num_rounds: int | None = None,
        platforms: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new debate simulation in MiroShark.

        Args:
            topic: The debate topic or hypothesis.
            scenario: Debate scenario type (see DEBATE_SCENARIOS).
            num_agents: Number of debate agents (default from scenario).
            num_rounds: Number of debate rounds (default from scenario).
            platforms: Social platforms to simulate (default: ["twitter", "reddit"]).

        Returns:
            Simulation metadata including simulation_id.
        """
        if not MIROSHARK_AVAILABLE:
            raise RuntimeError("aiohttp required for MiroShark adapter")

        scenario_config = DEBATE_SCENARIOS.get(scenario, DEBATE_SCENARIOS["hypothesis"])

        payload = {
            "topic": topic,
            "num_agents": num_agents or scenario_config["default_agents"],
            "num_rounds": num_rounds or scenario_config["default_rounds"],
            "platforms": platforms or ["twitter", "reddit"],
            "config": {
                "scenario": scenario,
                "agent_types": scenario_config["agent_types"],
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/simulation/create",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def run_simulation(self, simulation_id: str) -> dict[str, Any]:
        """Start and wait for a simulation to complete.

        This is a long-running operation — MiroShark simulations can take
        minutes depending on agent count and round count.
        """
        if not MIROSHARK_AVAILABLE:
            raise RuntimeError("aiohttp required for MiroShark adapter")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/simulation/{simulation_id}/run",
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_simulation_status(self, simulation_id: str) -> dict[str, Any]:
        """Get the current status of a simulation."""
        if not MIROSHARK_AVAILABLE:
            raise RuntimeError("aiohttp required for MiroShark adapter")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/simulation/{simulation_id}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_transcript(self, simulation_id: str) -> dict[str, Any]:
        """Get the full debate transcript from a completed simulation.

        Returns the raw MiroShark transcript data suitable for
        TranscriptConverter.from_miroshark_json().
        """
        if not MIROSHARK_AVAILABLE:
            raise RuntimeError("aiohttp required for MiroShark adapter")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/simulation/{simulation_id}/transcript",
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_belief_states(self, simulation_id: str) -> list[dict[str, Any]]:
        """Get belief state history for all agents in a simulation."""
        if not MIROSHARK_AVAILABLE:
            raise RuntimeError("aiohttp required for MiroShark adapter")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/simulation/{simulation_id}/beliefs",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("belief_states", [])

    async def health_check(self) -> bool:
        """Check if MiroShark backend is reachable."""
        if not MIROSHARK_AVAILABLE:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
