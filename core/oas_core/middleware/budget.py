"""Paperclip-aware budget enforcement middleware.

Provides ``check_budget()`` and ``report_cost()`` methods that wrap LLM calls
with Paperclip budget pre-check and post-report. Falls back to the existing
file-locked spend JSON when Paperclip is unreachable.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from oas_core.adapters.paperclip import PaperclipClient, PaperclipError
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

__all__ = ["BudgetMiddleware"]

logger = logging.getLogger("oas.middleware.budget")


class BudgetMiddleware:
    """Composable budget enforcement for LLM calls.

    Usage::

        mw = BudgetMiddleware(paperclip_client, agent_id)
        info = await mw.check_budget(request_id, agent_name, device)
        # ... LLM call ...
        await mw.report_cost(request_id, agent_name, device,
                             provider, model, in_tok, out_tok, cost_usd)
    """

    def __init__(
        self,
        paperclip: PaperclipClient | None,
        agent_id: str,
        *,
        fallback_record: Callable[..., Any] | None = None,
        budget_warn_threshold: float = 0.8,
    ):
        self.paperclip = paperclip
        self.agent_id = agent_id
        self._fallback_record = fallback_record
        self._warn_threshold = budget_warn_threshold

    async def check_budget(
        self,
        request_id: str,
        agent_name: str,
        device: str,
    ) -> dict:
        """Pre-check budget before an LLM call. Raises RuntimeError if exhausted."""
        await emit(DRVPEvent(
            event_type=DRVPEventType.BUDGET_CHECK,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"agent_id": self.agent_id},
        ))

        if self.paperclip:
            try:
                agent_data = await self.paperclip.get_agent_budget(self.agent_id)
                budget_cents = agent_data.get("budgetMonthlyCents", 0)
                summary = await self.paperclip.get_cost_summary()
                spent_cents = summary.get("totalCents", 0)

                remaining_cents = budget_cents - spent_cents
                usage_ratio = spent_cents / budget_cents if budget_cents > 0 else 0.0

                if usage_ratio >= self._warn_threshold:
                    await emit(DRVPEvent(
                        event_type=DRVPEventType.BUDGET_WARNING,
                        request_id=request_id,
                        agent_name=agent_name,
                        device=device,
                        payload={
                            "budget_cents": budget_cents,
                            "spent_cents": spent_cents,
                            "usage_ratio": round(usage_ratio, 3),
                        },
                    ))

                if remaining_cents <= 0:
                    await emit(DRVPEvent(
                        event_type=DRVPEventType.BUDGET_EXHAUSTED,
                        request_id=request_id,
                        agent_name=agent_name,
                        device=device,
                        payload={"budget_cents": budget_cents, "spent_cents": spent_cents},
                    ))
                    raise RuntimeError(
                        f"Monthly budget exhausted for agent {agent_name}: "
                        f"${spent_cents / 100:.2f} / ${budget_cents / 100:.2f}"
                    )

                return {
                    "source": "paperclip",
                    "budget_cents": budget_cents,
                    "spent_cents": spent_cents,
                    "remaining_cents": remaining_cents,
                }
            except PaperclipError as e:
                logger.warning("paperclip_budget_check_failed", exc_info=e)

        return {"source": "file_lock", "note": "Paperclip unavailable, using local budget"}

    async def report_cost(
        self,
        request_id: str,
        agent_name: str,
        device: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """Post-report cost after an LLM call completes."""
        cost_cents = max(1, round(cost_usd * 100))

        # Always record locally as fallback
        if self._fallback_record:
            try:
                self._fallback_record(cost_usd, provider, model)
            except Exception as e:
                logger.warning("local_budget_record_failed", exc_info=e)

        # Report to Paperclip
        if self.paperclip:
            try:
                await self.paperclip.report_cost(
                    agent_id=self.agent_id,
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_cents=cost_cents,
                )
            except PaperclipError as e:
                logger.warning("paperclip_cost_report_failed", exc_info=e)

        # Emit DRVP event
        await emit(DRVPEvent(
            event_type=DRVPEventType.LLM_CALL_COMPLETED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost_usd, 6),
            },
        ))
