"""Tests for TurboQuant KV cache compression."""
import math
import random

import pytest

from oas_core.turbo_quant.polar_quant import PolarQuant, QuantizedTensor
from oas_core.turbo_quant.qjl import QJLCorrector, QJLResidual
from oas_core.turbo_quant.kv_cache import CompressedKVCache, TurboQuantConfig, CacheStats
from oas_core.turbo_quant.middle_out import MiddleOutPolicy, DEFAULT_TIERS


def _random_tensor(rows: int, cols: int, seed: int = 42) -> list[list[float]]:
    """Generate a random 2D tensor."""
    rng = random.Random(seed)
    return [[rng.gauss(0, 1) for _ in range(cols)] for _ in range(rows)]


def _mse(a: list[list[float]], b: list[list[float]]) -> float:
    """Mean squared error between two 2D tensors."""
    total = 0.0
    count = 0
    for i in range(min(len(a), len(b))):
        for j in range(min(len(a[i]), len(b[i]))):
            total += (a[i][j] - b[i][j]) ** 2
            count += 1
    return total / count if count > 0 else 0.0


# ── PolarQuant tests ─────────────────────────────────────────────

class TestPolarQuant:
    def test_compress_decompress_roundtrip(self):
        """Compress → decompress should approximate the original."""
        pq = PolarQuant(bits=6, head_dim=16, seed=0)
        tensor = _random_tensor(8, 16)
        qt = pq.compress(tensor)
        reconstructed = pq.decompress(qt)

        assert len(reconstructed) == 8
        assert len(reconstructed[0]) == 16
        # 6-bit pure-Python: MSE should be moderate
        error = _mse(tensor, reconstructed)
        assert error < 2.0, f"MSE too high: {error}"

    def test_compression_ratio(self):
        """4-bit should compress significantly vs FP16."""
        pq = PolarQuant(bits=4, head_dim=32)
        tensor = _random_tensor(64, 32)
        qt = pq.compress(tensor)

        assert qt.compression_ratio > 2.0, f"Compression ratio only {qt.compression_ratio:.1f}x"

    def test_3bit_more_compressed_than_4bit(self):
        pq3 = PolarQuant(bits=3, head_dim=16)
        pq4 = PolarQuant(bits=4, head_dim=16)
        tensor = _random_tensor(32, 16)

        qt3 = pq3.compress(tensor)
        qt4 = pq4.compress(tensor)
        assert qt3.memory_bytes < qt4.memory_bytes

    def test_empty_tensor(self):
        pq = PolarQuant(bits=4, head_dim=8)
        qt = pq.compress([])
        assert qt.data == []
        assert pq.decompress(qt) == []

    def test_single_row(self):
        pq = PolarQuant(bits=4, head_dim=8)
        tensor = _random_tensor(1, 8)
        qt = pq.compress(tensor)
        recon = pq.decompress(qt)
        assert len(recon) == 1
        assert len(recon[0]) == 8

    def test_invalid_bits(self):
        with pytest.raises(ValueError):
            PolarQuant(bits=1)
        with pytest.raises(ValueError):
            PolarQuant(bits=9)

    def test_deterministic_rotation(self):
        """Same seed produces same rotation matrix."""
        pq1 = PolarQuant(bits=4, head_dim=8, seed=99)
        pq2 = PolarQuant(bits=4, head_dim=8, seed=99)
        assert pq1.rotation_matrix == pq2.rotation_matrix

    def test_rotation_orthogonality(self):
        """Rotation matrix should be approximately orthogonal."""
        pq = PolarQuant(bits=4, head_dim=8, seed=0)
        rot = pq.rotation_matrix
        dim = len(rot)
        # R @ R^T should ≈ I
        for i in range(dim):
            for j in range(dim):
                dot = sum(rot[i][k] * rot[j][k] for k in range(dim))
                expected = 1.0 if i == j else 0.0
                assert abs(dot - expected) < 0.1, f"Not orthogonal at ({i},{j}): {dot}"


# ── QJL tests ────────────────────────────────────────────────────

class TestQJLCorrector:
    def test_encode_decode_preserves_structure(self):
        """QJL encode → decode produces a non-trivial correction vector."""
        qjl = QJLCorrector(head_dim=16, jl_dim=8, seed=0)

        # Use a structured residual (not random — mimics real quantization error)
        residual = [[0.1 * (i + j) for j in range(16)] for i in range(8)]

        encoded = qjl.encode(residual)
        correction = qjl.decode(encoded)

        # Correction should be non-zero and same shape
        assert len(correction) == 8
        assert len(correction[0]) == 16
        # At least some values should be non-zero
        flat = [abs(v) for row in correction for v in row]
        assert max(flat) > 0.0, "QJL correction is all zeros"

    def test_1bit_memory_efficiency(self):
        """QJL residual should use ~1 bit per projected dimension."""
        qjl = QJLCorrector(head_dim=64, jl_dim=16)
        residual = _random_tensor(100, 64)
        encoded = qjl.encode(residual)

        expected_bits = 100 * 16  # n_vectors * jl_dim
        expected_bytes = math.ceil(expected_bits / 8)
        assert encoded.memory_bytes < expected_bytes * 1.5

    def test_empty_input(self):
        qjl = QJLCorrector(head_dim=8)
        encoded = qjl.encode([])
        assert encoded.n_vectors == 0
        decoded = qjl.decode(encoded)
        assert decoded == []


