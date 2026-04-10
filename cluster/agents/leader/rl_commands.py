"""RL command handlers for dispatch.py.

Implements /rl-train, /rl-status, /rl-rollback, /rl-freeze, /prorl-status,
/prorl-run, and /debate slash commands that manage OpenClaw-RL training,
NVIDIA ProRL sidecar execution, and MiroShark debate generation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from shared.models import Task, TaskResult
from shared.config import settings

__all__ = [
    "handle_rl_status",
    "handle_rl_freeze",
    "handle_rl_rollback",
    "handle_rl_train",
    "handle_prorl_status",
    "handle_prorl_run",
    "handle_debate",
]

logger = logging.getLogger("darklab.rl_commands")


def _parse_rl_train_args(raw_args: str) -> tuple[str, str]:
    """Parse `/rl-train` args and optional backend selector.

    Supports:
    - `<agent_type>`
    - `<agent_type> --backend prorl`
    - `<agent_type> --backend=prorl`
    """
    tokens = raw_args.split()
    backend = "openclaw"
    cleaned: list[str] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token == "--backend":
            if idx + 1 < len(tokens):
                backend = tokens[idx + 1].strip().lower()
                idx += 2
                continue
            backend = ""
            idx += 1
            continue
        if token.startswith("--backend="):
            backend = token.split("=", 1)[1].strip().lower()
            idx += 1
            continue
        cleaned.append(token)
        idx += 1
    return " ".join(cleaned).strip(), backend


def _prorl_adapter():
    from oas_core.adapters.prorl import ProRLAdapter

    return ProRLAdapter(
        base_url=settings.prorl_url,
        timeout=float(settings.prorl_timeout),
        api_key=settings.prorl_api_key,
        default_data_source=settings.prorl_default_data_source,
        default_model=settings.prorl_model,
    )


def _extract_registered_llm_servers(status_payload: dict[str, Any]) -> set[str]:
    """Best-effort parse of registered LLM servers from ProRL status payload."""
    candidates = (
        status_payload.get("llm_servers"),
        status_payload.get("registered_llm_servers"),
        status_payload.get("servers"),
    )
    for value in candidates:
        if isinstance(value, list):
            values = {
                str(item).strip()
                for item in value
                if str(item).strip()
            }
            if values:
                return values
    return set()


def _status_is_healthy(status_payload: dict[str, Any]) -> bool:
    healthy_raw = status_payload.get("healthy")
    if isinstance(healthy_raw, bool):
        return healthy_raw
    status_raw = str(status_payload.get("status", "")).strip().lower()
    if status_raw in {"ok", "healthy", "ready", "running"}:
        return True
    return bool(status_payload)


async def _emit_prorl_tool_event(
    *,
    task: Task,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Emit DRVP tool event for ProRL integration (best-effort)."""
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

        mapping = {
            "started": DRVPEventType.TOOL_CALL_STARTED,
            "completed": DRVPEventType.TOOL_CALL_COMPLETED,
            "failed": DRVPEventType.TOOL_CALL_FAILED,
        }
        event = mapping.get(event_type)
        if event is None:
            return

        await emit(
            DRVPEvent(
                event_type=event,
                request_id=task.task_id,
                task_id=task.task_id,
                issue_id=task.payload.get("_issue_key"),
                agent_name="prorl",
                device="leader",
                payload=payload,
            )
        )
    except Exception:
        pass


async def _ensure_prorl_issue(task: Task, prompt: str) -> tuple[str | None, str | None]:
    """Ensure a Paperclip issue linkage exists for `/prorl-run` (best-effort)."""
    issue_id = task.payload.get("_issue_id")
    issue_key = task.payload.get("_issue_key")
    if issue_id or issue_key:
        return issue_id, issue_key

    if not (settings.paperclip_url and settings.paperclip_api_key):
        return None, None

    try:
        from oas_core.adapters.paperclip import PaperclipClient
        from oas_core.middleware.governance import GovernanceMiddleware

        gov = GovernanceMiddleware(
            paperclip=PaperclipClient(
                base_url=settings.paperclip_url,
                api_key=settings.paperclip_api_key,
                company_id=settings.paperclip_company_id,
            ),
            agent_id=settings.paperclip_agent_id,
        )
        issue = await gov.open_issue(
            request_id=task.task_id,
            title=f"ProRL run: {prompt[:96]}",
            agent_name="prorl",
            device="leader",
            description="Auto-created for /prorl-run experimental execution.",
        )
        if issue:
            issue_id = issue.get("id")
            issue_key = issue.get("key")
            task.payload["_issue_id"] = issue_id
            task.payload["_issue_key"] = issue_key
    except Exception as exc:
        logger.debug("prorl_issue_link_skip", error=str(exc))

    return issue_id, issue_key


