"""OAS middleware pipeline.

Each middleware wraps an agent handler, adding cross-cutting concerns:
Budget → Audit → Governance → Memory → Summarization → DRVP emission.

The ``Pipeline`` class composes these middlewares into a single callable
that wraps any agent handler function.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from oas_core.middleware.audit import AuditMiddleware
from oas_core.middleware.budget import BudgetMiddleware
from oas_core.middleware.governance import GovernanceMiddleware
from oas_core.middleware.memory import MemoryMiddleware
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

__all__ = ["Pipeline", "PipelineConfig"]

logger = logging.getLogger("oas.middleware")


class PipelineConfig:
    """Configuration for the middleware pipeline.

    All middleware components are optional — pass ``None`` to skip.
    """

    def __init__(
        self,
        budget: BudgetMiddleware | None = None,
        audit: AuditMiddleware | None = None,
        governance: GovernanceMiddleware | None = None,
        memory: MemoryMiddleware | None = None,
    ):
        self.budget = budget
        self.audit = audit
        self.governance = governance
        self.memory = memory


class Pipeline:
    """Composable middleware pipeline for agent execution.

    Wraps an agent handler with cross-cutting concerns::

        pipeline = Pipeline(PipelineConfig(budget=bm, audit=am, memory=mm))

        result = await pipeline.execute(
            handler=my_agent_handler,
            task_id="task_123",
            agent_name="academic.research",
            device="academic",
            payload={"text": "Research quantum sensors"},
        )

    Execution order:
    1. DRVP: request.created event
    2. Budget: pre-check (raises if exhausted)
    3. Governance: open issue (if configured)
    4. Memory: pre-load relevant context → injects ``prior_context`` into payload
    5. Audit: log task start
    6. **Handler execution**
    7. Audit: log task end
    8. Memory: post-store findings
    9. Governance: update issue status
    10. DRVP: request.completed event
    """

    def __init__(self, config: PipelineConfig):
        self.config = config

    async def execute(
        self,
        handler: Callable[..., Awaitable[dict[str, Any]]],
        task_id: str,
        agent_name: str,
        device: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a handler through the full middleware pipeline."""
        req_id = request_id or task_id

        # 1. DRVP: request created
        await emit(DRVPEvent(
            event_type=DRVPEventType.REQUEST_CREATED,
            request_id=req_id,
            agent_name=agent_name,
            device=device,
            payload={"task_id": task_id},
        ))

        try:
            # 2. Budget pre-check
            if self.config.budget:
                await self.config.budget.check_budget(req_id, agent_name, device)

            # 3. Governance: open issue
            issue = None
            if self.config.governance:
                try:
                    title = payload.get("text", "")[:120] or f"Task {task_id}"
                    issue = await self.config.governance.open_issue(
                        request_id=req_id,
                        title=title,
                        agent_name=agent_name,
                        device=device,
                    )
                except Exception as e:
                    logger.warning("governance_open_issue_failed", extra={"error": str(e)})

            # 4. Memory: pre-load context
            if self.config.memory:
                query = payload.get("text", "") or payload.get("query", "")
                if query:
                    prior = await self.config.memory.pre_load(
                        req_id, agent_name, device, query
                    )
                    if prior:
                        payload = {**payload, "prior_context": prior}

            # 5. DRVP: agent activated
            await emit(DRVPEvent(
                event_type=DRVPEventType.AGENT_ACTIVATED,
                request_id=req_id,
                agent_name=agent_name,
                device=device,
                payload={},
            ))

            # 6. Audit: log start + execute handler + log end
            if self.config.audit:
                result = await self.config.audit(task_id, agent_name, payload, handler)
            else:
                result = await handler(payload)

            # 7. Memory: post-store findings
            if self.config.memory and result:
                await self.config.memory.post_store(
                    req_id, agent_name, device, task_id, result
                )

            # 8. Governance: update issue
            if self.config.governance and issue:
                try:
                    issue_id = issue.get("id")
                    if issue_id:
                        await self.config.governance.update_issue_status(
                            issue_id, "done"
                        )
                except Exception as e:
                    logger.warning("governance_update_failed", extra={"error": str(e)})

            # 9. DRVP: request completed
            await emit(DRVPEvent(
                event_type=DRVPEventType.REQUEST_COMPLETED,
                request_id=req_id,
                agent_name=agent_name,
                device=device,
                payload={"task_id": task_id, "status": "ok"},
            ))

            return result

        except Exception as e:
            # DRVP: request failed (wrapped to avoid swallowing the original)
            try:
                await emit(DRVPEvent(
                    event_type=DRVPEventType.REQUEST_FAILED,
                    request_id=req_id,
                    agent_name=agent_name,
                    device=device,
                    payload={"task_id": task_id, "error": str(e)},
                ))
            except Exception:
                logger.warning("drvp_emit_in_error_handler_failed", exc_info=True)
            raise