# ── CompressedKVCache tests ──────────────────────────────────────

class TestCompressedKVCache:
    def _make_kv(self, n_heads: int = 2, seq_len: int = 8, head_dim: int = 16):
        """Generate random K,V tensors per head."""
        k = [_random_tensor(seq_len, head_dim, seed=i) for i in range(n_heads)]
        v = [_random_tensor(seq_len, head_dim, seed=100 + i) for i in range(n_heads)]
        return k, v

    def test_append_and_retrieve(self):
        config = TurboQuantConfig(bits=4, head_dim=16, n_heads=2, enable_qjl=False)
        cache = CompressedKVCache(config)

        k, v = self._make_kv(n_heads=2, seq_len=8, head_dim=16)
        cache.append(k, v)

        assert cache.seq_len == 8

        k_out, v_out = cache.get_decompressed(0)
        assert len(k_out) == 8
        assert len(k_out[0]) == 16

    def test_with_qjl(self):
        config = TurboQuantConfig(bits=3, head_dim=16, n_heads=2, enable_qjl=True)
        cache = CompressedKVCache(config)

        k, v = self._make_kv(n_heads=2, seq_len=8, head_dim=16)
        cache.append(k, v)

        k_out, v_out = cache.get_decompressed(0)
        assert len(k_out) == 8

    def test_compression_stats(self):
        config = TurboQuantConfig(bits=4, head_dim=16, n_heads=4, enable_qjl=False)
        cache = CompressedKVCache(config)

        k, v = self._make_kv(n_heads=4, seq_len=32, head_dim=16)
        cache.append(k, v)

        stats = cache.stats
        assert stats.seq_len == 32
        assert stats.n_heads == 4
        assert stats.memory_bytes > 0
        assert stats.fp16_equivalent_bytes > stats.memory_bytes
        assert stats.compression_ratio > 1.0

    def test_clear(self):
        config = TurboQuantConfig(bits=4, head_dim=8, n_heads=1)
        cache = CompressedKVCache(config)

        k = [_random_tensor(4, 8)]
        v = [_random_tensor(4, 8)]
        cache.append(k, v)
        assert cache.seq_len == 4

        cache.clear()
        assert cache.seq_len == 0

    def test_head_index_out_of_range(self):
        config = TurboQuantConfig(bits=4, head_dim=8, n_heads=2)
        cache = CompressedKVCache(config)
        with pytest.raises(IndexError):
            cache.get_decompressed(5)


# ── MiddleOut tests ──────────────────────────────────────────────

class TestMiddleOutPolicy:
    def test_assign_tiers(self):
        policy = MiddleOutPolicy()
        scores = [0.1, 0.9, 0.5, 0.95, 0.2, 0.6, 0.3, 0.8, 0.15, 0.7]
        assignments = policy.assign(scores)

        assert len(assignments) == 10
        # Highest importance should get high tier
        high_count = sum(1 for a in assignments if a.tier == "high")
        low_count = sum(1 for a in assignments if a.tier == "low")
        assert high_count > 0
        assert low_count > 0

    def test_savings_estimate(self):
        policy = MiddleOutPolicy()
        scores = MiddleOutPolicy.simulate_attention_importance(100)
        assignments = policy.assign(scores)
        savings = policy.estimate_savings(assignments, baseline_bits=4, head_dim=64)

        assert savings["savings_pct"] > 0
        assert savings["middle_out_bytes"] < savings["baseline_bytes"]
        assert savings["avg_bits"] < 4.0

    def test_empty_input(self):
        policy = MiddleOutPolicy()
        assert policy.assign([]) == []
        assert policy.estimate_savings([])["savings_pct"] == 0.0

    def test_tier_fractions_validated(self):
        from oas_core.turbo_quant.middle_out import PrecisionTier
        with pytest.raises(ValueError, match="sum to 1.0"):
            MiddleOutPolicy(tiers=[
                PrecisionTier("a", bits=4, fraction=0.5),
                PrecisionTier("b", bits=2, fraction=0.3),
                # Missing 0.2
            ])
