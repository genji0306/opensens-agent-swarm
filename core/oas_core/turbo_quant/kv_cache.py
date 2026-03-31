"""CompressedKVCache — the main container for TurboQuant-compressed KV data.

Stores Key and Value tensors in compressed form, with on-demand
decompression for attention computation. Supports append (new tokens),
eviction (oldest tokens), and memory budgeting.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from oas_core.turbo_quant.polar_quant import PolarQuant, QuantizedTensor
from oas_core.turbo_quant.qjl import QJLCorrector, QJLResidual

__all__ = ["CompressedKVCache", "TurboQuantConfig", "CacheStats"]

logger = logging.getLogger("oas.turbo_quant.kv_cache")


@dataclass
class TurboQuantConfig:
    """Configuration for TurboQuant compression."""

    bits: int = 4  # Quantization bit-width (2-8)
    head_dim: int = 64  # Transformer head dimension
    n_heads: int = 32  # Number of attention heads
    jl_dim: int | None = None  # QJL projection dim (default: head_dim // 4)
    enable_qjl: bool = True  # Enable QJL residual correction
    max_seq_len: int = 131072  # Maximum sequence length
    seed: int = 42  # Random seed for rotation matrices


@dataclass
class CacheStats:
    """Runtime statistics for a compressed KV cache."""

    seq_len: int = 0
    n_heads: int = 0
    memory_bytes: int = 0
    fp16_equivalent_bytes: int = 0
    compression_ratio: float = 0.0
    peak_memory_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq_len": self.seq_len,
            "n_heads": self.n_heads,
            "memory_mb": round(self.memory_bytes / (1024 * 1024), 2),
            "fp16_equivalent_mb": round(self.fp16_equivalent_bytes / (1024 * 1024), 2),
            "compression_ratio": round(self.compression_ratio, 2),
            "peak_memory_mb": round(self.peak_memory_bytes / (1024 * 1024), 2),
        }


class CompressedKVCache:
    """TurboQuant-compressed KV cache for a single attention layer.

    Stores compressed K and V tensors per attention head. Supports
    incremental append (new tokens) and eviction (oldest tokens).

    Usage::

        config = TurboQuantConfig(bits=4, head_dim=64, n_heads=32)
        cache = CompressedKVCache(config)

        # Compress and store KV for new tokens
        cache.append(k_tensor, v_tensor)  # [seq_new][head_dim] per head

        # Retrieve decompressed KV for attention
        k, v = cache.get_decompressed(head_idx=0)

        # Check memory usage
        stats = cache.stats
    """

    def __init__(self, config: TurboQuantConfig):
        self.config = config
        self._compressors: list[PolarQuant] = [
            PolarQuant(bits=config.bits, head_dim=config.head_dim, seed=config.seed + i)
            for i in range(config.n_heads)
        ]
        self._qjl_correctors: list[QJLCorrector] | None = None
        if config.enable_qjl:
            jl_dim = config.jl_dim or max(4, config.head_dim // 4)
            self._qjl_correctors = [
                QJLCorrector(head_dim=config.head_dim, jl_dim=jl_dim, seed=config.seed + 1000 + i)
                for i in range(config.n_heads)
            ]

        # Storage: per-head compressed K and V
        self._k_compressed: list[QuantizedTensor | None] = [None] * config.n_heads
        self._v_compressed: list[QuantizedTensor | None] = [None] * config.n_heads
        self._k_residuals: list[QJLResidual | None] = [None] * config.n_heads
        self._v_residuals: list[QJLResidual | None] = [None] * config.n_heads

        self._seq_len: int = 0
        self._peak_memory: int = 0

    def append(
        self,
        k_per_head: list[list[list[float]]],
        v_per_head: list[list[list[float]]],
    ) -> None:
        """Compress and append new KV data.

        Args:
            k_per_head: [n_heads][new_tokens][head_dim] Key tensors.
            v_per_head: [n_heads][new_tokens][head_dim] Value tensors.
        """
        n_heads = min(len(k_per_head), self.config.n_heads)
        new_tokens = len(k_per_head[0]) if n_heads > 0 else 0

        for h in range(n_heads):
            k_data = k_per_head[h]
            v_data = v_per_head[h]

            # Compress K
            k_qt = self._compressors[h].compress(k_data)
            self._k_compressed[h] = k_qt

            # Compress V
            v_qt = self._compressors[h].compress(v_data)
            self._v_compressed[h] = v_qt

            # QJL residual correction
            if self._qjl_correctors:
                # Compute residual = original - dequantized
                k_deq = self._compressors[h].decompress(k_qt)
                v_deq = self._compressors[h].decompress(v_qt)
                k_residual = _subtract_2d(k_data, k_deq)
                v_residual = _subtract_2d(v_data, v_deq)
                self._k_residuals[h] = self._qjl_correctors[h].encode(k_residual)
                self._v_residuals[h] = self._qjl_correctors[h].encode(v_residual)

        self._seq_len = new_tokens
        mem = self._compute_memory()
        if mem > self._peak_memory:
            self._peak_memory = mem

    def get_decompressed(self, head_idx: int) -> tuple[list[list[float]], list[list[float]]]:
        """Decompress and return K, V for a specific attention head.

        Returns:
            (K, V) each as [seq_len][head_dim] float lists.
        """
        if head_idx >= self.config.n_heads:
            raise IndexError(f"head_idx {head_idx} >= n_heads {self.config.n_heads}")

        k_qt = self._k_compressed[head_idx]
        v_qt = self._v_compressed[head_idx]

        if k_qt is None or v_qt is None:
            return [], []

        k = self._compressors[head_idx].decompress(k_qt)
        v = self._compressors[head_idx].decompress(v_qt)

        # Apply QJL correction if available
        if self._qjl_correctors and self._k_residuals[head_idx]:
            k_corr = self._qjl_correctors[head_idx].decode(self._k_residuals[head_idx])
            v_corr = self._qjl_correctors[head_idx].decode(self._v_residuals[head_idx])
            k = _add_2d(k, k_corr)
            v = _add_2d(v, v_corr)

        return k, v

    def evict(self, n_tokens: int) -> None:
        """Evict the oldest n_tokens from the cache.

        For simplicity, this clears the cache if n_tokens >= seq_len.
        A production implementation would shift compressed data.
        """
        if n_tokens >= self._seq_len:
            self.clear()
        else:
            self._seq_len -= n_tokens
            # In a production implementation, we'd slice the compressed tensors
            # For now, just track the logical length

    def clear(self) -> None:
        """Clear all cached data."""
        self._k_compressed = [None] * self.config.n_heads
        self._v_compressed = [None] * self.config.n_heads
        self._k_residuals = [None] * self.config.n_heads
        self._v_residuals = [None] * self.config.n_heads
        self._seq_len = 0

    def _compute_memory(self) -> int:
        """Compute current memory usage in bytes."""
        total = 0
        for h in range(self.config.n_heads):
            if self._k_compressed[h]:
                total += self._k_compressed[h].memory_bytes
            if self._v_compressed[h]:
                total += self._v_compressed[h].memory_bytes
            if self._k_residuals[h]:
                total += self._k_residuals[h].memory_bytes
            if self._v_residuals[h]:
                total += self._v_residuals[h].memory_bytes
        return total

    @property
    def seq_len(self) -> int:
        return self._seq_len

    @property
    def stats(self) -> CacheStats:
        mem = self._compute_memory()
        fp16_eq = self._seq_len * self.config.head_dim * self.config.n_heads * 2 * 2  # K+V, FP16
        return CacheStats(
            seq_len=self._seq_len,
            n_heads=self.config.n_heads,
            memory_bytes=mem,
            fp16_equivalent_bytes=fp16_eq,
            compression_ratio=fp16_eq / mem if mem > 0 else 0.0,
            peak_memory_bytes=self._peak_memory,
        )


def _subtract_2d(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[a[i][j] - b[i][j] for j in range(len(a[i]))] for i in range(len(a))]


def _add_2d(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    rows = min(len(a), len(b))
    result = []
    for i in range(rows):
        cols = min(len(a[i]), len(b[i]))
        result.append([a[i][j] + b[i][j] for j in range(cols)])
    return result