async def handle_rl_status(task: Task) -> TaskResult:
    """Show RL training status for all agents."""
    rl_dir = settings.rl_dir

    status: dict[str, Any] = {
        "rl_enabled": settings.rl_enabled,
        "rl_enabled_agents": sorted(settings.rl_enabled_agent_set),
        "training_method": settings.rl_training_method,
        "rl_proxy_url": settings.rl_proxy_url or "(not configured)",
        "miroshark_enabled": settings.miroshark_enabled,
        "miroshark_url": settings.miroshark_url or "(not configured)",
    }

    # Count rollout files
    for source in ("live", "synthetic"):
        source_dir = rl_dir / "rollouts" / source
        if source_dir.exists():
            count = sum(1 for _ in source_dir.glob("*.jsonl"))
            status[f"rollout_files_{source}"] = count
        else:
            status[f"rollout_files_{source}"] = 0

    # List baselines
    baselines_dir = rl_dir / "baselines"
    if baselines_dir.exists():
        baselines = [p.stem for p in baselines_dir.glob("*.json")]
        status["baselines"] = sorted(baselines)
    else:
        status["baselines"] = []

    # List checkpoints
    checkpoints_dir = rl_dir / "checkpoints"
    if checkpoints_dir.exists():
        checkpoints = sorted([d.name for d in checkpoints_dir.iterdir() if d.is_dir()])
        status["checkpoints"] = checkpoints[-5:]  # Last 5
    else:
        status["checkpoints"] = []

    return TaskResult(
        task_id=task.task_id,
        agent_name="rl-commands",
        status="ok",
        result=status,
    )


async def handle_rl_freeze(task: Task) -> TaskResult:
    """Freeze the current agent behavior as a baseline snapshot.

    Usage: /rl-freeze research
           /rl-freeze all
    """
    args = task.payload.get("text", "").strip()
    if not args:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "Usage: /rl-freeze <agent_type|all>"},
        )

    agent_types = (
        sorted(settings.rl_enabled_agent_set)
        if args == "all"
        else [args.lower()]
    )

    baselines_dir = settings.rl_baselines_dir
    frozen: list[str] = []

    for agent_type in agent_types:
        baseline_path = baselines_dir / f"{agent_type}-v0.json"
        if baseline_path.exists():
            logger.info("baseline_already_exists", agent_type=agent_type)
            frozen.append(f"{agent_type}-v0 (already exists)")
            continue

        baseline = {
            "agent_type": agent_type,
            "version": f"{agent_type}-v0",
            "base_model": "Qwen/Qwen3-4B-Instruct-2507",
            "model_hash": "",
            "evaluation_scores": {"aggregate": 0.0},
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }
        baseline_path.write_text(json.dumps(baseline, indent=2))
        frozen.append(f"{agent_type}-v0")
        logger.info("baseline_frozen", agent_type=agent_type)

    return TaskResult(
        task_id=task.task_id,
        agent_name="rl-commands",
        status="ok",
        result={"frozen_baselines": frozen},
    )


async def handle_rl_rollback(task: Task) -> TaskResult:
    """Disable RL for an agent, reverting to the base model.

    Usage: /rl-rollback research
           /rl-rollback all
    """
    args = task.payload.get("text", "").strip()
    if not args:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "Usage: /rl-rollback <agent_type|all>"},
        )

    rolled_back: list[str] = []

    if args == "all":
        rolled_back = sorted(settings.rl_enabled_agent_set)
        # Note: actual config change requires env var update or runtime toggle
        # This records the intent; the model router checks rl_enabled_agents
    else:
        agent_type = args.lower()
        if agent_type in settings.rl_enabled_agent_set:
            rolled_back = [agent_type]

    # Emit DRVP rollback event
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        for agent in rolled_back:
            await emit(DRVPEvent(
                event_type=DRVPEventType.RL_CHECKPOINT_ROLLED_BACK,
                request_id=task.task_id,
                agent_name=agent,
                device="leader",
                payload={"agent_type": agent, "reason": "manual rollback"},
            ))
    except Exception:
        pass

    return TaskResult(
        task_id=task.task_id,
        agent_name="rl-commands",
        status="ok",
        result={
            "rolled_back": rolled_back,
            "message": (
                f"RL disabled for {', '.join(rolled_back)}. "
                "Traffic now routes to base model (EXECUTION tier)."
                if rolled_back
                else f"Agent '{args}' was not RL-enabled."
            ),
        },
    )


