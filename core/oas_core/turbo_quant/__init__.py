"""TurboQuant KV cache compression for multi-agent long-context reasoning.

Implements PolarQuant (rotation + scalar quantization) and QJL (1-bit
residual correction) to compress FP16 KV cache to ~3-4 bits with near-zero
accuracy loss. Achieves ~6x memory reduction and ~8x attention speedup.

The compression is:
- Inference-time (no training required)
- Data-oblivious (works with any model)
- Training-free (no calibration data needed)

Optional dependency: numpy. Falls back to pure-Python math without it.
"""
from __future__ import annotations

__all__ = [
    "PolarQuant",
    "QJLCorrector",
    "CompressedKVCache",
    "MemoryPool",
    "MiddleOutPolicy",
    "TurboQuantConfig",
    "TurboMOQCompressedCache",
    "TurboMOQConfig",
    "NumpyRotation",
    "NUMPY_AVAILABLE",
]

import logging

logger = logging.getLogger("oas.turbo_quant")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.info("numpy not available — TurboQuant using pure-Python fallback")

from oas_core.turbo_quant.polar_quant import PolarQuant
from oas_core.turbo_quant.qjl import QJLCorrector
from oas_core.turbo_quant.kv_cache import CompressedKVCache, TurboQuantConfig
from oas_core.turbo_quant.memory_pool import MemoryPool
from oas_core.turbo_quant.middle_out import MiddleOutPolicy

try:
    from oas_core.turbo_quant.turbomoq import (
        TurboMOQCompressedCache,
        TurboMOQConfig,
        NumpyRotation,
    )
except ImportError:
    # numpy not available — TurboMOQ requires numpy
    pass
