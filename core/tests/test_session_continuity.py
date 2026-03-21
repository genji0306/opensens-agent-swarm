"""Tests for session continuity features in MemoryClient."""
import pytest

from oas_core.memory import MemoryClient, SCOPE_SESSION


class TestSessionContext:
    @pytest.mark.asyncio
    async def test_load_session_context(self, monkeypatch):
        client = MemoryClient()
        called_with = {}

        async def mock_read(uri, level):
            called_with.update({"uri": uri, "level": level})
            return {"uri": uri, "level": level, "content": "session data"}

        monkeypatch.setattr(client, "read", mock_read)
        result = await client.load_session_context("session_abc", level=1)

        assert called_with["uri"] == f"{SCOPE_SESSION}/session_abc"
        assert called_with["level"] == 1
        assert result["content"] == "session data"

    @pytest.mark.asyncio
    async def test_archive_session(self, monkeypatch):
        client = MemoryClient()
        written = {}

        async def mock_write(uri, content, level):
            written.update({"uri": uri, "content": content, "level": level})

        monkeypatch.setattr(client, "write", mock_write)
        await client.archive_session(
            "session_xyz",
            messages=[{"role": "user", "content": "hello"}],
            summary="Test session",
            agent_name="academic",
        )

        assert written["uri"] == f"{SCOPE_SESSION}/session_xyz"
        assert written["level"] == 2
        assert written["content"]["summary"] == "Test session"
        assert written["content"]["message_count"] == 1

    @pytest.mark.asyncio
    async def test_find_related_sessions(self, monkeypatch):
        client = MemoryClient()

        async def mock_search(query, target_uri, limit, score_threshold):
            return [{"uri": f"{SCOPE_SESSION}/old_session", "score": 0.7}]

        monkeypatch.setattr(client, "search", mock_search)
        results = await client.find_related_sessions("quantum sensors")

        assert len(results) == 1
        assert results[0]["score"] == 0.7


class TestGoalHierarchyInPaperclip:
    """Tests for Paperclip goal hierarchy API methods."""

    @pytest.mark.asyncio
    async def test_create_goal(self, monkeypatch):
        from oas_core.adapters.paperclip import PaperclipClient

        client = PaperclipClient("http://localhost:3100", "key", "comp_1")
        called = {}

        async def mock_request(method, path, **kwargs):
            called.update({"method": method, "path": path, **kwargs})
            return {"id": "goal_1", "title": "Advance EIT"}

        monkeypatch.setattr(client, "_request", mock_request)
        result = await client.create_goal(
            "Advance EIT technology",
            "objective",
            description="Main research objective",
        )

        assert called["method"] == "POST"
        assert "/goals" in called["path"]
        assert called["json"]["level"] == "objective"
        assert result["id"] == "goal_1"

    @pytest.mark.asyncio
    async def test_get_goals(self, monkeypatch):
        from oas_core.adapters.paperclip import PaperclipClient

        client = PaperclipClient("http://localhost:3100", "key", "comp_1")

        async def mock_request(method, path, **kwargs):
            return {"goals": [{"id": "g1", "title": "Goal 1"}]}

        monkeypatch.setattr(client, "_request", mock_request)
        goals = await client.get_goals(level="objective")
        assert len(goals) == 1

    @pytest.mark.asyncio
    async def test_update_goal(self, monkeypatch):
        from oas_core.adapters.paperclip import PaperclipClient

        client = PaperclipClient("http://localhost:3100", "key", "comp_1")
        called = {}

        async def mock_request(method, path, **kwargs):
            called.update({"method": method, "path": path, **kwargs})
            return {"id": "g1", "status": "in_progress"}

        monkeypatch.setattr(client, "_request", mock_request)
        await client.update_goal("g1", status="in_progress", progress=0.5)

        assert called["method"] == "PATCH"
        assert called["json"]["status"] == "in_progress"
        assert called["json"]["progress"] == 0.5

    @pytest.mark.asyncio
    async def test_link_issue_to_goal(self, monkeypatch):
        from oas_core.adapters.paperclip import PaperclipClient

        client = PaperclipClient("http://localhost:3100", "key", "comp_1")
        called = {}

        async def mock_request(method, path, **kwargs):
            called.update({"method": method, "path": path, **kwargs})
            return {}

        monkeypatch.setattr(client, "_request", mock_request)
        await client.link_issue_to_goal("issue_42", "goal_1")

        assert "/goals/goal_1/issues" in called["path"]
        assert called["json"]["issueId"] == "issue_42"

    @pytest.mark.asyncio
    async def test_get_issues_with_filters(self, monkeypatch):
        from oas_core.adapters.paperclip import PaperclipClient

        client = PaperclipClient("http://localhost:3100", "key", "comp_1")

        async def mock_request(method, path, **kwargs):
            return {"issues": [{"id": "i1", "status": "in_progress"}]}

        monkeypatch.setattr(client, "_request", mock_request)
        issues = await client.get_issues(status="in_progress")
        assert len(issues) == 1
