"""Knowledge ingestion pipeline -- campaign step results to wiki entries.

Extracts entities and claims from campaign step results, stores them
in the wiki, entity store, and embedding index.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oas_core.knowledge.entity_store import EntityStore

__all__ = ["KnowledgeIngester"]

logger = logging.getLogger("oas.knowledge.ingester")


class KnowledgeIngester:
    """Ingests campaign step results into the wiki knowledge system.

    Orchestrates entity extraction, claim tracking, wiki page writing,
    and optional OpenViking write-back. Emits a DRVP event on success.
    """

    def __init__(
        self,
        *,
        wiki_dir: str | Path,
        entity_store: EntityStore,
        embedding_index: Any | None = None,  # EmbeddingIndex (optional)
        memory_client: Any | None = None,  # MemoryClient (optional)
    ) -> None:
        self._wiki_dir = Path(wiki_dir)
        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        self._entity_store = entity_store
        self._embedding_index = embedding_index
        self._memory_client = memory_client
        self._log_path = self._wiki_dir / "log.md"

    # ---- Public API ----

    async def ingest(
        self,
        *,
        step_result: dict[str, Any],
        campaign_id: str,
        step_number: int,
        agent_id: str = "leader",
        model_tier: str = "PLANNING_LOCAL",
        request_id: str = "",
    ) -> dict[str, Any]:
        """Ingest a campaign step result into the knowledge system.

        Returns a dict summarising the ingestion outcome.
        """
        start = time.monotonic()
        text = self._extract_text(step_result)
        if not text or len(text) < 50:
            return {"ingested": False, "reason": "insufficient_content"}

        # Extract entities (simple heuristic -- Gemma structured output in prod)
        entities = self._extract_entities(text)

        # Extract claims
        claims = self._extract_claims(text, campaign_id, step_number)

        # Store entities
        for ent in entities:
            self._entity_store.add_entity(
                name=ent["name"],
                entity_type=ent["type"],
                properties=ent.get("properties", {}),
            )

        # Store claims
        for claim in claims:
            self._entity_store.add_claim(
                claim_id=claim["id"],
                topic=claim["topic"],
                statement=claim["statement"],
                confidence=claim.get("confidence", 0.5),
                sources=claim.get("sources", []),
                provenance={
                    "agent_id": agent_id,
                    "campaign_id": campaign_id,
                    "model_tier": model_tier,
                },
            )

        # Write wiki page for campaign step
        page_path = self._write_campaign_page(
            campaign_id, step_number, text, entities, claims,
        )

        # Update index.md
        self._update_index()

        # Write to OpenViking if available
        if self._memory_client:
            try:
                await self._memory_client.store_research(
                    topic=step_result.get("command", "unknown"),
                    findings=text[:2000],
                    agent_name=agent_id,
                    request_id=request_id,
                )
            except Exception as exc:
                logger.warning(
                    "openviking_write_failed", extra={"error": str(exc)},
                )

        # Append to log
        self._append_log(
            campaign_id, step_number, agent_id, len(entities), len(claims),
        )

        duration = time.monotonic() - start

        # Emit DRVP event (best-effort -- event type may not exist yet)
        await self._emit_drvp(
            request_id=request_id,
            agent_id=agent_id,
            campaign_id=campaign_id,
            step_number=step_number,
            entity_count=len(entities),
            claim_count=len(claims),
            page_path=page_path,
            duration=round(duration, 2),
        )

        return {
            "ingested": True,
            "entity_count": len(entities),
            "claim_count": len(claims),
            "page_path": page_path,
            "duration_s": round(duration, 2),
        }

    # ---- Text extraction ----

    @staticmethod
    def _extract_text(output: dict[str, Any]) -> str:
        """Pull the main text content from a step result dict."""
        for key in (
            "text", "content", "raw", "findings",
            "summary", "result", "synthesis",
        ):
            val = output.get(key)
            if isinstance(val, str) and len(val) > 20:
                return val
            if isinstance(val, list):
                joined = " ".join(str(v) for v in val)
                if len(joined) > 20:
                    return joined
        return str(output)[:5000]

    # ---- Entity extraction ----

    @staticmethod
    def _extract_entities(text: str) -> list[dict[str, Any]]:
        """Simple heuristic entity extraction.

        Production version will use Gemma 4 E4B structured output
        via borrowed inference.
        """
        entities: list[dict[str, Any]] = []
        # Chemical formulas (e.g., BMIM-BF4, MoS2, TiO2)
        for match in re.finditer(
            r"\b([A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?(?:\d+)?){1,5})\b", text,
        ):
            name = match.group(1)
            if len(name) >= 3 and any(c.isdigit() for c in name):
                entities.append({"name": name, "type": "compound"})
        # Deduplicate
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for e in entities:
            if e["name"] not in seen:
                seen.add(e["name"])
                unique.append(e)
        return unique[:20]  # Cap at 20

    # ---- Claim extraction ----

    @staticmethod
    def _extract_claims(
        text: str, campaign_id: str, step: int,
    ) -> list[dict[str, Any]]:
        """Extract factual claims from text (sentence-level heuristic)."""
        claims: list[dict[str, Any]] = []
        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 30]
        for sent in sentences[:10]:  # Cap at 10 claims per step
            claim_id = hashlib.sha256(
                f"{campaign_id}:{step}:{sent[:80]}".encode(),
            ).hexdigest()[:16]
            claims.append({
                "id": f"claim_{claim_id}",
                "topic": campaign_id,
                "statement": sent[:500],
                "confidence": 0.5,
                "sources": [f"campaign:{campaign_id}:step:{step}"],
            })
        return claims

    # ---- Wiki page writing ----

    def _write_campaign_page(
        self,
        campaign_id: str,
        step: int,
        text: str,
        entities: list[dict[str, Any]],
        claims: list[dict[str, Any]],
    ) -> str:
        """Write a markdown wiki page for a campaign step."""
        campaigns_dir = self._wiki_dir / "wiki" / "campaigns"
        campaigns_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{campaign_id}-step-{step}.md"
        page_path = campaigns_dir / filename

        entity_links = ", ".join(
            f"[[{e['name']}]]" for e in entities[:10]
        )
        claim_lines = "\n".join(
            f"- {c['statement'][:200]}" for c in claims[:5]
        )
        content = (
            f"# {campaign_id} -- Step {step}\n\n"
            f"## Summary\n{text[:500]}\n\n"
            f"## Entities\n{entity_links or 'No entities extracted'}\n\n"
            f"## Claims\n{claim_lines or 'No claims extracted'}\n\n"
            f"## Metadata\n"
            f"- Campaign: {campaign_id}\n"
            f"- Step: {step}\n"
            f"- Entities: {len(entities)}\n"
            f"- Claims: {len(claims)}\n"
            f"- Ingested: {datetime.now(timezone.utc).isoformat()}\n"
        )
        page_path.write_text(content, encoding="utf-8")
        return str(page_path.relative_to(self._wiki_dir))

    # ---- Index maintenance ----

    def _update_index(self) -> None:
        """Rebuild wiki/index.md from all wiki pages."""
        wiki_dir = self._wiki_dir / "wiki"
        if not wiki_dir.exists():
            return

        sections: dict[str, list[str]] = {
            "entities": [],
            "concepts": [],
            "campaigns": [],
            "lessons": [],
        }
        for subdir_name in sections:
            subdir = wiki_dir / subdir_name
            if subdir.exists():
                for f in sorted(subdir.glob("*.md")):
                    sections[subdir_name].append(
                        f"- [{f.stem}]({subdir_name}/{f.name})",
                    )

        index_lines = [
            "# Wiki Index",
            "",
            f"_Auto-generated at {datetime.now(timezone.utc).isoformat()}_",
            "",
        ]
        for section, entries in sections.items():
            if entries:
                index_lines.append(f"## {section.title()} ({len(entries)})")
                index_lines.extend(entries)
                index_lines.append("")

        stats = self._entity_store.stats()
        index_lines.extend([
            "## Stats",
            f"- Entities: {stats['entities']}",
            f"- Claims: {stats['claims']}",
            f"- Relationships: {stats['relationships']}",
        ])

        (wiki_dir / "index.md").write_text(
            "\n".join(index_lines), encoding="utf-8",
        )

    # ---- Log ----

    def _append_log(
        self,
        campaign_id: str,
        step: int,
        agent: str,
        entities: int,
        claims: int,
    ) -> None:
        """Append an ingestion record to the wiki log."""
        with self._log_path.open("a", encoding="utf-8") as f:
            ts = datetime.now(timezone.utc).isoformat()
            f.write(
                f"- [{ts}] {agent}: ingested {campaign_id} step {step} "
                f"({entities} entities, {claims} claims)\n",
            )

    # ---- DRVP ----

    @staticmethod
    async def _emit_drvp(
        *,
        request_id: str,
        agent_id: str,
        campaign_id: str,
        step_number: int,
        entity_count: int,
        claim_count: int,
        page_path: str,
        duration: float,
    ) -> None:
        """Emit a DRVP knowledge.ingested event (best-effort).

        The KNOWLEDGE_INGESTED event type may not exist in the enum yet,
        so we wrap the entire emit in a try/except and fall back to logging.
        """
        try:
            from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

            event = DRVPEvent(
                event_type=DRVPEventType.KNOWLEDGE_INGESTED,
                request_id=request_id,
                agent_name=agent_id,
                device="leader",
                payload={
                    "campaign_id": campaign_id,
                    "step_number": step_number,
                    "entity_count": entity_count,
                    "claim_count": claim_count,
                    "page_path": page_path,
                    "duration_s": duration,
                },
            )
            await emit(event)
        except (AttributeError, ValueError) as exc:
            logger.info(
                "drvp_knowledge_ingested_skipped",
                extra={
                    "reason": str(exc),
                    "campaign_id": campaign_id,
                    "step_number": step_number,
                },
            )
        except Exception as exc:
            logger.warning(
                "drvp_emit_failed",
                extra={"error": str(exc)},
            )
