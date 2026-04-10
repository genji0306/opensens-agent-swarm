"""Eval-driven development harness for OAS.

Golden set management, multi-dimension scoring, config comparison,
and regression detection for continuous agent improvement.
"""

from __future__ import annotations

from oas_core.eval.runner import EvalReport, EvalRunner
from oas_core.eval.scorer import DimensionScore, EvalScorer, ScoringResult

__all__ = [
    "DimensionScore",
    "EvalReport",
    "EvalRunner",
    "EvalScorer",
    "ScoringResult",
]
