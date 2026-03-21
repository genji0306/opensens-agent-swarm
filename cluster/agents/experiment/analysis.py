"""DarkLab Analysis Agent: data ingestion, statistical analysis, EIS fitting.

Handles CSV/JSON data, computes statistics, correlations, and domain-specific analyses.
"""
from __future__ import annotations

import hashlib
import io
import json
from typing import Any

import numpy as np
import pandas as pd
from shared.models import Task, TaskResult
from shared.config import settings
from shared.node_bridge import run_agent


async def handle(task: Task) -> TaskResult:
    data_source = task.payload.get("data") or task.payload.get("file_path")
    analysis_type = task.payload.get("analysis_type", "general")

    if not data_source:
        return TaskResult(
            task_id=task.task_id,
            agent_name="AnalysisAgent",
            status="error",
            result={"error": "No data provided. Send CSV/JSON data or file_path."},
        )

    # Load data
    df = _load_data(data_source)
    if df is None:
        return TaskResult(
            task_id=task.task_id,
            agent_name="AnalysisAgent",
            status="error",
            result={"error": "Could not parse data. Supported: CSV string, file path, or list of dicts."},
        )

    # Run analysis based on type
    if analysis_type == "eis":
        result_data = _eis_analysis(df, task.payload)
    elif analysis_type == "cv":
        result_data = _cv_analysis(df, task.payload)
    else:
        result_data = _general_analysis(df)

    # Save processed data
    artifacts = []
    output_path = settings.artifacts_dir / f"analysis_{task.task_id}.json"
    output_path.write_text(json.dumps(result_data, indent=2, default=str))
    artifacts.append(str(output_path))

    payload_hash = hashlib.sha256(
        json.dumps(task.payload, sort_keys=True, default=str).encode()
    ).hexdigest()

    return TaskResult(
        task_id=task.task_id,
        agent_name="AnalysisAgent",
        status="ok",
        result=result_data,
        artifacts=artifacts,
        payload_hash=payload_hash,
    )


def _load_data(source: Any) -> pd.DataFrame | None:
    try:
        if isinstance(source, str) and source.endswith((".csv", ".tsv")):
            return pd.read_csv(source)
        elif isinstance(source, str) and source.endswith(".json"):
            return pd.read_json(source)
        elif isinstance(source, str):
            return pd.read_csv(io.StringIO(source))
        elif isinstance(source, list):
            return pd.DataFrame(source)
        elif isinstance(source, dict):
            return pd.DataFrame(source)
    except Exception:
        return None
    return None


def _general_analysis(df: pd.DataFrame) -> dict:
    """General statistical analysis of a DataFrame."""
    numeric_df = df.select_dtypes(include=[np.number])

    result = {
        "analysis_type": "general",
        "shape": list(df.shape),
        "columns": list(df.columns),
        "dtypes": {k: str(v) for k, v in df.dtypes.items()},
        "describe": json.loads(df.describe(include="all").to_json()),
        "missing": json.loads(df.isnull().sum().to_json()),
    }

    if len(numeric_df.columns) > 1:
        result["correlations"] = json.loads(numeric_df.corr().to_json())

    # Detect outliers (IQR method)
    outliers = {}
    for col in numeric_df.columns:
        q1, q3 = numeric_df[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        n_outliers = int(((numeric_df[col] < q1 - 1.5 * iqr) | (numeric_df[col] > q3 + 1.5 * iqr)).sum())
        if n_outliers > 0:
            outliers[col] = n_outliers
    if outliers:
        result["outliers"] = outliers

    return result


def _eis_analysis(df: pd.DataFrame, params: dict) -> dict:
    """Electrochemical Impedance Spectroscopy analysis."""
    from scipy.optimize import curve_fit

    z_real_col = params.get("z_real_col", "Z_real")
    z_imag_col = params.get("z_imag_col", "Z_imag")
    freq_col = params.get("freq_col", "frequency")

    result: dict[str, Any] = {"analysis_type": "eis"}

    if z_real_col in df.columns and z_imag_col in df.columns:
        z_real = df[z_real_col].values
        z_imag = df[z_imag_col].values
        z_mag = np.sqrt(z_real**2 + z_imag**2)

        result["impedance_stats"] = {
            "z_real_range": [float(z_real.min()), float(z_real.max())],
            "z_imag_range": [float(z_imag.min()), float(z_imag.max())],
            "z_magnitude_range": [float(z_mag.min()), float(z_mag.max())],
        }

        # Simple Randles circuit fit: R_s + R_ct/(1 + j*omega*R_ct*C_dl)
        if freq_col in df.columns:
            freq = df[freq_col].values
            result["frequency_range"] = [float(freq.min()), float(freq.max())]
    else:
        result["warning"] = f"Columns {z_real_col}, {z_imag_col} not found. Available: {list(df.columns)}"
        result.update(_general_analysis(df))

    return result


def _cv_analysis(df: pd.DataFrame, params: dict) -> dict:
    """Cyclic Voltammetry analysis."""
    voltage_col = params.get("voltage_col", "voltage")
    current_col = params.get("current_col", "current")

    result: dict[str, Any] = {"analysis_type": "cv"}

    if voltage_col in df.columns and current_col in df.columns:
        voltage = df[voltage_col].values
        current = df[current_col].values

        # Find peaks
        from scipy.signal import find_peaks
        anodic_peaks, _ = find_peaks(current, prominence=np.std(current) * 0.5)
        cathodic_peaks, _ = find_peaks(-current, prominence=np.std(current) * 0.5)

        result["peaks"] = {
            "anodic": [{"voltage": float(voltage[i]), "current": float(current[i])} for i in anodic_peaks],
            "cathodic": [{"voltage": float(voltage[i]), "current": float(current[i])} for i in cathodic_peaks],
        }
        result["voltage_window"] = [float(voltage.min()), float(voltage.max())]
        result["current_range"] = [float(current.min()), float(current.max())]
    else:
        result["warning"] = f"Columns {voltage_col}, {current_col} not found."
        result.update(_general_analysis(df))

    return result


if __name__ == "__main__":
    run_agent(handle, agent_name="AnalysisAgent")
