"""PolarQuant — rotation + scalar quantization for KV cache compression.

Algorithm:
1. Apply random Hadamard rotation to flatten outlier distribution
2. Per-channel scalar quantization to target bit-width (3-4 bits)
3. Store quantized values + per-channel scales for reconstruction

The rotation matrix is generated once per model configuration and reused
across all compression calls. This ensures consistency and enables
efficient batch processing.
"""
from __future__ import annotations

import hashlib
import logging
import math
import struct
from dataclasses import dataclass, field
from typing import Any

__all__ = ["PolarQuant", "QuantizedTensor"]

logger = logging.getLogger("oas.turbo_quant.polar_quant")


@dataclass
class QuantizedTensor:
    """A quantized tensor with per-channel scales for reconstruction.

    Attributes:
        data: Quantized integer values (flat list, row-major).
        scales: Per-channel scale factors for dequantization.
        shape: Original tensor shape (rows, cols).
        bits: Quantization bit-width.
        zero_points: Per-channel zero points (for asymmetric quantization).
    """

    data: list[int]
    scales: list[float]
    shape: tuple[int, int]
    bits: int = 4
    zero_points: list[float] = field(default_factory=list)

    @property
    def memory_bytes(self) -> int:
        """Estimated memory usage in bytes."""
        n_values = len(self.data)
        data_bytes = math.ceil(n_values * self.bits / 8)
        scale_bytes = len(self.scales) * 2  # FP16 scales
        return data_bytes + scale_bytes

    @property
    def compression_ratio(self) -> float:
        """Compression ratio vs FP16 baseline."""
        fp16_bytes = self.shape[0] * self.shape[1] * 2
        if self.memory_bytes == 0:
            return 0.0
        return fp16_bytes / self.memory_bytes


class PolarQuant:
    """PolarQuant compressor: random rotation + scalar quantization.

    Usage::

        pq = PolarQuant(bits=4, head_dim=64)
        quantized = pq.compress(tensor_2d)
        reconstructed = pq.decompress(quantized)

    The random rotation matrix is seeded from head_dim for determinism.
    """

    def __init__(self, bits: int = 4, head_dim: int = 64, seed: int | None = None):
        if bits < 2 or bits > 8:
            raise ValueError(f"bits must be 2-8, got {bits}")
        self.bits = bits
        self.head_dim = head_dim
        self._seed = seed if seed is not None else head_dim
        self._rotation: list[list[float]] | None = None

    @property
    def rotation_matrix(self) -> list[list[float]]:
        """Lazy-init the random orthogonal rotation matrix."""
        if self._rotation is None:
            self._rotation = self._generate_hadamard_rotation(self.head_dim, self._seed)
        return self._rotation

    def compress(self, tensor: list[list[float]]) -> QuantizedTensor:
        """Compress a 2D tensor (seq_len x head_dim) using PolarQuant.

        Args:
            tensor: 2D list of floats [seq_len][head_dim].

        Returns:
            QuantizedTensor with compressed data and reconstruction metadata.
        """
        rows = len(tensor)
        cols = len(tensor[0]) if rows > 0 else 0

        if cols == 0:
            return QuantizedTensor(data=[], scales=[], shape=(rows, cols), bits=self.bits)

        # Step 1: Apply rotation (flatten outlier distribution)
        rotated = self._apply_rotation(tensor)

        # Step 2: Per-channel scalar quantization
        qmax = (1 << self.bits) - 1
        half = qmax // 2

        scales: list[float] = []
        quantized: list[int] = []

        for col_idx in range(cols):
            # Find per-channel max absolute value
            col_max = 0.0
            for row_idx in range(rows):
                val = abs(rotated[row_idx][col_idx])
                if val > col_max:
                    col_max = val

            scale = col_max / half if col_max > 0 else 1.0
            scales.append(scale)

            # Symmetric quantization
            for row_idx in range(rows):
                val = rotated[row_idx][col_idx]
                q = round(val / scale)
                q = max(-half, min(half, q))
                quantized.append(q + half)  # Store as unsigned

        return QuantizedTensor(
            data=quantized,
            scales=scales,
            shape=(rows, cols),
            bits=self.bits,
        )

    def decompress(self, qt: QuantizedTensor) -> list[list[float]]:
        """Decompress a QuantizedTensor back to 2D float tensor.

        Args:
            qt: The compressed QuantizedTensor.

        Returns:
            2D list of floats [seq_len][head_dim] (approximate reconstruction).
        """
        rows, cols = qt.shape
        if rows == 0 or cols == 0:
            return []

        half = ((1 << qt.bits) - 1) // 2

        # Dequantize
        rotated: list[list[float]] = []
        for row_idx in range(rows):
            row: list[float] = []
            for col_idx in range(cols):
                idx = row_idx * cols + col_idx
                q_unsigned = qt.data[idx]
                q_signed = q_unsigned - half
                val = q_signed * qt.scales[col_idx]
                row.append(val)
            rotated.append(row)

        # Apply inverse rotation
        return self._apply_inverse_rotation(rotated)

    def _apply_rotation(self, tensor: list[list[float]]) -> list[list[float]]:
        """Apply the random Hadamard rotation to the tensor."""
        rot = self.rotation_matrix
        rows = len(tensor)
        cols = len(tensor[0]) if rows else 0
        result: list[list[float]] = []

        for row_idx in range(rows):
            new_row: list[float] = []
            for col_idx in range(cols):
                val = 0.0
                for k in range(cols):
                    val += tensor[row_idx][k] * rot[k][col_idx]
                new_row.append(val)
            result.append(new_row)

        return result

    def _apply_inverse_rotation(self, tensor: list[list[float]]) -> list[list[float]]:
        """Apply the transpose (inverse) of the rotation matrix."""
        rot = self.rotation_matrix
        rows = len(tensor)
        cols = len(tensor[0]) if rows else 0
        result: list[list[float]] = []

        for row_idx in range(rows):
            new_row: list[float] = []
            for col_idx in range(cols):
                val = 0.0
                for k in range(cols):
                    val += tensor[row_idx][k] * rot[col_idx][k]  # Transposed
                new_row.append(val)
            result.append(new_row)

        return result

    @staticmethod
    def _generate_hadamard_rotation(dim: int, seed: int) -> list[list[float]]:
        """Generate a random orthogonal matrix using seeded Hadamard construction.

        Uses a simplified construction: random sign flips applied to a
        Walsh-Hadamard-like structure, then Gram-Schmidt orthogonalization.
        """
        import random
        rng = random.Random(seed)

        # Generate random matrix
        matrix: list[list[float]] = []
        for i in range(dim):
            row = [rng.gauss(0, 1) for _ in range(dim)]
            matrix.append(row)

        # Gram-Schmidt orthogonalization
        for i in range(dim):
            # Subtract projections of previous vectors
            for j in range(i):
                dot = sum(matrix[i][k] * matrix[j][k] for k in range(dim))
                for k in range(dim):
                    matrix[i][k] -= dot * matrix[j][k]

            # Normalize
            norm = math.sqrt(sum(matrix[i][k] ** 2 for k in range(dim)))
            if norm > 1e-10:
                for k in range(dim):
                    matrix[i][k] /= norm

        return matrix
