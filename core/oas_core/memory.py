"""OpenViking integration layer for persistent agent memory.

Wraps the OpenViking HTTP API to provide tiered context retrieval
(L0 abstract, L1 overview, L2 full detail) and write-back for storing
research findings after agent execution.

Uses HTTP mode (no native bindings required) — connects to the OpenViking
server at the configured URL.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

__all__ = [
    "MemoryClient",
    "MemoryError",
    "SCOPE_AGENT",
    "SCOPE_SESSION",
    "SCOPE_RESOURCES",
    "SCOPE_RESEARCH",
    "SCOPE_EXPERIMENTS",
    "SCOPE_KNOWLEDGE",
]

logger = logging.getLogger("oas.memory")

# Viking URI scopes used by DarkLab agents
SCOPE_AGENT = "viking://agent"
SCOPE_SESSION = "viking://session"
SCOPE_RESOURCES = "viking://resources"
SCOPE_RESEARCH = "viking://research"
SCOPE_EXPERIMENTS = "viking://experiments"
SCOPE_KNOWLEDGE = "viking://knowledge"


class MemoryError(Exception):
    """Raised when an OpenViking operation fails."""

    def __init__(self, detail: str, status_code: int | None = None):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class MemoryClient:
    """Async client for the OpenViking HTTP API.

    Provides tiered context reading (L0/L1/L2) and write-back,
    plus semantic search for finding relevant past context.

    Usage::

        client = MemoryClient("http://localhost:1933", api_key="...")
        context = await client.read("viking://agent/memories/cases/eit-sim-01")
        await client.write("viking://agent/memories/cases/eit-sim-02", {
            "title": "EIT Simulation Results",
            "content": "...",
        })
        results = await client.search("quantum dot electrode impedance", limit=5)
        await client.close()
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1933",
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise MemoryError(
                f"OpenViking {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
        if resp.status_code == 204:
            return {}
        return resp.json()

    # --- Tiered reading ---

    async def abstract(self, uri: str) -> str:
        """Read L0 abstract (ultra-condensed, 10-50 tokens)."""
        data = await self._request("GET", "/api/abstract", params={"uri": uri})
        return data.get("abstract", "")

    async def overview(self, uri: str) -> str:
        """Read L1 overview (medium detail, 100-300 tokens)."""
        data = await self._request("GET", "/api/overview", params={"uri": uri})
        return data.get("overview", "")

    async def read(self, uri: str, level: int = 2) -> dict[str, Any]:
        """Read context at a given detail level.

        Args:
            uri: Viking URI (e.g. ``viking://agent/memories/cases/foo``)
            level: 0=abstract, 1=overview, 2=full content
        """
        if level == 0:
            return {"uri": uri, "level": 0, "content": await self.abstract(uri)}
        if level == 1:
            return {"uri": uri, "level": 1, "content": await self.overview(uri)}
        data = await self._request("GET", "/api/read", params={"uri": uri})
        return {"uri": uri, "level": 2, "content": data.get("content", "")}

    # --- Writing ---

    async def write(self, uri: str, content: str | dict, level: int = 2) -> None:
        """Write content to a Viking URI.

        Args:
            uri: Target Viking URI
            content: String or dict payload to store
            level: Detail level (default L2 full)
        """
        body: dict[str, Any] = {"uri": uri, "level": level}
        if isinstance(content, str):
            body["content"] = content
        else:
            body["content"] = content
        await self._request("POST", "/api/write", json=body)
        logger.debug("memory_write", extra={"uri": uri, "level": level})

    # --- Directory operations ---

    async def ls(self, uri: str) -> list[dict[str, Any]]:
        """List children of a Viking URI directory."""
        data = await self._request("GET", "/api/ls", params={"uri": uri})
        return data.get("items", [])

    async def mkdir(self, uri: str) -> None:
        """Create a directory at the given Viking URI."""
        await self._request("POST", "/api/mkdir", json={"uri": uri})

    # --- Search ---

    async def search(
        self,
        query: str,
        target_uri: str = SCOPE_AGENT,
        *,
        limit: int = 10,
        score_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Semantic search for relevant context.

        Args:
            query: Natural language search query
            target_uri: Scope to search within
            limit: Max results
            score_threshold: Minimum relevance score (0-1)
        """
        data = await self._request(
            "POST",
            "/api/find",
            json={
                "query": query,
                "target_uri": target_uri,
                "limit": limit,
                "score_threshold": score_threshold,
            },
        )
        return data.get("results", [])

    # --- Relations ---

    async def link(self, from_uri: str, to_uris: list[str], reason: str = "") -> None:
        """Create explicit cross-references between contexts."""
        await self._request(
            "POST",
            "/api/link",
            json={"from_uri": from_uri, "to_uris": to_uris, "reason": reason},
        )

    async def relations(self, uri: str) -> list[dict[str, Any]]:
        """Get all relations for a given URI."""
        data = await self._request("GET", "/api/relations", params={"uri": uri})
        return data.get("relations", [])

    # --- Session continuity ---

    async def load_session_context(
        self,
        session_id: str,
        *,
        level: int = 1,
    ) -> dict[str, Any]:
        """Load follow-up context from a previous session.

        Reads the session archive at ``viking://session/{session_id}``
        at the requested detail level, enabling agents to continue
        prior conversations.

        Args:
            session_id: Previous session/request identifier
            level: Detail level (0=abstract, 1=overview, 2=full)
        """
        uri = f"{SCOPE_SESSION}/{session_id}"
        return await self.read(uri, level=level)

    async def archive_session(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        *,
        summary: str = "",
        agent_name: str = "",
    ) -> None:
        """Archive a completed session for future follow-up.

        Writes session content to ``viking://session/{session_id}``
        so subsequent requests can reference it.

        Args:
            session_id: Session/request identifier
            messages: Conversation messages to archive
            summary: Human-readable summary of the session
            agent_name: Agent that handled the session
        """
        uri = f"{SCOPE_SESSION}/{session_id}"
        content = {
            "session_id": session_id,
            "agent_name": agent_name,
            "summary": summary,
            "message_count": len(messages),
            "messages": messages,
        }
        await self.write(uri, content, level=2)
        logger.debug("session_archived", extra={"session_id": session_id})

    async def find_related_sessions(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for prior sessions relevant to a query.

        Searches ``viking://session/`` scope for semantically similar
        past sessions.
        """
        return await self.search(
            query=query,
            target_uri=SCOPE_SESSION,
            limit=limit,
            score_threshold=0.4,
        )

    # --- Research knowledge graph ---

    async def store_research(
        self,
        topic: str,
        findings: dict[str, Any],
        *,
        subtopic: str = "",
        agent_name: str = "",
        request_id: str = "",
    ) -> str:
        """Store research findings in the knowledge graph.

        Schema::

            viking://research/{topic}/{subtopic}
              L0: title + one-line summary
              L1: abstract + key findings + citation count
              L2: full data + methodology + artifacts

        Returns the Viking URI of the stored entry.
        """
        slug = _slugify(topic)
        uri = f"{SCOPE_RESEARCH}/{slug}"
        if subtopic:
            uri = f"{uri}/{_slugify(subtopic)}"

        content = {
            "topic": topic,
            "subtopic": subtopic or None,
            "agent_name": agent_name,
            "request_id": request_id,
            **findings,
        }
        await self.write(uri, content, level=2)

        # Auto-link to session if request_id provided
        if request_id:
            session_uri = f"{SCOPE_SESSION}/{request_id}"
            try:
                await self.link(uri, [session_uri], reason="research_output")
            except Exception:
                pass  # Non-fatal

        logger.debug("research_stored", extra={"uri": uri, "topic": topic})
        return uri

    async def find_research(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search across the research knowledge graph."""
        return await self.search(
            query=query,
            target_uri=SCOPE_RESEARCH,
            limit=limit,
            score_threshold=0.3,
        )

    async def store_experiment(
        self,
        name: str,
        results: dict[str, Any],
        *,
        research_topic: str = "",
        agent_name: str = "",
        request_id: str = "",
    ) -> str:
        """Store experiment results and link to research topic.

        Schema: ``viking://experiments/{name}``
        """
        slug = _slugify(name)
        uri = f"{SCOPE_EXPERIMENTS}/{slug}"

        content = {
            "name": name,
            "agent_name": agent_name,
            "request_id": request_id,
            **results,
        }
        await self.write(uri, content, level=2)

        # Cross-link to research topic
        if research_topic:
            research_uri = f"{SCOPE_RESEARCH}/{_slugify(research_topic)}"
            try:
                await self.link(uri, [research_uri], reason="experiment_for_research")
            except Exception:
                pass

        logger.debug("experiment_stored", extra={"uri": uri, "name": name})
        return uri

    async def build_knowledge_context(
        self,
        query: str,
        *,
        max_research: int = 5,
        max_experiments: int = 3,
        max_sessions: int = 3,
    ) -> dict[str, Any]:
        """Build a comprehensive context bundle from the knowledge graph.

        Searches research, experiments, and sessions for relevant context
        and returns a structured bundle suitable for injection into agent prompts.
        """
        research = await self.find_research(query, limit=max_research)
        experiments = await self.search(
            query, target_uri=SCOPE_EXPERIMENTS, limit=max_experiments,
        )
        sessions = await self.find_related_sessions(query, limit=max_sessions)

        return {
            "query": query,
            "research": research,
            "experiments": experiments,
            "related_sessions": sessions,
            "total_sources": len(research) + len(experiments) + len(sessions),
        }


def _slugify(text: str) -> str:
    """Convert text to a URI-safe slug."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:80].rstrip("-") or "untitled"
