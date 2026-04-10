"""Tests for the knowledge embedding helpers and autoDream integration.

The mlx-embeddings model is not required for these tests — they exercise
the hash fallback path, which is deterministic and always available.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest


def test_hash_embedding_deterministic():
    """Same input → same vector, always."""
    from oas_core.knowledge.embeddings import hash_embedding

    a = hash_embedding("ionic liquid electrode study")
    b = hash_embedding("ionic liquid electrode study")
    assert a == b
    assert len(a) == 128


def test_hash_embedding_normalized():
    """Hash embeddings are L2-normalized."""
    from oas_core.knowledge.embeddings import hash_embedding

    v = hash_embedding("some text to encode")
    norm = math.sqrt(sum(x * x for x in v))
    # Allow small floating-point drift
    assert abs(norm - 1.0) < 1e-6 or norm == 0.0


def test_hash_embedding_empty():
    """Empty string returns zero vector, not an error."""
    from oas_core.knowledge.embeddings import hash_embedding

    v = hash_embedding("")
    assert len(v) == 128
    assert all(x == 0.0 for x in v)


def test_hash_embedding_similarity_shared_tokens():
    """Texts sharing tokens have higher cosine similarity than disjoint texts."""
    from oas_core.knowledge.embeddings import hash_embedding
    from oas_core.kairos.autodream import _cosine_similarity

    a = hash_embedding("ionic liquid electrode conductivity study")
    b = hash_embedding("ionic liquid electrode stability analysis")
    c = hash_embedding("quantum computing topological qubits")

    sim_ab = _cosine_similarity(a, b)
    sim_ac = _cosine_similarity(a, c)

    # Shared tokens should produce higher similarity than disjoint
    assert sim_ab > sim_ac


def test_get_embedding_fn_returns_callable():
    """get_embedding_fn() returns a working str -> list[float] callable."""
    from oas_core.knowledge.embeddings import get_embedding_fn

    fn = get_embedding_fn(prefer_mlx=False)
    assert callable(fn)
    result = fn("test input")
    assert isinstance(result, list)
    assert len(result) == 128
    assert all(isinstance(x, float) for x in result)


def test_autodream_semantic_merge_with_embedding_fn(tmp_path: Path):
    """AutoDream uses semantic merge when embedding_fn is provided."""
    from oas_core.kairos.autodream import AutoDream
    from oas_core.knowledge.embeddings import hash_embedding

    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    kb_file = kb_dir / "knowledge.jsonl"
    # Two near-duplicates (differ only in ending), one unrelated
    import json
    entries = [
        {"content": "ionic liquid electrode conductivity is high", "timestamp": 9e9},
        {"content": "ionic liquid electrode conductivity is excellent", "timestamp": 9e9},
        {"content": "quantum dots used in display technology", "timestamp": 9e9},
    ]
    kb_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    # Threshold lowered to 0.75 because the hash fallback embedding produces
    # cosine ~0.83 for the two near-duplicate entries here. Real mlx-embeddings
    # vectors cluster near-dupes much more tightly (> 0.92), so the default
    # 0.85 in AutoDream is fine for production but too strict for the hash
    # stand-in used in this unit test.
    dream = AutoDream(
        kb_dir=kb_dir,
        similarity_threshold=0.75,
        embedding_fn=hash_embedding,
    )
    result = dream.consolidate()

    # The two near-dupes should be merged, unrelated one stays
    assert result["entries_before"] == 3
    assert result["entries_after"] == 2
    assert result["merged"] >= 1
    assert result["succeeded"] is True


def test_autodream_falls_back_to_prefix_without_fn(tmp_path: Path):
    """AutoDream without embedding_fn uses prefix dedup."""
    from oas_core.kairos.autodream import AutoDream
    import json

    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    kb_file = kb_dir / "knowledge.jsonl"
    entries = [
        {"content": "exact duplicate text here", "timestamp": 9e9},
        {"content": "exact duplicate text here", "timestamp": 9e9},
    ]
    kb_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    dream = AutoDream(kb_dir=kb_dir)  # No embedding_fn
    result = dream.consolidate()

    # Exact duplicates removed by dedup step (SHA-256), not prefix
    assert result["entries_after"] == 1
    assert result["deduplicated"] == 1


def test_autodream_semantic_merge_handles_embed_errors(tmp_path: Path):
    """If embedding_fn raises, entry is kept rather than dropped."""
    from oas_core.kairos.autodream import AutoDream
    import json

    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    kb_file = kb_dir / "knowledge.jsonl"
    entries = [
        {"content": "first entry", "timestamp": 9e9},
        {"content": "second entry", "timestamp": 9e9},
    ]
    kb_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    def broken_fn(text: str) -> list[float]:
        raise RuntimeError("embedding service down")

    dream = AutoDream(kb_dir=kb_dir, embedding_fn=broken_fn)
    result = dream.consolidate()

    # Both entries should survive even though embedding_fn throws
    assert result["entries_after"] == 2
    assert result["merged"] == 0
    assert result["succeeded"] is True


def test_mlx_embeddings_availability_flag():
    """MLX_EMBEDDINGS_AVAILABLE is a boolean — detection should work."""
    from oas_core.knowledge.embeddings import MLX_EMBEDDINGS_AVAILABLE

    assert isinstance(MLX_EMBEDDINGS_AVAILABLE, bool)


def test_knowledge_package_exports_embedding_helpers():
    """The knowledge package re-exports the new embedding helpers."""
    from oas_core import knowledge

    assert hasattr(knowledge, "get_embedding_fn")
    assert hasattr(knowledge, "hash_embedding")
    assert hasattr(knowledge, "MLX_EMBEDDINGS_AVAILABLE")


def test_cosine_similarity_edge_cases():
    """_cosine_similarity handles zero vectors and mismatched dims."""
    from oas_core.kairos.autodream import _cosine_similarity

    assert _cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)