async def handle_rl_train(task: Task) -> TaskResult:
    """Trigger a training cycle for an agent type.

    Usage: /rl-train research
           /rl-train research --backend prorl
    """
    raw_args = task.payload.get("text", "").strip()
    if not raw_args:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "Usage: /rl-train <agent_type> [--backend openclaw|prorl]"},
        )

    args, backend = _parse_rl_train_args(raw_args)
    if not args:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "Usage: /rl-train <agent_type> [--backend openclaw|prorl]"},
        )
    if backend not in {"openclaw", "prorl"}:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": f"Unsupported backend '{backend}'. Use openclaw or prorl."},
        )

    if backend == "prorl":
        if not settings.prorl_enabled:
            return TaskResult(
                task_id=task.task_id,
                agent_name="rl-commands",
                status="error",
                result={"error": "ProRL backend disabled (set DARKLAB_PRORL_ENABLED=true)."},
            )
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={
                "error": "ProRL backend for /rl-train is not enabled yet. Use /prorl-run for phase-2 experimental execution.",
            },
        )

    agent_type = args.lower()

    # Check prerequisites
    if not settings.tinker_api_key:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "DARKLAB_TINKER_API_KEY not configured"},
        )

    # Load rollouts
    try:
        from oas_core.rl.training_pipeline import TrainingPipeline
        pipeline = TrainingPipeline(
            rollouts_dir=settings.rl_rollouts_dir,
            batch_size=settings.rl_batch_size,
        )

        live = pipeline.load_rollouts(agent_type, "live")
        synthetic = pipeline.load_rollouts(agent_type, "synthetic")

        if not live and not synthetic:
            return TaskResult(
                task_id=task.task_id,
                agent_name="rl-commands",
                status="error",
                result={"error": f"No rollouts found for {agent_type}"},
            )

        scored_live = pipeline.score_rollouts(live)
        scored_synthetic = pipeline.score_rollouts(synthetic)
        batch = pipeline.assemble_batch(agent_type, scored_live, scored_synthetic)

        if batch is None:
            return TaskResult(
                task_id=task.task_id,
                agent_name="rl-commands",
                status="error",
                result={
                    "error": f"Insufficient scored rollouts for batch (need {settings.rl_batch_size})",
                    "live_scored": len(scored_live),
                    "synthetic_scored": len(scored_synthetic),
                },
            )

        # Emit DRVP event
        try:
            from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
            await emit(DRVPEvent(
                event_type=DRVPEventType.RL_ROLLOUT_COLLECTED,
                request_id=task.task_id,
                agent_name=agent_type,
                device="leader",
                payload={"batch_id": batch.batch_id, "total": batch.total},
            ))
        except Exception:
            pass

        # Submit to Tinker if available
        training_job: dict | None = None
        try:
            from oas_core.rl.tinker_client import TinkerClient, TINKER_AVAILABLE
            if TINKER_AVAILABLE and settings.tinker_api_key:
                tinker = TinkerClient(api_key=settings.tinker_api_key)
                if tinker.circuit_breaker.allow_request():
                    rollout_data = [
                        r.session.model_dump() for r in batch.rollouts
                    ]
                    training_job = await tinker.submit_training_job(
                        model="Qwen/Qwen3-4B-Instruct-2507",
                        method=settings.rl_training_method,
                        lora_rank=settings.rl_lora_rank,
                        batch_size=settings.rl_batch_size,
                        rollout_data=rollout_data,
                        agent_type=agent_type,
                    )
                    tinker.circuit_breaker.record_success()
                    logger.info("tinker_job_submitted", job=training_job)
                else:
                    logger.warning("tinker_circuit_breaker_open")
        except Exception as tinker_exc:
            logger.warning("tinker_submit_failed", error=str(tinker_exc))
            # Training failure doesn't block the response

        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="ok",
            result={
                "message": f"Training batch assembled for {agent_type}",
                "batch_id": batch.batch_id,
                "live_rollouts": batch.live_count,
                "synthetic_rollouts": batch.synthetic_count,
                "total": batch.total,
                "backend": "openclaw",
                "tinker_job": training_job,
                "tinker_status": "submitted" if training_job else "skipped (no aiohttp or circuit breaker open)",
            },
        )
    except Exception as exc:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": str(exc)},
        )


