"""LLM-powered research synthesizer — generates structured reports from papers.

Replaces the placeholder synthesis in the orchestrator with actual LLM calls
via Ollama/LiteLLM. Falls back to placeholder if no LLM is available.
"""
from __future__ import annotations

import logging
from typing import Any

from oas_core.deep_research.sources import SearchResult

__all__ = ["LLMSynthesizer", "SYNTHESIZER_AVAILABLE"]

logger = logging.getLogger("oas.deep_research.llm_synthesizer")

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

SYNTHESIZER_AVAILABLE = _AIOHTTP_AVAILABLE

SYNTHESIS_SYSTEM_PROMPT = """\
You are a DarkLab research synthesizer. Given a research topic, academic papers, \
and optional prior draft with gap feedback, produce a structured research report.

Output format:
# Research Report: [Topic]

## Introduction
[2-3 sentences framing the research question]

## Methodology
[How sources were identified and evaluated]

## Key Findings
[Numbered findings with [citations] referencing the source list]

## Discussion
[Interpretation, implications, connections between findings]

## Conclusion
[Summary and future directions]

## Limitations
[Scope constraints, source limitations]

## References
[Numbered reference list matching citations]

Rules:
- Cite specific papers using [N] notation
- Include quantitative data when available (percentages, counts, dates)
- Be specific, not generic
- If gap feedback is provided, prioritize addressing those gaps
"""


class LLMSynthesizer:
    """Generates research reports using a local LLM via Ollama API.

    Usage::

        synth = LLMSynthesizer(ollama_url="http://localhost:11434")
        report = await synth.synthesize(
            topic="quantum sensors",
            sources=[...],
            prior_draft="...",
            feedback="Missing cost analysis",
        )
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def synthesize(
        self,
        topic: str,
        sources: list[SearchResult],
        prior_draft: str = "",
        feedback: str = "",
    ) -> str:
        """Generate a research report from topic and sources.

        Falls back to a structured concatenation if LLM is unavailable.
        """
        if not SYNTHESIZER_AVAILABLE:
            logger.info("llm_synthesizer_fallback", reason="aiohttp not available")
            return self._fallback(topic, sources, prior_draft, feedback)

        # Build the prompt
        source_text = self._format_sources(sources)
        user_prompt = f"Research topic: {topic}\n\n"
        user_prompt += f"## Available Sources ({len(sources)} papers)\n\n{source_text}\n\n"

        if prior_draft:
            user_prompt += f"## Prior Draft (to improve)\n\n{prior_draft[:2000]}\n\n"
        if feedback:
            user_prompt += f"## Gap Feedback (address these)\n\n{feedback}\n\n"

        user_prompt += "Generate the structured research report now."

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": user_prompt,
                        "system": SYNTHESIS_SYSTEM_PROMPT,
                        "stream": False,
                        "options": {
                            "num_predict": self.max_tokens,
                            "temperature": self.temperature,
                        },
                    },
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("llm_synthesis_http_error", status=resp.status)
                        return self._fallback(topic, sources, prior_draft, feedback)
                    data = await resp.json()
                    return data.get("response", "") or self._fallback(topic, sources, prior_draft, feedback)
        except Exception as exc:
            logger.warning("llm_synthesis_failed", error=str(exc))
            return self._fallback(topic, sources, prior_draft, feedback)

    def _format_sources(self, sources: list[SearchResult]) -> str:
        lines: list[str] = []
        for i, s in enumerate(sources[:20], 1):
            authors = ", ".join(s.authors[:3]) if s.authors else "Unknown"
            year = f" ({s.year})" if s.year else ""
            cites = f" — {s.citation_count} citations" if s.citation_count else ""
            lines.append(f"[{i}] {s.title}{year}. {authors}{cites}")
            if s.abstract:
                lines.append(f"    Abstract: {s.abstract[:300]}")
            lines.append("")
        return "\n".join(lines)

    def _fallback(
        self,
        topic: str,
        sources: list[SearchResult],
        prior_draft: str,
        feedback: str,
    ) -> str:
        """Structured placeholder when LLM is unavailable."""
        sections = [f"# Research Report: {topic}\n"]
        if feedback:
            sections.append(f"*Addressing gaps: {feedback}*\n")
        sections.append("## Introduction\n")
        sections.append(f"This report examines: {topic}\n")
        if sources:
            sections.append(f"\n## Sources ({len(sources)} papers)\n")
            for i, s in enumerate(sources[:15], 1):
                authors = ", ".join(s.authors[:3])
                year = f" ({s.year})" if s.year else ""
                sections.append(f"[{i}] {s.title}{year}. {authors}\n")
        sections.append("\n## Key Findings\n")
        for i, s in enumerate(sources[:5], 1):
            sections.append(f"- Finding {i}: {s.title} [{i}]\n")
        sections.append("\n## Conclusion\n")
        sections.append(f"Further research on {topic} is warranted.\n")
        return "\n".join(sections)
