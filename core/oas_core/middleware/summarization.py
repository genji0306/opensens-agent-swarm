"""Context window management middleware.

Auto-summarises conversation history when it approaches the model's
context limit. Uses a simple token-count heuristic (4 chars ≈ 1 token)
to decide when to compress older messages.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = ["SummarizationMiddleware"]

logger = logging.getLogger("oas.middleware.summarization")

# Approximate chars-per-token ratio for English text
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count estimate (4 chars ≈ 1 token)."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


class SummarizationMiddleware:
    """Middleware that compresses long conversations.

    When the total message history exceeds ``max_tokens``, older messages
    are replaced with a summary, keeping the most recent ``keep_recent``
    messages intact.

    Usage::

        mw = SummarizationMiddleware(max_tokens=100_000, keep_recent=10)
        messages = mw.maybe_compress(messages, summarize_fn)
    """

    def __init__(
        self,
        max_tokens: int = 100_000,
        *,
        keep_recent: int = 10,
        summary_prefix: str = "[Prior conversation summary]\n",
    ):
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent
        self.summary_prefix = summary_prefix

    def _total_tokens(self, messages: list[dict[str, Any]]) -> int:
        return sum(
            estimate_tokens(m.get("content", ""))
            for m in messages
        )

    def needs_compression(self, messages: list[dict[str, Any]]) -> bool:
        """Check if messages exceed the token budget."""
        return self._total_tokens(messages) > self.max_tokens

    def compress(
        self,
        messages: list[dict[str, Any]],
        summary: str,
    ) -> list[dict[str, Any]]:
        """Replace older messages with a summary, keeping recent ones.

        Args:
            messages: Full message list
            summary: Pre-generated summary of older messages

        Returns:
            Compressed message list with summary prepended
        """
        if len(messages) <= self.keep_recent:
            return messages

        recent = messages[-self.keep_recent:]
        summary_msg = {
            "role": "system",
            "content": self.summary_prefix + summary,
        }

        logger.info(
            "conversation_compressed",
            extra={
                "original_count": len(messages),
                "kept_recent": len(recent),
                "summary_tokens": estimate_tokens(summary),
            },
        )

        return [summary_msg] + recent