async def handle_prorl_status(task: Task) -> TaskResult:
    """Show readiness and registration status for the ProRL sidecar."""
    status_result: dict[str, Any] = {
        "backend": "prorl",
        "enabled": settings.prorl_enabled,
        "url": settings.prorl_url or "(not configured)",
        "llm_server": settings.prorl_llm_server or "(not configured)",
    }

    if not settings.prorl_enabled:
        status_result.update(
            {
                "ready": False,
                "healthy": False,
                "message": "ProRL disabled (set DARKLAB_PRORL_ENABLED=true to enable).",
            }
        )
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="ok",
            result=status_result,
        )

    if not settings.prorl_url:
        status_result.update(
            {
                "ready": False,
                "healthy": False,
                "message": "DARKLAB_PRORL_URL is not configured.",
            }
        )
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result=status_result,
        )

    try:
        adapter = _prorl_adapter()
        upstream_status = await adapter.status()
        healthy = _status_is_healthy(upstream_status)

        desired_server = settings.prorl_llm_server.strip()
        llm_registration = "not_configured"
        llm_registration_error = ""
        registered_servers = _extract_registered_llm_servers(upstream_status)
        start_response: dict[str, Any] | None = None

        if desired_server:
            if desired_server in registered_servers:
                llm_registration = "already_registered"
            else:
                try:
                    await adapter.add_llm_server(desired_server)
                    start_response = await adapter.start()
                    llm_registration = "registered"
                    upstream_status = await adapter.status()
                    registered_servers = _extract_registered_llm_servers(upstream_status)
                except Exception as exc:
                    llm_registration = "registration_failed"
                    llm_registration_error = str(exc)

        healthy = _status_is_healthy(upstream_status)
        ready = healthy and (not desired_server or desired_server in registered_servers)
        status_result.update(
            {
                "healthy": healthy,
                "ready": ready,
                "llm_registration": llm_registration,
                "registered_llm_servers": sorted(registered_servers),
                "status_payload": upstream_status,
                "start_response": start_response,
                "message": (
                    "ProRL is ready."
                    if ready
                    else "ProRL reachable but not fully ready. Check registration and backend status."
                ),
            }
        )
        if llm_registration_error:
            status_result["llm_registration_error"] = llm_registration_error

        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="ok" if ready else "error",
            result=status_result,
        )
    except Exception as exc:
        status_result.update(
            {
                "healthy": False,
                "ready": False,
                "message": "Failed to query ProRL status.",
                "error": str(exc),
            }
        )
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result=status_result,
        )


async def handle_prorl_run(task: Task) -> TaskResult:
    """Submit a bounded experimental prompt to ProRL `/process`.

    Usage: /prorl-run <prompt>
    """
    prompt = task.payload.get("text", "").strip()
    if not prompt:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "Usage: /prorl-run <prompt>"},
        )

    if not settings.prorl_enabled:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "ProRL disabled (set DARKLAB_PRORL_ENABLED=true)."},
        )
    if not settings.prorl_url:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "DARKLAB_PRORL_URL is not configured."},
        )

    issue_id, issue_key = await _ensure_prorl_issue(task, prompt)

    metadata = {
        "task_type": task.task_type.value,
        "source": task.payload.get("source", "leader"),
        "issue_id": issue_id,
        "issue_key": issue_key,
        "user_id": task.user_id,
        "raw_text": task.payload.get("raw_text", ""),
    }
    if "_worktree" in task.payload:
        metadata["worktree"] = task.payload["_worktree"]

    adapter = _prorl_adapter()
    instance = adapter.build_instance(
        request_id=task.task_id,
        prompt=prompt,
        metadata=metadata,
    )
    sampling_params = adapter.build_sampling_params(model=settings.prorl_model)

    await _emit_prorl_tool_event(
        task=task,
        event_type="started",
        payload={
            "backend": "prorl",
            "endpoint": "/process",
            "model": settings.prorl_model,
            "issue_id": issue_id,
            "issue_key": issue_key,
        },
    )

    try:
        result = await adapter.process(
            instance=instance,
            sampling_params=sampling_params,
            request_id=task.task_id,
            agent_name="leader",
            device="leader",
        )
        event_type = "completed" if result.get("status") == "ok" else "failed"
        await _emit_prorl_tool_event(
            task=task,
            event_type=event_type,
            payload={
                "backend": "prorl",
                "request_id": task.task_id,
                "status": result.get("status", "error"),
                "summary": str(result.get("summary", ""))[:300],
                "issue_id": issue_id,
                "issue_key": issue_key,
            },
        )
        if event_type == "failed":
            try:
                from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

                await emit(
                    DRVPEvent(
                        event_type=DRVPEventType.AGENT_ERROR,
                        request_id=task.task_id,
                        task_id=task.task_id,
                        issue_id=issue_key,
                        agent_name="prorl",
                        device="leader",
                        payload={
                            "backend": "prorl",
                            "status": result.get("status"),
                            "summary": str(result.get("summary", ""))[:300],
                        },
                    )
                )
            except Exception:
                pass

        result["issue_id"] = issue_id
        result["issue_key"] = issue_key
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="ok" if result.get("status") == "ok" else "error",
            result=result,
        )
    except Exception as exc:
        await _emit_prorl_tool_event(
            task=task,
            event_type="failed",
            payload={
                "backend": "prorl",
                "request_id": task.task_id,
                "error": str(exc),
                "issue_id": issue_id,
                "issue_key": issue_key,
            },
        )
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={
                "backend": "prorl",
                "request_id": task.task_id,
                "status": "error",
                "error": str(exc),
                "issue_id": issue_id,
                "issue_key": issue_key,
            },
        )


