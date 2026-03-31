"""TurboQuant status command handler.

Implements /turboq-status — shows memory pool status, compression ratios,
and capacity estimates for the TurboQuant KV cache system.
"""
from __future__ import annotations

import logging
from typing import Any

from shared.models import Task, TaskResult
from shared.config import settings

__all__ = ["handle"]

logger = logging.getLogger("darklab.turboq_cmd")


async def handle(task: Task) -> TaskResult:
    """Show TurboQuant memory pool status and capacity estimates.

    Usage: /turboq-status
    """
    try:
        from oas_core.turbo_quant.kv_cache import TurboQuantConfig
        from oas_core.turbo_quant.runtime_adapter import RuntimeAdapter, RuntimeConfig

        tq_config = TurboQuantConfig(
            bits=settings.turbo_quant_bits,
            enable_qjl=settings.turbo_quant_enable_qjl,
        )
        rt_config = RuntimeConfig(
            pool_budget_mb=settings.turbo_quant_pool_mb,
            turbo_quant=tq_config,
        )
        adapter = RuntimeAdapter(rt_config)

        capacity = adapter.estimate_capacity()
        pool_stats = adapter.pool_stats.to_dict()

        return TaskResult(
            task_id=task.task_id,
            agent_name="turboq",
            status="ok",
            result={
                "turbo_quant_enabled": settings.turbo_quant_enabled,
                "compression_bits": settings.turbo_quant_bits,
                "qjl_enabled": settings.turbo_quant_enable_qjl,
                "middle_out_enabled": settings.turbo_quant_middle_out,
                "capacity": capacity,
                "pool": pool_stats,
            },
        )
    except Exception as exc:
        return TaskResult(
            task_id=task.task_id,
            agent_name="turboq",
            status="ok",
            result={
                "turbo_quant_enabled": settings.turbo_quant_enabled,
                "error": str(exc),
            },
        )
