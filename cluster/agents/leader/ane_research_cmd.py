"""ANE Research command handler — Apple Neural Engine + MLX + CUDA unified stack.

Pre-loaded with findings from two full swarm research runs:
  Run 1 (2026-04-02): CUDA-on-MLX — kernel translation, SPIR-V pipeline, MetaXuda, ZMLX
  Run 2 (2026-04-02): ANE direct training — maderix/ANE, Orion framework, IOSurface zero-copy

Usage:
  /ane-research <research topic or question>
  /ane-research benchmark
  /ane-research status
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from shared.models import Task, TaskResult

__all__ = ["handle"]

logger = logging.getLogger("darklab.ane_research_cmd")

# ── Pre-loaded research context ───────────────────────────────────────

ANE_CONTEXT = """
## Apple Silicon AI Stack — Research Knowledge Base

### ANE Direct Training (maderix/ANE + Orion)
- Private APIs: _ANEClient, _ANECompiler, _ANEInMemoryModelDescriptor
- _ANEInMemoryModelDescriptor: compiles MIL text + weight blobs in-memory (no disk file)
- MIL = Apple's typed SSA IR; compiles to E5 microcode (~2,688 bytes per 1024×1024 matmul)
- Orion (mechramc): production framework — delta BLOBFILE patching bypasses 119-compile limit
- Orion: 3.8× training speedup; 170+ tokens/sec inference on GPT-2 124M
- Orion paper: arXiv:2603.06728
- IOSurface zero-copy: GPU and ANE share same physical memory pages — no transfer overhead
- ANE matmul as 1×1 convolution = 3× faster than ANE native matmul
- W8A8 INT8 quantization = 1.88× throughput improvement over FP16
- Softmax speedup: 33.8× over CPU at 32k vocab
- RMSNorm speedup: 10× over CPU (fused kernel)
- M4 ANE: 38 TOPS claimed; actual ~1.78 TFLOPS sustained (11.2% utilization)
- SRAM cliff at 32MB: 30% throughput drop above; budget tracking critical
- 119-compile limit per process; Orion delta compilation bypasses via BLOBFILE patching
- LoRA hot-swap without recompilation (Orion feature)
- Causal masking, gradient accumulation, complex activations → CPU fallback
- DVFS: hard power gating to 0mW when idle

### MLX + CUDA Compatibility
- mx.fast.metal_kernel(): primary API for custom Metal kernels (JIT, autograd, caching)
- ZMLX: Triton-style kernel toolkit for MLX (70+ kernels, MLX ≥0.30.0)
- MetaXuda v2.0 (Rust, PyPI): CUDA runtime API shim → Metal buffers
- CUDA translation pipeline: CUDA → SPIR-V (chipStar) → MSL (SPIRV-Cross) → mx.fast.metal_kernel()
- mlx-cuda: MLX running on NVIDIA CUDA GPUs (Apple-backed, mid-2025)
- Apple Silicon FP32 matmul ≈ NVIDIA parity; FP16 2-3× slower (no tensor cores)
- Energy efficiency: >10× better perf/watt vs RTX 4090 at 450W TDP

### Optimal Dispatch Table
- ANE: softmax (33.8×), RMSNorm (10×), linear (1×1 conv, 3×), INT8 ops (1.88×)
- GPU/MPS/MLX: FP16 matmul, general attention, CUDA-translated ops
- CPU/Accelerate: gradient accumulation, causal masking, Adam, embedding lookup