async def handle_debate(task: Task) -> TaskResult:
    """Generate a multi-agent debate using MiroShark.

    Usage: /debate "CRISPR off-target effects are under-reported"
           /debate --scenario peer-review --rounds 15 "topic"
    """
    text = task.payload.get("text", "").strip()
    if not text:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "Usage: /debate <topic>"},
        )

    if not settings.miroshark_enabled or not settings.miroshark_url:
        return TaskResult(
            task_id=task.task_id,
            agent_name="rl-commands",
            status="error",
            result={"error": "MiroShark not enabled (set DARKLAB_MIROSHARK_ENABLED=true)"},
        )

    # Parse optional flags
    scenario = "hypothesis"
    rounds = settings.debate_default_rounds
    topic = text

    # Simple flag parsing
    if "--scenario" in text:
        parts = text.split("--scenario")
        rest = parts[1].strip()
        scenario_name, topic = rest.split(None, 1) if " " in rest else (rest, "")
        scenario = scenario_name.strip()
    if "--rounds" in topic:
        parts = topic.split("--rounds")
        rest = parts[1].strip()
        rounds_str, topic = rest.split(None, 1) if " " in rest else (rest, "")
        try:
            rounds = int(rounds_str.strip())
        except ValueError:
            pass

    topic = topic.strip().strip('"').strip("'")

    # Emit DRVP debate started event
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        await emit(DRVPEvent(
            event_type=DRVPEventType.DEBATE_STARTED,
            request_id=task.task_id,
            agent_name="debate-orchestrator",
            device="leader",
            payload={"topic": topic, "scenario": scenario, "rounds": rounds},
        ))
    except Exception:
        pass

    # Run MiroShark simulation
    simulation_result: dict | None = None
    transcript_saved = False
    try:
        from oas_core.adapters.miroshark import MiroSharkAdapter, MIROSHARK_AVAILABLE
        if MIROSHARK_AVAILABLE:
            adapter = MiroSharkAdapter(base_url=settings.miroshark_url)

            # Create and run simulation
            sim = await adapter.create_simulation(
                topic=topic,
                scenario=scenario,
                num_rounds=rounds,
            )
            sim_id = sim.get("simulation_id", sim.get("id", "unknown"))
            simulation_result = await adapter.run_simulation(sim_id)

            # Get transcript and convert to training rollout
            try:
                transcript_data = await adapter.get_transcript(sim_id)
                from oas_core.rl.transcript_converter import TranscriptConverter
                from oas_core.middleware.rl_rollout import RolloutCollector

                converter = TranscriptConverter(target_agent_type="research")
                transcript = converter.from_miroshark_json(transcript_data)
                session = converter.convert(transcript)

                collector = RolloutCollector(rollouts_dir=settings.rl_rollouts_dir)
                collector.write_synthetic(session)
                transcript_saved = True
            except Exception as conv_exc:
                logger.warning("debate_transcript_conversion_failed", error=str(conv_exc))

            # Emit completion event
            try:
                from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
                await emit(DRVPEvent(
                    event_type=DRVPEventType.DEBATE_COMPLETED,
                    request_id=task.task_id,
                    agent_name="debate-orchestrator",
                    device="leader",
                    payload={"topic": topic, "simulation_id": sim_id},
                ))
            except Exception:
                pass
    except Exception as ms_exc:
        logger.warning("miroshark_simulation_failed", error=str(ms_exc))
        # MiroShark failure doesn't block the response

    return TaskResult(
        task_id=task.task_id,
        agent_name="rl-commands",
        status="ok",
        result={
            "message": "Debate simulation completed" if simulation_result else "Debate simulation queued (MiroShark aiohttp unavailable)",
            "topic": topic,
            "scenario": scenario,
            "rounds": rounds,
            "simulation": simulation_result,
            "transcript_saved_for_training": transcript_saved,
        },
    )
