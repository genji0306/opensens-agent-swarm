"""Local embedding helpers for the knowledge subsystem.

Two providers supported:

1. **mlx-embeddings** (preferred on Apple Silicon): loads a local
   sentence-transformer model via MLX and runs inference on the Apple
   Neural Engine / GPU. Default model is ``all-MiniLM-L6-v2`` which
   produces 384-dim vectors at ~15 ms per 1K tokens.

2. **hash fallback** (always works): deterministic low-dimensional
   bag-of-hashes vector. Not semantically meaningful but cosine
   similarity still identifies exact duplicates and near-duplicates
   (shared tokens), which is enough for autoDream dedup when the real
   embedding model is unavailable.

The main entry point is :func:`get_embedding_fn`, which returns a
callable ``str -> list[float]`` suitable for passing to
``AutoDream(embedding_fn=...)``. The function is callable from a forked
subprocess because it re-initializes the model on first use inside the
child process.
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, Callable

__all__ = [
    "get_embedding_fn",
    "hash_embedding",
    "MLX_EMBEDDINGS_AVAILABLE",
    "DEFAULT_EMBEDDING_MODEL",
]

logger = logging.getLogger("oas.knowledge.embeddings")

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_HASH_DIM = 128

try:
    import mlx_embeddings  # type: ignore[import-not-found]

    MLX_EMBEDDINGS_AVAILABLE = True
except ImportError:
    mlx_embeddings = None  # type: ignore[assignment]
    MLX_EMBEDDINGS_AVAILABLE = False


def hash_embedding(text: str, dim: int = _HASH_DIM) -> list[float]:
    """Deterministic bag-of-hashes embedding in R^dim.

    Not semantically meaningful, but cosine similarity is stable: two
    texts that share tokens produce correlated vectors. Good enough for
    exact-duplicate and near-duplicate detection when no real embedding
    model is available.
    """
    vec = [0.0] * dim
    if not text:
        return vec
    tokens = text.lower().split()
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if (digest[4] & 1) else -1.0
        vec[idx] += sign
    # L2 normalize so cosine similarity reduces to dot product
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _make_mlx_fn(model_name: str) -> Callable[[str], list[float]]:
    """Build an embedding function backed by mlx-embeddings.

    The model is loaded lazily on first call so the function survives
    being pickled/imported by a forked subprocess without paying the
    load cost until actually needed.
    """
    state: dict[str, Any] = {"model": None}

    def embed(text: str) -> list[float]:
        if state["model"] is None:
            try:
                model, tokenizer = mlx_embeddings.load(model_name)  # type: ignore[union-attr]
                state["model"] = (model, tokenizer)
            except Exception as exc:
                logger.warning(
                    "mlx_embeddings_load_failed_falling_back_to_hash",
                    extra={"model": model_name, "error": str(exc)},
                )
                state["model"] = "fallback"
        if state["model"] == "fallback":
            return hash_embedding(text)
        try:
            model, tokenizer = state["model"]
            output = mlx_embeddings.generate(model, tokenizer, texts=[text])  # type: ignore[union-attr]
            # Normalize to plain Python list of floats
            vec = output.text_embeds[0].tolist() if hasattr(output, "text_embeds") else output[0].tolist()
            return [float(x) for x in vec]
        except Exception as exc:
            logger.warning(
                "mlx_embeddings_generate_failed_falling_back",
                extra={"error": str(exc)},
            )
            return hash_embedding(text)

    return embed


def get_embedding_fn(
    *, prefer_mlx: bool = True, model: str = DEFAULT_EMBEDDING_MODEL
) -> Callable[[str], list[float]]:
    """Return a callable that maps text to a dense vector.

    Args:
        prefer_mlx: If True and mlx-embeddings is importable, use it.
            Otherwise fall back to the hash embedding.
        model: HuggingFace model id for mlx-embeddings. Ignored when
            falling back to hash.

    Returns:
        A function ``embed(text: str) -> list[float]`` that is safe to
        call from a forked subprocess. The mlx-embeddings model is
        loaded lazily on first invocation inside that process.
    """
    if prefer_mlx and MLX_EMBEDDINGS_AVAILABLE:
        logger.info("embedding_fn_mlx_selected", extra={"model": model})
        return _make_mlx_fn(model)
    logger.info("embedding_fn_hash_selected")
    return hash_embedding
