"""Paperclip governance middleware — issue tracking and approval gates.

Task 13: Issue-driven research workflow
  - Auto-creates Paperclip issues for incoming research requests
  - Updates issue status as work progresses
  - Attaches results and costs to the issue

Task 14: Approval gates for campaigns
  - Multi-step campaign plans require human approval before execution
  - Creates Paperclip approval request with plan details
  - Polls for approval status before proceeding
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from typing import Any

from oas_core.adapters.paperclip import PaperclipClient, PaperclipError
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

try:
    import nacl.signing  # type: ignore[import-untyped]

    _NACL_AVAILABLE = True
except ImportError:
    _NACL_AVAILABLE = False

__all__ = ["GovernanceMiddleware"]

logger = logging.getLogger("oas.middleware.governance")


class GovernanceMiddleware:
    """Issue tracking and approval gates via Paperclip.

    Usage::

        gov = GovernanceMiddleware(paperclip_client, agent_id="agt_leader")
        issue = await gov.open_issue(request_id, "Research quantum sensors", ...)
        # ... work happens ...
        await gov.update_issue_status(issue["id"], "in_progress")
        # For campaigns:
        approved = await gov.request_campaign_approval(request_id, plan, ...)
        if not approved:
            return  # blocked
        # ... execute campaign ...
        await gov.close_issue(issue["id"], result_summary)
    """

    def __init__(
        self,
        paperclip: PaperclipClient | None,
        agent_id: str,
        *,
        approval_timeout: float = 300.0,
        approval_poll_interval: float = 5.0,
    ):
        self.paperclip = paperclip
        self.agent_id = agent_id
        self._approval_timeout = approval_timeout
        self._poll_interval = approval_poll_interval

    # --- Issue Lifecycle ---

    async def open_issue(
        self,
        request_id: str,
        title: str,
        agent_name: str,
        device: str,
        *,
        description: str | None = None,
        priority: str = "medium",
    ) -> dict | None:
        """Create a Paperclip issue for a research request.

        Returns the created issue dict, or None if Paperclip unavailable.
        """
        if not self.paperclip:
            return None

        try:
            issue = await self.paperclip.create_issue(
                title=title,
                description=description or f"Auto-created from request {request_id}",
                assignee_agent_id=self.agent_id,
                priority=priority,
                status="in_progress",
            )

            await emit(DRVPEvent(
                event_type=DRVPEventType.REQUEST_CREATED,
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={
                    "issue_id": issue.get("id"),
                    "issue_key": issue.get("key"),
                    "title": title,
                },
            ))

            logger.info(
                "issue_created: id=%s key=%s request_id=%s",
                issue.get("id"), issue.get("key"), request_id,
            )
            return issue
        except PaperclipError as e:
            logger.warning("issue_create_failed: %s (request_id=%s)", e, request_id)
            return None

    async def update_issue_status(
        self,
        issue_id: str,
        status: str,
        *,
        details: dict | None = None,
    ) -> None:
        """Log a status update on an issue via Paperclip activity log."""
        if not self.paperclip:
            return

        try:
            await self.paperclip.log_activity(
                action=f"issue.status.{status}",
                entity_type="issue",
                entity_id=issue_id,
                agent_id=self.agent_id,
                details={"status": status, **(details or {})},
            )
        except PaperclipError as e:
            logger.warning("issue_update_failed: %s (issue_id=%s)", e, issue_id)

    async def close_issue(
        self,
        issue_id: str,
        result_summary: str,
        request_id: str = "",
        agent_name: str = "leader",
        device: str = "leader",
    ) -> None:
        """Mark an issue as done and log the result summary."""
        if not self.paperclip:
            return

        try:
            await self.paperclip.log_activity(
                action="issue.status.done",
                entity_type="issue",
                entity_id=issue_id,
                agent_id=self.agent_id,
                details={"status": "done", "result_summary": result_summary[:500]},
            )

            if request_id:
                await emit(DRVPEvent(
                    event_type=DRVPEventType.REQUEST_COMPLETED,
                    request_id=request_id,
                    agent_name=agent_name,
                    device=device,
                    payload={"issue_id": issue_id, "status": "done"},
                ))
        except PaperclipError as e:
            logger.warning("issue_close_failed: %s (issue_id=%s)", e, issue_id)

    # --- Campaign Approval Gates ---

    async def request_campaign_approval(
        self,
        request_id: str,
        plan: list[dict],
        agent_name: str = "leader",
        device: str = "leader",
        *,
        issue_id: str | None = None,
        auto_approve_single_step: bool = True,
    ) -> dict:
        """Request human approval for a multi-step campaign plan.

        Returns a dict with:
          - ``approved``: bool — whether the campaign was approved
          - ``approval_id``: str | None — the Paperclip approval record ID
          - ``reason``: str — why it was approved/rejected/timed out

        Single-step plans are auto-approved by default.
        """
        if auto_approve_single_step and len(plan) <= 1:
            return {"approved": True, "approval_id": None, "reason": "single_step_auto"}

        if not self.paperclip:
            return {"approved": True, "approval_id": None, "reason": "paperclip_unavailable"}

        # Emit DRVP event for approval request
        await emit(DRVPEvent(
            event_type=DRVPEventType.CAMPAIGN_STEP_COMPLETED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"action": "approval_requested", "n_steps": len(plan)},
        ))

        try:
            step_summaries = [
                f"Step {s.get('step', i+1)}: /{s.get('command', '?')} {s.get('args', '')}"
                for i, s in enumerate(plan)
            ]

            approval = await self.paperclip.create_approval(
                approval_type="campaign_execution",
                requested_by_agent_id=self.agent_id,
                payload={
                    "request_id": request_id,
                    "n_steps": len(plan),
                    "steps": step_summaries,
                    "plan": plan,
                },
                issue_ids=[issue_id] if issue_id else None,
            )

            approval_id = approval.get("id", "")
            logger.info(
                "approval_requested: id=%s steps=%d request_id=%s",
                approval_id, len(plan), request_id,
            )

            # Poll for approval decision
            status = await self._poll_approval(approval_id)

            return {
                "approved": status == "approved",
                "approval_id": approval_id,
                "reason": status,
            }

        except PaperclipError as e:
            logger.warning("approval_request_failed: %s", e)
            # Fail-closed: block campaign execution when governance is unavailable.
            # Approval gates are safety controls — bypassing them on outage is risky.
            return {"approved": False, "approval_id": None, "reason": "paperclip_error_fail_closed"}

    async def _poll_approval(self, approval_id: str) -> str:
        """Poll Paperclip for approval status until resolved or timeout.

        Returns one of: 'approved', 'rejected', 'timeout'.
        """
        if not self.paperclip:
            return "approved"

        elapsed = 0.0
        while elapsed < self._approval_timeout:
            try:
                data = await self.paperclip.get_approval(approval_id)
                status = data.get("status", "pending")
                if status in ("approved", "rejected"):
                    logger.info(
                        "approval_resolved: id=%s status=%s",
                        approval_id, status,
                    )
                    return status
            except PaperclipError:
                pass

            await asyncio.sleep(self._poll_interval)
            elapsed += self._poll_interval

        logger.warning("approval_timeout: approval_id=%s", approval_id)
        return "timeout"

    # --- Signed Approval Records ---

    @staticmethod
    def sign_approval(
        approval_data: dict[str, Any],
        signing_key_seed: bytes,
    ) -> dict[str, Any]:
        """Sign an approval record with Ed25519.

        Returns the approval_data with ``signature`` and ``signer_public_key`` added.
        Requires PyNaCl.
        """
        if not _NACL_AVAILABLE:
            logger.warning("nacl_not_available: cannot sign approval")
            return approval_data

        signing_key = nacl.signing.SigningKey(signing_key_seed)
        payload_bytes = json.dumps(
            approval_data, sort_keys=True, default=str
        ).encode()
        signed = signing_key.sign(payload_bytes)

        return {
            **approval_data,
            "signature": base64.b64encode(signed.signature).decode(),
            "signer_public_key": base64.b64encode(
                signing_key.verify_key.encode()
            ).decode(),
        }

    @staticmethod
    def verify_approval_signature(signed_data: dict[str, Any]) -> bool:
        """Verify an Ed25519-signed approval record.

        Returns True if valid, False if invalid or PyNaCl unavailable.
        """
        if not _NACL_AVAILABLE:
            return False

        signature_b64 = signed_data.get("signature")
        pubkey_b64 = signed_data.get("signer_public_key")
        if not signature_b64 or not pubkey_b64:
            return False

        # Reconstruct the payload without signature fields
        payload = {
            k: v
            for k, v in signed_data.items()
            if k not in ("signature", "signer_public_key")
        }
        payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()

        try:
            signature = base64.b64decode(signature_b64)
            pubkey_bytes = base64.b64decode(pubkey_b64)
            verify_key = nacl.signing.VerifyKey(pubkey_bytes)
            verify_key.verify(payload_bytes, signature)
            return True
        except Exception:
            return False
