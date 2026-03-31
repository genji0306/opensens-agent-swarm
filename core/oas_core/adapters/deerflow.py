"""DeerFlow adapter for OAS — wraps DeerFlowClient with DRVP event emission.

Provides an async interface that bridges the embedded DeerFlow research harness
into the OAS middleware pipeline. The adapter:

- Initialises a ``DeerFlowClient`` with config from ``~/.darklab/deerflow/``
- Emits DRVP events (agent lifecycle, LLM boost) during execution
- Supports model selection via the OAS tiered model router
- Handles file uploads and artifact collection

DeerFlow is an optional dependency.  All imports are guarded behind
``DEERFLOW_AVAILABLE`` so the rest of OAS keeps working without it.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

__all__ = [
    "DeerFlowAdapter",
    "DEERFLOW_AVAILABLE",
    "DEFAULT_CONFIG_PATH",
]

logger = logging.getLogger("oas.adapters.deerflow")

# --- Import guard ---
try:
    from deerflow.client import DeerFlowClient  # type: ignore[import-untyped]

    DEERFLOW_AVAILABLE = True
except ImportError:
    DEERFLOW_AVAILABLE = False

DEFAULT_CONFIG_PATH = Path.home() / ".darklab" / "deerflow" / "config.yaml"


class DeerFlowAdapter:
    """Bridges DeerFlow's embedded client into the OAS dispatch pipeline.

    Parameters
    ----------
    config_path:
        Path to DeerFlow's ``config.yaml``.  Defaults to
        ``~/.darklab/deerflow/config.yaml``.
    model_name:
        Override the default model defined in ``config.yaml``.
    thinking_enabled:
        Enable extended thinking (trades cost for quality).
    subagent_enabled:
        Allow DeerFlow to spawn background sub-agents.
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        model_name: str | None = None,
        thinking_enabled: bool = True,
        subagent_enabled: bool = True,
    ):
        if not DEERFLOW_AVAILABLE:
            raise ImportError(
                "deerflow-harness is not installed. "
                "Install with: uv pip install -e ./frameworks/deer-flow-main/backend/packages/harness"
            )
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._model_name = model_name
        self._thinking_enabled = thinking_enabled
        self._subagent_enabled = subagent_enabled
        self._client: Any = None  # Lazy DeerFlowClient

    def _get_client(self) -> Any:
        """Lazily initialise the DeerFlowClient."""
        if self._client is None:
            self._client = DeerFlowClient(
                config_path=str(self._config_path),
                model_name=self._model_name,
                thinking_enabled=self._thinking_enabled,
                subagent_enabled=self._subagent_enabled,
                plan_mode=False,
            )
            logger.info(
                "deerflow_client_init",
                config=str(self._config_path),
                model=self._model_name,
            )
        return self._client

    async def run_research(
        self,
        request_id: str,
        query: str,
        *,
        agent_name: str = "deerflow",
        device: str = "leader",
        thread_id: str | None = None,
        files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a DeerFlow research task with DRVP event emission.

        Parameters
        ----------
        request_id:
            OAS request identifier (used for DRVP event grouping).
        query:
            The research question or objective.
        agent_name:
            Agent name for DRVP events.
        device:
            Device name for DRVP events.
        thread_id:
            DeerFlow thread for multi-turn context.  Defaults to *request_id*.
        files:
            Local file paths to upload before executing.

        Returns
        -------
        dict with keys ``output``, ``thread_id``, ``artifacts``.
        """
        client = self._get_client()
        thread_id = thread_id or request_id

        # Upload files if provided
        if files:
            try:
                client.upload_files(thread_id, files)
                logger.debug("deerflow_files_uploaded", count=len(files), thread=thread_id)
            except Exception as exc:
                logger.warning("deerflow_upload_failed", error=str(exc))

        # Emit activation event
        await self._emit_event(
            "agent.activated",
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"query": query[:200], "thread_id": thread_id},
        )

        # Prefix query to prevent clarification tool calls in autonomous mode
        autonomous_query = (
            "IMPORTANT: Do NOT ask for clarification. Proceed directly with "
            "the research using your best judgment. Produce a comprehensive "
            "answer.\n\n" + query
        )

        # Stream response in a thread (DeerFlowClient.stream is synchronous)
        # DeerFlow agents produce tool calls (web_search, task) and tool results.
        # The final answer may be: (a) the last AI message without tool_calls,
        # or (b) synthesised from the last few messages' content.
        # We keep the last non-empty AI content OR fall back to the last
        # `end` event's accumulated artifacts.
        final_output: list[str] = []
        all_ai_contents: list[str] = []
        step_count = 0

        def _run_stream() -> None:
            nonlocal step_count
            for event in client.stream(autonomous_query, thread_id=thread_id):
                if event.type == "values":
                    msgs = event.data.get("messages", [])
                    for m in reversed(msgs):
                        if not isinstance(m, dict):
                            continue
                        mtype = m.get("type", "")
                        content = str(m.get("content", "")).strip()
                        if not content:
                            continue
                        has_tool_calls = bool(m.get("tool_calls"))

                        if mtype == "ai" and not has_tool_calls:
                            # Real AI prose — best candidate
                            final_output.clear()
                            final_output.append(content)
                            step_count += 1
                            break
                        elif mtype == "ai" and content:
                            # AI with tool_calls — track content anyway
                            all_ai_contents.append(content)
                            break
                        elif mtype == "tool" and content:
                            # Tool result — may contain useful research
                            all_ai_contents.append(content)
                            break

        try:
            await asyncio.to_thread(_run_stream)
        except Exception as exc:
            await self._emit_event(
                "agent.error",
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={"error": str(exc)},
            )
            raise

        # Prefer clean AI prose; fall back to last accumulated content
        if final_output:
            result_text = "\n".join(final_output)
        elif all_ai_contents:
            # Use the last substantial content (tool results, partial answers)
            result_text = all_ai_contents[-1]
        else:
            result_text = ""

        # Collect artifacts from the thread
        artifacts: list[str] = []
        try:
            uploads = client.list_uploads(thread_id)
            if uploads and isinstance(uploads, dict):
                artifacts = [f.get("name", "") for f in uploads.get("files", [])]
        except Exception:
            pass  # Artifacts are best-effort

        # Emit completion event
        await self._emit_event(
            "agent.idle",
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={
                "output_length": len(result_text),
                "steps": step_count,
                "artifacts_count": len(artifacts),
            },
        )

        return {
            "output": result_text,
            "thread_id": thread_id,
            "artifacts": artifacts,
        }

    # --- Convenience wrappers ---

    def list_models(self) -> dict[str, Any]:
        """List models configured in DeerFlow."""
        return self._get_client().list_models()

    def list_skills(self) -> dict[str, Any]:
        """List skills available in DeerFlow."""
        return self._get_client().list_skills()

    def get_memory_status(self) -> dict[str, Any]:
        """Get DeerFlow memory status."""
        return self._get_client().get_memory_status()

    def reset(self) -> None:
        """Force-recreate the DeerFlow client (after config changes)."""
        if self._client is not None:
            try:
                self._client.reset_agent()
            except Exception:
                pass
        self._client = None
        logger.info("deerflow_client_reset")

    # --- DRVP event helpers ---

    @staticmethod
    async def _emit_event(
        event_type_str: str,
        *,
        request_id: str,
        agent_name: str,
        device: str,
        payload: dict[str, Any],
    ) -> None:
        """Emit a DRVP event (best-effort, never raises)."""
        try:
            from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

            et = DRVPEventType(event_type_str)
            await emit(
                DRVPEvent(
                    event_type=et,
                    request_id=request_id,
                    agent_name=agent_name,
                    device=device,
                    payload=payload,
                )
            )
        except Exception:
            pass  # DRVP is best-effort
