"""Structured logging setup for DarkLab agents.

Call ``setup_logging()`` once at process startup (serve.py main, node_bridge.run_agent).
All modules then use ``structlog.get_logger()`` which auto-binds to the configured pipeline.
Existing ``logging.getLogger("darklab.X")`` calls continue to produce structured JSON via
the ProcessorFormatter bridge.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

try:
    import structlog
except ImportError:  # pragma: no cover - exercised in minimal test envs
    structlog = None  # type: ignore[assignment]

# Context variable for request-scoped tracing
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_configured = False


def _add_request_id(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict,
) -> dict:
    rid = request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def _add_agent_role(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict,
) -> dict:
    try:
        from shared.config import settings
        event_dict.setdefault("role", settings.darklab_role)
    except Exception:
        pass
    return event_dict


def setup_logging(*, json_output: bool = True, level: str | None = None) -> None:
    """Configure structlog + stdlib logging integration.

    Safe to call multiple times (idempotent).
    """
    global _configured
    if _configured:
        return
    _configured = True

    if level is None:
        try:
            from shared.config import settings
            level = settings.log_level
        except Exception:
            level = "INFO"

    log_level = getattr(logging, level.upper(), logging.INFO)

    if structlog is None:
        logging.basicConfig(
            level=log_level,
            stream=sys.stderr,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            force=True,
        )
        for name in ("httpx", "httpcore", "uvicorn.access"):
            logging.getLogger(name).setLevel(logging.WARNING)
        return

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_request_id,
            _add_agent_role,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)
