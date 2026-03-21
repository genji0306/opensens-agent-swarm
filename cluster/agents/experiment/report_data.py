"""DarkLab Report Data Agent: publication-quality figures and data tables.

Generates matplotlib/plotly visualizations and formatted data tables
for inclusion in research reports and papers.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

from shared.models import Task, TaskResult
from shared.config import settings
from shared.node_bridge import run_agent


async def handle(task: Task) -> TaskResult:
    data = task.payload.get("data", {})
    plot_type = task.payload.get("plot_type", "auto")
    title = task.payload.get("title", "")
    output_format = task.payload.get("format", "png")

    if not data:
        return TaskResult(
            task_id=task.task_id,
            agent_name="ReportDataAgent",
            status="error",
            result={"error": "No data provided."},
        )

    artifacts = []
    result_data: dict = {"plots": [], "tables": []}

    # Generate plot
    fig_path = _generate_plot(data, plot_type, title, task.task_id, output_format)
    if fig_path:
        artifacts.append(str(fig_path))
        result_data["plots"].append({
            "path": str(fig_path),
            "type": plot_type,
            "title": title,
        })

    # Generate summary table
    table = _generate_table(data)
    if table:
        table_path = settings.artifacts_dir / f"table_{task.task_id}.json"
        table_path.write_text(json.dumps(table, indent=2, default=str))
        artifacts.append(str(table_path))
        result_data["tables"].append(table)

    payload_hash = hashlib.sha256(
        json.dumps(task.payload, sort_keys=True, default=str).encode()
    ).hexdigest()

    return TaskResult(
        task_id=task.task_id,
        agent_name="ReportDataAgent",
        status="ok",
        result=result_data,
        artifacts=artifacts,
        payload_hash=payload_hash,
    )


def _generate_plot(
    data: dict, plot_type: str, title: str, task_id: str, fmt: str
) -> Path | None:
    fig_dir = settings.artifacts_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig_path = fig_dir / f"fig_{task_id}.{fmt}"

    try:
        fig, ax = plt.subplots(figsize=(8, 6))

        if plot_type == "xy" or ("x" in data and "y" in data):
            x = np.array(data["x"])
            y = np.array(data.get("y", data.get("y_noisy", [])))
            ax.plot(x, y, "b-", linewidth=1.5)
            if "y_true" in data:
                ax.plot(x, np.array(data["y_true"]), "r--", linewidth=1, alpha=0.7, label="True")
                ax.legend()
            ax.set_xlabel(data.get("x_label", "X"))
            ax.set_ylabel(data.get("y_label", "Y"))

        elif plot_type == "xrd" or data.get("data_type") == "xrd":
            two_theta = np.array(data["two_theta"])
            intensity = np.array(data["intensity"])
            ax.plot(two_theta, intensity, "b-", linewidth=1)
            ax.set_xlabel("2θ (degrees)")
            ax.set_ylabel("Intensity (a.u.)")

        elif plot_type == "cv" or data.get("data_type") == "cv":
            voltage = np.array(data["voltage"])
            current = np.array(data["current"])
            ax.plot(voltage, current, "b-", linewidth=1.5)
            ax.set_xlabel("Potential (V)")
            ax.set_ylabel("Current (mA)")

        elif plot_type == "histogram":
            values = np.array(data.get("values", data.get("signal", [])))
            ax.hist(values, bins=data.get("bins", 30), edgecolor="black", alpha=0.7)
            ax.set_xlabel(data.get("x_label", "Value"))
            ax.set_ylabel("Count")

        else:
            # Auto-detect: plot first two numeric arrays found
            arrays = {k: v for k, v in data.items() if isinstance(v, list) and all(isinstance(i, (int, float)) for i in v[:5])}
            keys = list(arrays.keys())[:2]
            if len(keys) >= 2:
                ax.plot(arrays[keys[0]], arrays[keys[1]], "b-", linewidth=1.5)
                ax.set_xlabel(keys[0])
                ax.set_ylabel(keys[1])
            elif len(keys) == 1:
                ax.plot(arrays[keys[0]], "b-", linewidth=1.5)
                ax.set_ylabel(keys[0])

        ax.set_title(title or "DarkLab Analysis")
        fig.tight_layout()
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return fig_path

    except Exception as e:
        plt.close("all")
        return None


def _generate_table(data: dict) -> dict | None:
    """Generate a summary statistics table from the data."""
    try:
        # Find numeric arrays in data
        numeric_data = {}
        for key, val in data.items():
            if isinstance(val, list) and len(val) > 0 and isinstance(val[0], (int, float)):
                arr = np.array(val)
                numeric_data[key] = {
                    "count": len(arr),
                    "mean": float(np.mean(arr)),
                    "std": float(np.std(arr)),
                    "min": float(np.min(arr)),
                    "max": float(np.max(arr)),
                    "median": float(np.median(arr)),
                }

        if numeric_data:
            return {"type": "summary_statistics", "columns": numeric_data}
    except Exception:
        pass
    return None


if __name__ == "__main__":
    run_agent(handle, agent_name="ReportDataAgent")
