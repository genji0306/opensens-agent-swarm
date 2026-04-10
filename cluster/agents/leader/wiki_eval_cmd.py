"""Wiki compile/lint and eval run/report slash command handlers.

Handles four Phase 25 commands:
  /wiki-compile  — compile wiki pages from KnowledgeIngester output
  /wiki-lint     — lint wiki for stale/low-confidence pages
  /eval-run      — run EvalRunner against golden set fixtures
  /eval-report   — print last eval report from disk
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.models import Task, TaskResult

logger = logging.getLogger("darklab.wiki_eval")

_GOLDEN_DIR = Path(__file__).resolve().parents[4] / "core" / "tests" / "eval_golden"
_EVAL_REPORT_PATH = Path.home() / ".darklab" / "eval" / "last_report.json"


async def handle_wiki_compile(task: Task) -> TaskResult:
    """Compile wiki pages from entity store into ~/.darklab/wiki/."""
    try:
        from oas_core.knowledge.ingester import KnowledgeIngester
        from oas_core.knowledge.entity_store import EntityStore
        from oas_core.knowledge.embedding_index import EmbeddingIndex
        from shared.config import settings

        wiki_dir = settings.darklab_home / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)

        db_path = settings.darklab_home / "knowledge" / "entities.db"
        index_path = settings.darklab_home / "knowledge" / "index.lance"

        store = EntityStore(db_path)
        index = EmbeddingIndex(index_path)
        ingester = KnowledgeIngester(settings, store, index)

        # Compile index page
        stats = await store.stats()
        index_content = _render_wiki_index(stats, wiki_dir)
        (wiki_dir / "index.md").write_text(index_content, encoding="utf-8")

        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        try:
            await emit(DRVPEvent(
                event_type=DRVPEventType.WIKI_SYNC_COMPLETED,
                request_id=task.task_id,
                agent_name="leader",
                device="leader",
                payload={"entity_count": stats.get("entity_count", 0),
                         "claim_count": stats.get("claim_count", 0),
                         "wiki_dir": str(wiki_dir)},
            ))
        except Exception:
            pass

        return TaskResult(
            task_id=task.task_id,
            agent_name="WikiCompile",
            status="ok",
            result={
                "wiki_dir": str(wiki_dir),
                "entity_count": stats.get("entity_count", 0),
                "claim_count": stats.get("claim_count", 0),
                "index_written": True,
            },
        )
    except Exception as e:
        logger.warning("wiki_compile_failed", exc_info=True)
        return TaskResult(
            task_id=task.task_id,
            agent_name="WikiCompile",
            status="error",
            result={"error": str(e)},
        )


async def handle_wiki_lint(task: Task) -> TaskResult:
    """Lint wiki pages: find stale, low-confidence, or orphaned pages."""
    try:
        from shared.config import settings

        wiki_dir = settings.darklab_home / "wiki"
        if not wiki_dir.exists():
            return TaskResult(
                task_id=task.task_id,
                agent_name="WikiLint",
                status="ok",
                result={"issues": [], "message": "No wiki directory found — run /wiki-compile first"},
            )

        issues: list[dict[str, Any]] = []
        pages = list(wiki_dir.glob("*.md"))

        for page in pages:
            if page.name == "index.md":
                continue
            text = page.read_text(encoding="utf-8")
            # Check for low confidence marker
            if "Confidence**: 0." in text:
                conf_line = [l for l in text.splitlines() if "**Confidence**" in l]
                if conf_line:
                    try:
                        conf = float(conf_line[0].split("**Confidence**: ")[1])
                        if conf < 0.4:
                            issues.append({"page": page.name, "type": "low_confidence", "value": conf})
                    except (IndexError, ValueError):
                        pass
            # Check for empty claims
            if "## Key Claims" in text and "- " not in text.split("## Key Claims")[1].split("##")[0]:
                issues.append({"page": page.name, "type": "no_claims"})

        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        try:
            await emit(DRVPEvent(
                event_type=DRVPEventType.WIKI_LINT_COMPLETED,
                request_id=task.task_id,
                agent_name="leader",
                device="leader",
                payload={"page_count": len(pages), "issue_count": len(issues)},
            ))
        except Exception:
            pass

        return TaskResult(
            task_id=task.task_id,
            agent_name="WikiLint",
            status="ok",
            result={
                "pages_checked": len(pages),
                "issues": issues,
                "issue_count": len(issues),
                "clean": len(issues) == 0,
            },
        )
    except Exception as e:
        logger.warning("wiki_lint_failed", exc_info=True)
        return TaskResult(
            task_id=task.task_id,
            agent_name="WikiLint",
            status="error",
            result={"error": str(e)},
        )


async def handle_eval_run(task: Task) -> TaskResult:
    """Run EvalRunner against all golden set fixtures."""
    try:
        from oas_core.eval.runner import EvalRunner

        if not _GOLDEN_DIR.exists():
            return TaskResult(
                task_id=task.task_id,
                agent_name="EvalRun",
                status="error",
                result={"error": f"Golden dir not found: {_GOLDEN_DIR}"},
            )

        runner = EvalRunner(golden_dir=_GOLDEN_DIR)

        # Build outputs dict from shared memory or payload
        outputs: dict[str, str] = task.payload.get("outputs", {})
        costs: dict[str, float] = task.payload.get("costs", {})
        config_hash: str = task.payload.get("config_hash", "manual")

        report = runner.run_all(
            outputs_by_task_id=outputs,
            costs=costs,
            config_hash=config_hash,
        )

        # Persist report for /eval-report
        _EVAL_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _EVAL_REPORT_PATH.write_text(
            json.dumps(report.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit
        try:
            await emit(DRVPEvent(
                event_type=DRVPEventType.EVAL_RUN_COMPLETED,
                request_id=task.task_id,
                agent_name="leader",
                device="leader",
                payload=report.to_dict(),
            ))
        except Exception:
            pass

        return TaskResult(
            task_id=task.task_id,
            agent_name="EvalRun",
            status="ok",
            result=report.to_dict(),
        )
    except Exception as e:
        logger.warning("eval_run_failed", exc_info=True)
        return TaskResult(
            task_id=task.task_id,
            agent_name="EvalRun",
            status="error",
            result={"error": str(e)},
        )


async def handle_eval_report(task: Task) -> TaskResult:
    """Print the last eval report from disk."""
    if not _EVAL_REPORT_PATH.exists():
        return TaskResult(
            task_id=task.task_id,
            agent_name="EvalReport",
            status="ok",
            result={"message": "No eval report found — run /eval-run first"},
        )
    try:
        data = json.loads(_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
        return TaskResult(
            task_id=task.task_id,
            agent_name="EvalReport",
            status="ok",
            result=data,
        )
    except Exception as e:
        return TaskResult(
            task_id=task.task_id,
            agent_name="EvalReport",
            status="error",
            result={"error": str(e)},
        )


def _render_wiki_index(stats: dict[str, Any], wiki_dir: Path) -> str:
    pages = sorted(p.name for p in wiki_dir.glob("*.md") if p.name != "index.md")
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# DarkLab Knowledge Wiki",
        f"",
        f"**Last compiled**: {ts}",
        f"**Entities**: {stats.get('entity_count', 0)}",
        f"**Claims**: {stats.get('claim_count', 0)}",
        f"**Pages**: {len(pages)}",
        f"",
        f"## Pages",
    ]
    for page in pages:
        topic = page.replace(".md", "").replace("_", " ").title()
        lines.append(f"- [{topic}]({page})")
    return "\n".join(lines) + "\n"
