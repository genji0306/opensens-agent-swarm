"""Tests for oas_core.middleware Pipeline compositor."""
import pytest

from oas_core.middleware import Pipeline, PipelineConfig
from oas_core.middleware.audit import AuditMiddleware
from oas_core.middleware.memory import MemoryMiddleware
from oas_core.memory import MemoryClient
from oas_core.protocols.drvp import configure


@pytest.fixture(autouse=True)
def disable_drvp():
    configure(company_id="test", redis_client=None, paperclip_client=None)


class TestPipelineBasic:
    @pytest.mark.asyncio
    async def test_execute_without_middleware(self):
        pipeline = Pipeline(PipelineConfig())

        async def handler(payload):
            return {"answer": payload["question"]}

        result = await pipeline.execute(
            handler=handler,
            task_id="t_1",
            agent_name="test",
            device="leader",
            payload={"question": "What is EIT?"},
        )

        assert result["answer"] == "What is EIT?"

    @pytest.mark.asyncio
    async def test_execute_with_audit(self, tmp_path):
        audit = AuditMiddleware(log_dir=tmp_path)
        pipeline = Pipeline(PipelineConfig(audit=audit))

        async def handler(payload):
            return {"result": "done"}

        result = await pipeline.execute(
            handler=handler,
            task_id="t_2",
            agent_name="academic",
            device="academic",
            payload={"text": "test"},
        )

        assert result["result"] == "done"

        # Verify audit log was written
        log_file = tmp_path / "audit.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2  # start + end

    @pytest.mark.asyncio
    async def test_execute_with_memory(self, monkeypatch):
        client = MemoryClient()

        async def mock_search(**kwargs):
            return [{"uri": "viking://agent/foo", "content": "prior work"}]

        async def mock_write(uri, content, level):
            pass

        monkeypatch.setattr(client, "search", mock_search)
        monkeypatch.setattr(client, "write", mock_write)

        memory = MemoryMiddleware(client)
        pipeline = Pipeline(PipelineConfig(memory=memory))

        received_payload = {}

        async def handler(payload):
            received_payload.update(payload)
            return {"findings": "new data"}

        await pipeline.execute(
            handler=handler,
            task_id="t_3",
            agent_name="academic",
            device="academic",
            payload={"text": "quantum sensors"},
        )

        # Memory should inject prior_context
        assert "prior_context" in received_payload
        assert len(received_payload["prior_context"]) == 1

    @pytest.mark.asyncio
    async def test_execute_handler_error_propagates(self):
        pipeline = Pipeline(PipelineConfig())

        async def bad_handler(payload):
            raise ValueError("Something broke")

        with pytest.raises(ValueError, match="Something broke"):
            await pipeline.execute(
                handler=bad_handler,
                task_id="t_4",
                agent_name="test",
                device="leader",
                payload={},
            )

    @pytest.mark.asyncio
    async def test_execute_with_custom_request_id(self):
        pipeline = Pipeline(PipelineConfig())

        async def handler(payload):
            return {"ok": True}

        result = await pipeline.execute(
            handler=handler,
            task_id="t_5",
            agent_name="test",
            device="leader",
            payload={},
            request_id="custom_req_123",
        )

        assert result["ok"] is True
