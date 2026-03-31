"""QJL — Quantized Johnson-Lindenstrauss residual correction.

After PolarQuant compresses K,V to ~3-4 bits, there's a quantization residual.
QJL corrects this using:

1. Random JL projection to reduce dimensionality
2. 1-bit sign quantization of the projected residual
3. On-demand reconstruction via transpose projection

This adds minimal overhead (~1 bit per dimension) while recovering much of
the quantization error, making 3-bit compression nearly lossless.
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any

__all__ = ["QJLCorrector", "QJLResidual"]

logger = logging.getLogger("oas.turbo_quant.qjl")


@dataclass
class QJLResidual:
    """1-bit residual correction data from QJL projection.

    Attributes:
        sign_bits: Packed sign bits (1 = positive, 0 = negative).
        scale: Global scale factor for reconstruction.
        jl_dim: Projected dimensionality.
        original_dim: Original head dimension.
        n_vectors: Number of vectors (seq_len).
    """

    sign_bits: list[int]  # Packed as integers (each stores up to 32 bits)
    scale: float
    jl_dim: int
    original_dim: int
    n_vectors: int

    @property
    def memory_bytes(self) -> int:
        """Estimated memory usage in bytes."""
        bits_total = self.n_vectors * self.jl_dim
        return math.ceil(bits_total / 8) + 4  # +4 for scale FP32


class QJLCorrector:
    """QJL residual correction using random Johnson-Lindenstrauss projection.

    Usage::

        qjl = QJLCorrector(head_dim=64, jl_dim=16)
        residual_data = qjl.encode(residual_2d)
        correction = qjl.decode(residual_data)
        # Add correction back to dequantized tensor
    """

    def __init__(self, head_dim: int = 64, jl_dim: int | None = None, seed: int = 42):
        self.head_dim = head_dim
        self.jl_dim = jl_dim or max(4, head_dim // 4)
        self._seed = seed
        self._jl_matrix: list[list[float]] | None = None

    @property
    def jl_matrix(self) -> list[list[float]]:
        """Lazy-init the random JL projection matrix.

        JL matrix is sparse {-1, +1} scaled by 1/sqrt(jl_dim).
        """
        if self._jl_matrix is None:
            rng = random.Random(self._seed)
            scale = 1.0 / math.sqrt(self.jl_dim)
            matrix: list[list[float]] = []
            for i in range(self.jl_dim):
                row = [scale * (1.0 if rng.random() > 0.5 else -1.0) for _ in range(self.head_dim)]
                matrix.append(row)
            self._jl_matrix = matrix
        return self._jl_matrix

    def encode(self, residual: list[list[float]]) -> QJLResidual:
        """Encode quantization residual using QJL 1-bit projection.

        Args:
            residual: 2D float tensor [seq_len][head_dim] — the quantization error.

        Returns:
            QJLResidual with 1-bit sign data and reconstruction scale.
        """
        n_vectors = len(residual)
        if n_vectors == 0:
            return QJLResidual(sign_bits=[], scale=0.0, jl_dim=self.jl_dim,
                               original_dim=self.head_dim, n_vectors=0)

        jl = self.jl_matrix

        # Project: projected[i][j] = sum(jl[j][k] * residual[i][k])
        projected: list[list[float]] = []
        for vec in residual:
            proj_vec: list[float] = []
            for j in range(self.jl_dim):
                val = sum(jl[j][k] * vec[k] for k in range(self.head_dim))
                proj_vec.append(val)
            projected.append(proj_vec)

        # Compute global scale as RMS of projected values
        sum_sq = 0.0
        count = 0
        for pvec in projected:
            for v in pvec:
                sum_sq += v * v
                count += 1
        scale = math.sqrt(sum_sq / count) if count > 0 else 1.0

        # 1-bit sign quantization — pack into integers
        sign_bits: list[int] = []
        current_word = 0
        bit_pos = 0

        for pvec in projected:
            for v in pvec:
                if v >= 0:
                    current_word |= (1 << bit_pos)
                bit_pos += 1
                if bit_pos == 32:
                    sign_bits.append(current_word)
                    current_word = 0
                    bit_pos = 0

        if bit_pos > 0:
            sign_bits.append(current_word)

        return QJLResidual(
            sign_bits=sign_bits,
            scale=scale,
            jl_dim=self.jl_dim,
            original_dim=self.head_dim,
            n_vectors=n_vectors,
        )

    def decode(self, residual: QJLResidual) -> list[list[float]]:
        """Decode QJL residual back to approximate correction vectors.

        Args:
            residual: QJLResidual from encode().

        Returns:
            2D float tensor [seq_len][head_dim] — approximate residual.
        """
        if residual.n_vectors == 0:
            return []

        jl = self.jl_matrix

        # Unpack sign bits
        signs: list[float] = []
        bit_idx = 0
        total_bits = residual.n_vectors * residual.jl_dim

        for word in residual.sign_bits:
            for pos in range(32):
                if bit_idx >= total_bits:
                    break
                sign = 1.0 if (word & (1 << pos)) else -1.0
                signs.append(sign * residual.scale)
                bit_idx += 1

        # Transpose projection: result[i][k] = sum(jl[j][k] * signs[i*jl_dim+j])
        result: list[list[float]] = []
        for i in range(residual.n_vectors):
            vec: list[float] = []
            for k in range(self.head_dim):
                val = 0.0
                for j in range(self.jl_dim):
                    val += jl[j][k] * signs[i * self.jl_dim + j]
                vec.append(val)
            result.append(vec)

        return result
