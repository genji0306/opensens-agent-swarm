"""Eval runner -- loads golden set, scores outputs, reports results.

Usage::

    runner = EvalRunner(golden_dir="core/tests/eval_golden")
    results = runner.run_all(outputs_by_task_id={...})
    report = runner.report(results)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from oas_core.eval.scorer import EvalScorer, ScoringResult

logger = logging.getLogger("oas.eval.runner")

__all__ = ["EvalRunner", "EvalReport"]


class EvalReport:
    """Summary of an eval run."""

    def __init__(
        self, results: list[ScoringResult], config_hash: str = ""
    ) -> None:
        self.results = tuple(results)
        self.config_hash = config_hash

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def avg_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.weighted_average for r in self.results) / len(
            self.results
        )

    @property
    def per_dimension(self) -> dict[str, float]:
        if not self.results:
            return {}
        dim_totals: dict[str, list[float]] = {}
        for r in self.results:
            for d in r.dimension_scores:
                dim_totals.setdefault(d.name, []).append(d.score)
        return {
            name: sum(scores) / len(scores)
            for name, scores in dim_totals.items()
        }

    @property
    def per_task_type(self) -> dict[str, float]:
        if not self.results:
            return {}
        type_totals: dict[str, list[float]] = {}
        for r in self.results:
            type_totals.setdefault(r.task_type, []).append(r.weighted_average)
        return {
            tt: sum(scores) / len(scores)
            for tt, scores in type_totals.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "avg_score": round(self.avg_score, 2),
            "per_dimension": {
                k: round(v, 2) for k, v in self.per_dimension.items()
            },
            "per_task_type": {
                k: round(v, 2) for k, v in self.per_task_type.items()
            },
            "config_hash": self.config_hash,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Eval Report",
            f"Config: `{self.config_hash}`",
            f"**{self.passed}/{self.total} passed** (avg: {self.avg_score:.2f}/5.0)",
            "",
            "## Per Dimension",
        ]
        for name, avg in sorted(self.per_dimension.items()):
            lines.append(f"- **{name}**: {avg:.2f}/5.0")
        lines.append("")
        lines.append("## Per Task Type")
        for tt, avg in sorted(self.per_task_type.items()):
            lines.append(f"- **{tt}**: {avg:.2f}/5.0")
        lines.append("")
        lines.append("## Failed Tasks")
        for r in self.results:
            if not r.passed:
                lines.append(
                    f"- `{r.task_id}` ({r.task_type}): "
                    f"{r.weighted_average:.2f} -- {r.feedback}"
                )
        return "\n".join(lines)


class EvalRunner:
    """Loads golden set fixtures and scores agent outputs."""

    def __init__(
        self,
        *,
        golden_dir: str | Path,
        scorer: EvalScorer | None = None,
    ) -> None:
        self._golden_dir = Path(golden_dir)
        self._scorer = scorer or EvalScorer()
        self._golden_set: list[dict[str, Any]] = []

    @property
    def golden_set(self) -> list[dict[str, Any]]:
        return list(self._golden_set)

    def load_golden_set(self) -> list[dict[str, Any]]:
        """Load all YAML fixtures from golden_dir."""
        self._golden_set = []
        if not self._golden_dir.exists():
            logger.warning(
                "golden_dir_missing",
                extra={"path": str(self._golden_dir)},
            )
            return self._golden_set

        for yaml_file in sorted(self._golden_dir.glob("*.yaml")):
            try:
                with yaml_file.open("r") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    data.setdefault("task_id", yaml_file.stem)
                    self._golden_set.append(data)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            item.setdefault(
                                "task_id",
                                f"{yaml_file.stem}_{len(self._golden_set)}",
                            )
                            self._golden_set.append(item)
            except Exception as exc:
                logger.warning(
                    "golden_set_load_error",
                    extra={"file": str(yaml_file), "error": str(exc)},
                )

        logger.info(
            "golden_set_loaded",
            extra={"count": len(self._golden_set)},
        )
        return self._golden_set

    def score_output(
        self,
        task_id: str,
        output: dict[str, Any],
        cost_usd: float = 0.0,
    ) -> ScoringResult | None:
        """Score a single output against its golden set entry."""
        task = next(
            (t for t in self._golden_set if t["task_id"] == task_id), None
        )
        if task is None:
            logger.warning(
                "task_not_found", extra={"task_id": task_id}
            )
            return None

        return self._scorer.score(
            task_id=task_id,
            task_type=task.get("task_type", "unknown"),
            output=output,
            ground_truth=task.get("ground_truth", {}),
            cost_usd=cost_usd,
        )

    def run_all(
        self,
        outputs_by_task_id: dict[str, dict[str, Any]],
        costs_by_task_id: dict[str, float] | None = None,
        config_hash: str = "",
    ) -> EvalReport:
        """Score all outputs against the golden set and return a report."""
        if not self._golden_set:
            self.load_golden_set()

        results: list[ScoringResult] = []
        costs = costs_by_task_id or {}

        for task in self._golden_set:
            tid = task["task_id"]
            if tid in outputs_by_task_id:
                result = self.score_output(
                    tid, outputs_by_task_id[tid], costs.get(tid, 0.0)
                )
                if result is not None:
                    results.append(result)

        report = EvalReport(results, config_hash=config_hash)
        logger.info(
            "eval_run_complete",
            extra={
                "total": report.total,
                "passed": report.passed,
                "avg_score": round(report.avg_score, 2),
            },
        )
        return report