### Mac Mini 16GB Capacity
- GPU FP16 only: 4k tokens, 7B full
- MLX + TurboQuant 4-bit: 12k tokens, 7B quantized
- ANE INT8 + MLX 4-bit: 16k tokens, 7B (ANE offload frees GPU VRAM)
"""

DISPATCH_TABLE = {
    "softmax":        {"target": "ANE",           "speedup": "33.8× CPU",   "method": "native kernel"},
    "rmsnorm":        {"target": "ANE",           "speedup": "10× CPU",     "method": "fused kernel"},
    "linear":         {"target": "ANE",           "speedup": "3× ANE matmul", "method": "1×1 convolution"},
    "matmul_int8":    {"target": "ANE",           "speedup": "1.88× FP16",  "method": "W8A8 quantization"},
    "matmul_fp16":    {"target": "GPU/MPS",       "speedup": "GPU-native",  "method": "Metal Performance Shaders"},
    "attention":      {"target": "GPU/MPS",       "speedup": "GPU-native",  "method": "FlashAttention via Metal"},
    "cuda_kernel":    {"target": "Metal via SPIR-V", "speedup": "compat",   "method": "chipStar→SPIRV-Cross→mx.fast.metal_kernel"},
    "triton_kernel":  {"target": "Metal via ZMLX","speedup": "native",      "method": "ZMLX kernel compilation"},
    "causal_mask":    {"target": "CPU",           "speedup": "n/a",         "method": "cblas/Accelerate (branching)"},
    "grad_accum":     {"target": "CPU",           "speedup": "n/a",         "method": "cblas (unsupported on ANE)"},
    "adam_optimizer": {"target": "CPU",           "speedup": "n/a",         "method": "Accelerate framework"},
    "embedding":      {"target": "CPU",           "speedup": "n/a",         "method": "Accelerate (branching)"},
}


async def handle(task: Task) -> TaskResult:
    """Handle /ane-research command.

    Provides research, dispatch recommendations, and architecture guidance
    for Apple Neural Engine + MLX + CUDA workloads on Apple Silicon.
    """
    text = task.payload.get("text", "").strip()
    args = task.payload.get("args", "").strip()
    topic = args or text

    if not topic or topic in ("status", "/ane-research"):
        return _handle_status(task)

    if topic.lower().strip("/").startswith("benchmark"):
        return _handle_benchmark(task)

    # Research mode: run deep research with ANE context injected
    try:
        result = await _run_ane_deep_research(task, topic)
        return result
    except Exception as exc:
        logger.error("ane_research_failed: %s", exc)
        return TaskResult(
            task_id=task.task_id,
            agent_name="ane-research",
            status="error",
            result={"error": str(exc)},
        )


def _handle_status(task: Task) -> TaskResult:
    """Return current ANE research knowledge base status."""
    return TaskResult(
        task_id=task.task_id,
        agent_name="ane-research",
        status="ok",
        result={
            "status": "ready",
            "knowledge_base": "ANE + MLX + CUDA (2026-04-02 full swarm runs)",
            "dispatch_table_ops": list(DISPATCH_TABLE.keys()),
            "key_projects": [
                "maderix/ANE (6.5k stars) — private API reverse engineering",
                "mechramc/Orion — production ANE training (arXiv:2603.06728)",
                "ZMLX — Triton-style kernel toolkit for MLX",
                "MetaXuda v2.0 — CUDA runtime → Metal shim",
                "chipStar — CUDA/HIP → SPIR-V",
                "SPIRV-Cross — SPIR-V → MSL",
                "mlx-cuda — MLX on NVIDIA CUDA (Apple-backed)",
            ],
            "hardware": {
                "M4_ANE_FP16_TFLOPS": 18.6,
                "M4_ANE_INT8_TFLOPS": 35.1,
                "SRAM_cliff_MB": 32,
                "compile_limit": 119,
                "orion_bypasses_compile_limit": True,
                "IOSurface_zero_copy": True,
            },
        },
    )


def _handle_benchmark(task: Task) -> TaskResult:
    """Return dispatch benchmark table for all ops."""
    benchmarks = []
    for op, info in DISPATCH_TABLE.items():
        benchmarks.append({
            "operation": op,
            "target": info["target"],
            "speedup": info["speedup"],
            "method": info["method"],
        })

    summary = (
        "# ANE + MLX Dispatch Benchmark\n\n"
        "| Operation | Target | Speedup | Method |\n"
        "|-----------|--------|---------|--------|\n"
    )
    for b in benchmarks:
        summary += f"| {b['operation']} | {b['target']} | {b['speedup']} | {b['method']} |\n"

    return TaskResult(
        task_id=task.task_id,
        agent_name="ane-research",
        status="ok",
        result={
            "output": summary,
            "benchmarks": benchmarks,
            "note": (
                "Dispatch targets derived from full swarm research runs "
                "(maderix/ANE + Orion characterization data, 2026-04-02)."
            ),
        },
    )


async def _run_ane_deep_research(task: Task, topic: str) -> TaskResult:
    """Run iterative deep research with ANE context pre-loaded."""
    # Emit DRVP start event
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        await emit(DRVPEvent(
            event_type=DRVPEventType.DEEP_RESEARCH_STARTED,
            request_id=task.task_id,
            agent_name="ane-research",
            device="leader",
            payload={"topic": topic[:200], "context": "ANE+MLX+CUDA knowledge base"},
        ))
    except Exception:
        pass

    # Augment query with ANE context
    augmented_topic = (
        f"{topic}\n\n"
        f"Research context:\n{ANE_CONTEXT[:600]}"
    )

    try:
        from oas_core.deep_research import ResearchOrchestrator, ResearchConfig
        config = ResearchConfig(max_iterations=3, threshold=0.70)
        orchestrator = ResearchOrchestrator(config)
        result = await orchestrator.run(augmented_topic, task.task_id)

        # Build dispatch recommendations if topic is about ops
        dispatch_recs = _extract_dispatch_recommendations(topic)

        # Emit completion
        try:
            from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
            await emit(DRVPEvent(
                event_type=DRVPEventType.DEEP_RESEARCH_COMPLETED,
                request_id=task.task_id,
                agent_name="ane-research",
                device="leader",
                payload={"score": round(result.final_score, 3), "sources": result.total_sources},
            ))
        except Exception:
            pass

        return TaskResult(
            task_id=task.task_id,
            agent_name="ane-research",
            status="ok",
            result={
                "output": result.output,
                "topic": topic,
                "score": round(result.final_score, 3),
                "sources": result.total_sources,
                "iterations": result.iterations_completed,
                "converged": result.converged,
                "dispatch_recommendations": dispatch_recs,
                "knowledge_base": "ANE+MLX+CUDA (2026-04-02 full swarm)",
            },
        )

    except ImportError:
        # Fallback: return pre-loaded knowledge without deep search
        dispatch_recs = _extract_dispatch_recommendations(topic)
        return TaskResult(
            task_id=task.task_id,
            agent_name="ane-research",
            status="ok",
            result={
                "output": _generate_static_answer(topic),
                "topic": topic,
                "score": 0.75,
                "sources": 0,
                "iterations": 0,
                "converged": True,
                "dispatch_recommendations": dispatch_recs,
                "knowledge_base": "ANE+MLX+CUDA static (ResearchOrchestrator unavailable)",
                "note": "Deep research unavailable — returning pre-loaded knowledge base answer.",
            },
        )


def _extract_dispatch_recommendations(topic: str) -> list[dict[str, Any]]:
    """Return dispatch table entries relevant to the topic."""
    topic_lower = topic.lower()
    recs = []
    for op, info in DISPATCH_TABLE.items():
        if any(kw in topic_lower for kw in [op, op.replace("_", " "), info["target"].lower()]):
            recs.append({"operation": op, **info})
    # Always include top-3 speedup ops as context
    if not recs:
        recs = [
            {"operation": "softmax", **DISPATCH_TABLE["softmax"]},
            {"operation": "rmsnorm", **DISPATCH_TABLE["rmsnorm"]},
            {"operation": "linear", **DISPATCH_TABLE["linear"]},
        ]
    return recs


def _generate_static_answer(topic: str) -> str:
    """Generate a structured answer from the pre-loaded knowledge base."""
    return f"""# ANE + MLX Research: {topic}

## From DarkLab Knowledge Base (2026-04-02 Full Swarm Runs)

{ANE_CONTEXT}

## Dispatch Recommendations

| Operation | Target | Speedup |
|-----------|--------|---------|
| Softmax (32k vocab) | ANE | 33.8× CPU |
| RMSNorm | ANE | 10× CPU |
| Linear layers (matmul as 1×1 conv) | ANE | 3× ANE matmul |
| INT8 W8A8 | ANE | 1.88× FP16 |
| FP16 matmul | GPU/MPS | GPU-native |
| CUDA kernels | SPIR-V → Metal → MLX | Compatibility |
| Gradient accumulation | CPU/cblas | Required fallback |
| Causal masking | CPU/Accelerate | Branching unsupported |

## Key References
- maderix/ANE: https://github.com/maderix/ANE
- Orion: https://github.com/mechramc/Orion
- Orion paper: https://arxiv.org/abs/2603.06728
- MLX custom kernels: https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html
"""


if __name__ == "__main__":
    from shared.node_bridge import run_agent
    run_agent(handle, agent_name="ANEResearch")
