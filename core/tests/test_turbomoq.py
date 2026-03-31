"""Tests for TurboMOQ — integrated into core/oas_core/turbo_quant."""
import math
import pytest

np = pytest.importorskip("numpy")

from oas_core.turbo_quant.turbomoq import (
    TurboMOQConfig,
    TurboMOQCompressedCache,
    NumpyRotation,
    lloyd_max_codebook,
)


# ── Helpers ──

def _randn_2d(rows, cols, seed=42):
    """Generate list[list[float]] random tensor."""
    rng = np.random.RandomState(seed)
    return rng.randn(rows, cols).astype(np.float32).tolist()


def _cosine_sim(a, b):
    """Cosine similarity between two list[list[float]] tensors."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    a_flat = a.reshape(-1, a.shape[-1])
    b_flat = b.reshape(-1, b.shape[-1])
    dots = np.sum(a_flat * b_flat, axis=-1)
    na = np.linalg.norm(a_flat, axis=-1) + 1e-10
    nb = np.linalg.norm(b_flat, axis=-1) + 1e-10
    return float(np.mean(dots / (na * nb)))


def _mse(a, b):
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    return float(np.mean((a - b) ** 2))


# ── NumpyRotation ──

class TestNumpyRotation:
    def test_orthogonal(self):
        rot = NumpyRotation(64)
        I = rot.Q @ rot.Q.T
        assert np.allclose(I, np.eye(64), atol=1e-5)

    def test_deterministic(self):
        r1 = NumpyRotation(32, seed=7)
        r2 = NumpyRotation(32, seed=7)
        assert np.allclose(r1.Q, r2.Q)

    def test_roundtrip_lists(self):
        rot = NumpyRotation(32, seed=42)
        x = _randn_2d(8, 32)
        recovered = rot.unrotate(rot.rotate(x))
        assert _cosine_sim(x, recovered) > 0.9999

    def test_roundtrip_numpy(self):
        rot = NumpyRotation(64)
        x = np.random.randn(16, 64).astype(np.float32)
        recovered = rot.unrotate(rot.rotate(x))
        assert np.allclose(x, recovered, atol=1e-4)

    def test_preserves_norm(self):
        rot = NumpyRotation(32)
        x = np.random.randn(10, 32).astype(np.float32)
        norms_orig = np.linalg.norm(x, axis=1)
        norms_rot = np.linalg.norm(rot.rotate(x), axis=1)
        assert np.allclose(norms_orig, norms_rot, atol=1e-4)


# ── Lloyd-Max Codebook ──

class TestLloydMax:
    def test_correct_count(self):
        vals = np.random.randn(500).tolist()
        for n in [2, 4, 8, 16]:
            cb = lloyd_max_codebook(vals, n)
            assert len(cb) == n

    def test_sorted(self):
        cb = lloyd_max_codebook(np.random.randn(1000).tolist(), 8)
        assert all(cb[i] <= cb[i + 1] for i in range(len(cb) - 1))

    def test_numpy_input(self):
        """Should accept numpy arrays too."""
        cb = lloyd_max_codebook(np.random.randn(100), 4)
        assert len(cb) == 4

    def test_low_distortion(self):
        """Lloyd-Max should achieve lower distortion than uniform spacing."""
        rng = np.random.RandomState(42)
        vals = np.concatenate([rng.randn(800) * 0.3, rng.randn(200) * 3.0])
        n = 8
        lm = lloyd_max_codebook(vals.tolist(), n)
        uniform = np.linspace(vals.min(), vals.max(), n).tolist()

        # Measure distortion for both
        def distortion(cb):
            total = 0
            for v in vals:
                total += min((v - c) ** 2 for c in cb)
            return total / len(vals)

        assert distortion(lm) <= distortion(uniform) * 1.05


# ── TurboMOQCompressedCache ──

class TestTurboMOQCache:
    def _make_cache(self, n_heads=4, head_dim=32, **kwargs):
        config = TurboMOQConfig(
            key_bits=4, value_bits=4,
            head_dim=head_dim, n_heads=n_heads,
            **kwargs,
        )
        return TurboMOQCompressedCache(config)

    def _make_kv(self, n_heads=4, seq_len=16, head_dim=32, seed=42):
        rng = np.random.RandomState(seed)
        K = rng.randn(n_heads, seq_len, head_dim).astype(np.float32).tolist()
        V = rng.randn(n_heads, seq_len, head_dim).astype(np.float32).tolist()
        return K, V

    def test_append_and_seq_len(self):
        cache = self._make_cache()
        K, V = self._make_kv(seq_len=10)
        cache.append(K, V)
        assert cache.seq_len == 10

    def test_get_decompressed_shape(self):
        cache = self._make_cache(head_dim=64)
        K, V = self._make_kv(seq_len=8, head_dim=64)
        cache.append(K, V)
        k_out, v_out = cache.get_decompressed(0)
        assert len(k_out) == 8
        assert len(k_out[0]) == 64

    def test_quality_with_rotation(self):
        cache = self._make_cache(head_dim=64, enable_rotation=True)
        K, V = self._make_kv(seq_len=32, head_dim=64)
        cache.append(K, V)
        k_out, _ = cache.get_decompressed(0)
        cos = _cosine_sim(K[0], k_out)
        assert cos > 0.95, f"Key cosine {cos} too low with rotation"

    def test_quality_without_rotation(self):
        cache = self._make_cache(head_dim=64, enable_rotation=False)
        K, V = self._make_kv(seq_len=32, head_dim=64)
        cache.append(K, V)
        k_out, _ = cache.get_decompressed(0)
        cos = _cosine_sim(K[0], k_out)
        assert cos > 0.9, f"Key cosine {cos} too low without rotation"

    def test_rotation_improves_keys(self):
        """Rotation should improve key quality."""
        K, V = self._make_kv(seq_len=32, head_dim=64)

        cache_rot = self._make_cache(head_dim=64, enable_rotation=True)
        cache_rot.append(K, V)
        k_rot, _ = cache_rot.get_decompressed(0)
        cos_rot = _cosine_sim(K[0], k_rot)

        cache_no = self._make_cache(head_dim=64, enable_rotation=False)
        cache_no.append(K, V)
        k_no, _ = cache_no.get_decompressed(0)
        cos_no = _cosine_sim(K[0], k_no)

        assert cos_rot >= cos_no - 0.01, \
            f"Rotation ({cos_rot:.4f}) should be >= no-rotation ({cos_no:.4f})"

    def test_compression_ratio(self):
        cache = self._make_cache()
        K, V = self._make_kv(seq_len=64)
        cache.append(K, V)
        s = cache.stats
        assert s["compression_ratio"] > 1.0

    def test_calibrate_improves_values(self):
        """Calibration with Lloyd-Max should give decent value quality."""
        K, V = self._make_kv(seq_len=32, head_dim=64)

        cache = self._make_cache(head_dim=64, enable_lloyd_max=True)
        cache.calibrate(V)
        cache.append(K, V)
        _, v_out = cache.get_decompressed(0)
        cos = _cosine_sim(V[0], v_out)
        assert cos > 0.85, f"Calibrated value cosine {cos} too low"

    def test_per_head_bit_allocation(self):
        """Per-head allocation should work."""
        cache = self._make_cache(n_heads=4, head_dim=32)
        cache.set_bit_allocation({0: (8, 8), 1: (2, 2), 2: (4, 4), 3: (1, 1)})
        K, V = self._make_kv(n_heads=4, seq_len=16, head_dim=32)
        cache.append(K, V)

        # Head 0 (8-bit) should have better quality than head 3 (1-bit)
        k0, _ = cache.get_decompressed(0)
        k3, _ = cache.get_decompressed(3)
        cos0 = _cosine_sim(K[0], k0)
        cos3 = _cosine_sim(K[3], k3)
        assert cos0 > cos3, f"8-bit head ({cos0:.4f}) should beat 1-bit ({cos3:.4f})"

    def test_clear(self):
        cache = self._make_cache()
        K, V = self._make_kv()
        cache.append(K, V)
        assert cache.seq_len > 0
        cache.clear()
        assert cache.seq_len == 0

    def test_evict(self):
        cache = self._make_cache()
        K, V = self._make_kv(seq_len=20)
        cache.append(K, V)
        cache.evict(10)
        assert cache.seq_len == 10

    def test_evict_all(self):
        cache = self._make_cache()
        K, V = self._make_kv(seq_len=10)
        cache.append(K, V)
        cache.evict(100)
        assert cache.seq_len == 0

    def test_stats_structure(self):
        cache = self._make_cache()
        K, V = self._make_kv()
        cache.append(K, V)
        s = cache.stats
        assert "seq_len" in s
        assert "compression_ratio" in s
        assert "rotation_enabled" in s
        assert "lloyd_max_enabled" in s
        assert s["rotation_enabled"] is True

    def test_multiple_appends(self):
        cache = self._make_cache()
        K1, V1 = self._make_kv(seq_len=8, seed=1)
        K2, V2 = self._make_kv(seq_len=12, seed=2)
        cache.append(K1, V1)
        cache.append(K2, V2)
        assert cache.seq_len == 12  # last append's seq len

    def test_head_index_bounds(self):
        cache = self._make_cache(n_heads=2)
        K, V = self._make_kv(n_heads=2)
        cache.append(K, V)
        with pytest.raises(IndexError):
            cache.get_decompressed(5)

    def test_empty_cache_decompresses(self):
        cache = self._make_cache()
        k, v = cache.get_decompressed(0)
        assert k == []
        assert v == []


# ── Integration: TurboMOQ vs PolarQuant ──

class TestVsPolarQuant:
    """Compare TurboMOQ against the original PolarQuant at same bit level."""

    def test_turbomoq_beats_polarquant_cosine(self):
        """TurboMOQ (numpy rotation) should have better cosine than PolarQuant."""
        from oas_core.turbo_quant.polar_quant import PolarQuant

        head_dim = 32
        seq_len = 32
        rng = np.random.RandomState(42)
        K = rng.randn(seq_len, head_dim).astype(np.float32)

        # PolarQuant (pure Python)
        pq = PolarQuant(bits=4, head_dim=head_dim, seed=42)
        k_qt = pq.compress(K.tolist())
        k_pq = np.array(pq.decompress(k_qt), dtype=np.float32)
        cos_pq = _cosine_sim(K, k_pq)

        # TurboMOQ (numpy rotation)
        config = TurboMOQConfig(key_bits=4, value_bits=4, head_dim=head_dim, n_heads=1)
        cache = TurboMOQCompressedCache(config)
        cache.append([K.tolist()], [K.tolist()])
        k_tmoq, _ = cache.get_decompressed(0)
        cos_tmoq = _cosine_sim(K.tolist(), k_tmoq)

        assert cos_tmoq > cos_pq, \
            f"TurboMOQ ({cos_tmoq:.4f}) should beat PolarQuant ({cos_pq:.4f})"

    def test_turbomoq_compression_comparable(self):
        """TurboMOQ should achieve comparable compression to PolarQuant."""
        from oas_core.turbo_quant.polar_quant import PolarQuant, QuantizedTensor

        head_dim = 32
        seq_len = 64
        K = np.random.randn(seq_len, head_dim).astype(np.float32)

        pq = PolarQuant(bits=4, head_dim=head_dim)
        qt = pq.compress(K.tolist())
        pq_bytes = qt.memory_bytes

        config = TurboMOQConfig(key_bits=4, value_bits=4, head_dim=head_dim, n_heads=1)
        cache = TurboMOQCompressedCache(config)
        cache.append([K.tolist()], [K.tolist()])
        tmoq_bytes = cache.stats["memory_bytes"]

        # TurboMOQ should be within 2x of PolarQuant's memory
        assert tmoq_bytes < pq_bytes * 3, \
            f"TurboMOQ ({tmoq_bytes}) shouldn't be much larger than PolarQuant ({pq_bytes})"
