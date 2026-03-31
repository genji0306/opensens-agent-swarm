"""Deep Research orchestrator — iterative research with convergence evaluation.

Implements the Memento-Codex integration plan: a multi-phase research pipeline
that generates a research draft, refines it through specialist agents, and
iterates until quality converges above the threshold.

Flow:
  1. Academic source search (arXiv, Semantic Scholar, bioRxiv)
  2. Research synthesis via LLM
  3. Refinement through specialist roles (fact-checker, gap-finder, synthesizer, critic)
  4. Convergence evaluation (5 quality metrics)
  5. Iterate or deliver
"""
from __future__ import annotations

__all__ = [
    "ResearchOrchestrator",
    "ConvergenceEvaluator",
    "AcademicSearcher",
    "KnowledgeBase",
    "ResearchConfig",
    "ResearchResult",
    "SearchResult",
]

from oas_core.deep_research.orchestrator import ResearchOrchestrator, ResearchConfig, ResearchResult
from oas_core.deep_research.evaluator import ConvergenceEvaluator
from oas_core.deep_research.sources import AcademicSearcher, SearchResult
from oas_core.deep_research.knowledge_base import KnowledgeBase
