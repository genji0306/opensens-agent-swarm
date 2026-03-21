"""Ed25519 audit middleware.

Wraps task execution with cryptographic audit logging — hashes the
payload on entry and the result on exit, signing both with an Ed25519
key. Produces append-only JSONL audit entries compatible with the
existing ``cluster/agents/shared/audit.py`` format.

Uses PyNaCl for Ed25519 operations (same library as ``shared.crypto``).
Falls back to unsigned logging if no signing key is available.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

__all__ = ["AuditMiddleware", "AuditEntry"]

logger = logging.getLogger("oas.middleware.audit")

# Optional PyNaCl import — audit still works without signing
try:
    from nacl.signing import SigningKey
    import base64

    _NACL_AVAILABLE = True
except ImportError:
    _NACL_AVAILABLE = False


class AuditEntry:
    """A single audit log entry."""

    def __init__(
        self,
        event: str,
        task_id: str,
        agent_name: str,
        payload_hash: str,
        signature: str | None = None,
        **extra: Any,
    ):
        self.event = event
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.task_id = task_id
        self.agent_name = agent_name
        self.payload_hash = payload_hash
        self.signature = signature
        self.extra = extra

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "event": self.event,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "payload_hash": self.payload_hash,
        }
        if self.signature:
            d["signature"] = self.signature
        d.update(self.extra)
        return d


def _hash_payload(payload: dict[str, Any]) -> str:
    """SHA-256 hash of a JSON-serialised payload."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _sign_hash(digest_hex: str, key_path: Path) -> str | None:
    """Sign a hex digest with an Ed25519 key. Returns None if unavailable."""
    if not _NACL_AVAILABLE:
        return None
    try:
        raw = key_path.read_bytes()
        sk = SigningKey(base64.b64decode(raw))
        signed = sk.sign(bytes.fromhex(digest_hex))
        return signed.signature.hex()
    except Exception as e:
        logger.warning("audit_sign_failed", extra={"error": str(e)})
        return None


class AuditMiddleware:
    """Middleware that logs and signs every task invocation.

    Usage::

        audit = AuditMiddleware(log_dir=Path("~/.darklab/logs"))
        # With optional Ed25519 signing:
        audit = AuditMiddleware(
            log_dir=Path("~/.darklab/logs"),
            signing_key_path=Path("~/.darklab/keys/signing.key"),
        )

        entry = audit.log_task_start(task_id, agent_name, payload)
        # ... agent work ...
        audit.log_task_end(task_id, agent_name, result, status="ok")
    """

    def __init__(
        self,
        log_dir: Path,
        *,
        signing_key_path: Path | None = None,
        log_filename: str = "audit.jsonl",
    ):
        self.log_dir = log_dir
        self._signing_key_path = signing_key_path
        self._log_file = log_dir / log_filename

    def _write_entry(self, entry: AuditEntry) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with open(self._log_file, "a") as f:
            f.write(json.dumps(entry.to_dict(), default=str) + "\n")

    def _sign(self, digest_hex: str) -> str | None:
        if self._signing_key_path and self._signing_key_path.exists():
            return _sign_hash(digest_hex, self._signing_key_path)
        return None

    def log_task_start(
        self,
        task_id: str,
        agent_name: str,
        payload: dict[str, Any],
    ) -> AuditEntry:
        """Log and optionally sign a task start event."""
        payload_hash = _hash_payload(payload)
        signature = self._sign(payload_hash)

        entry = AuditEntry(
            event="task_started",
            task_id=task_id,
            agent_name=agent_name,
            payload_hash=payload_hash,
            signature=signature,
        )
        self._write_entry(entry)
        logger.debug("audit_task_start", extra={"task_id": task_id, "signed": signature is not None})
        return entry

    def log_task_end(
        self,
        task_id: str,
        agent_name: str,
        result: dict[str, Any],
        *,
        status: str = "ok",
        artifact_count: int = 0,
    ) -> AuditEntry:
        """Log and optionally sign a task completion event."""
        result_hash = _hash_payload(result)
        signature = self._sign(result_hash)

        entry = AuditEntry(
            event="task_completed",
            task_id=task_id,
            agent_name=agent_name,
            payload_hash=result_hash,
            signature=signature,
            status=status,
            artifact_count=artifact_count,
        )
        self._write_entry(entry)
        logger.debug("audit_task_end", extra={"task_id": task_id, "status": status})
        return entry

    async def __call__(
        self,
        task_id: str,
        agent_name: str,
        payload: dict[str, Any],
        handler: Callable[..., Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Wrap an async handler with audit logging.

        Logs task start, calls the handler, logs task end (or failure).
        """
        self.log_task_start(task_id, agent_name, payload)
        try:
            result = await handler(payload)
            self.log_task_end(
                task_id, agent_name, result,
                status="ok",
                artifact_count=len(result.get("artifacts", [])),
            )
            return result
        except Exception as e:
            self.log_task_end(
                task_id, agent_name, {"error": str(e)},
                status="error",
            )
            raise
