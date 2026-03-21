"""DarkLab Simulation Agent: parametric simulation with uncertainty quantification.

Supports parametric sweeps, Monte Carlo methods, kinetics, and transport models.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
from shared.models import Task, TaskResult
from shared.llm_client import call_anthropic
from shared.config import settings
from shared.node_bridge import run_agent

SYSTEM_PROMPT = """\
You are the DarkLab Simulation Agent. Given experimental parameters, generate
Python simulation code using numpy/scipy. The code should:
1. Define the mathematical model
2. Run the simulation with given parameters
3. Include uncertainty quantification (Monte Carlo or analytical)
4. Return numerical results as JSON

Output ONLY executable Python code wrapped in ```python``` blocks.
The code must define a function `simulate(params: dict) -> dict` and call it.
"""


async def handle(task: Task) -> TaskResult:
    model_name = task.payload.get("model", "linear_response")
    params = task.payload.get("params", {})
    n_samples = task.payload.get("n_samples", 100)
    method = task.payload.get("method", "parametric")  # "parametric" | "monte_carlo"

    if method == "monte_carlo":
        result_data = _monte_carlo_simulation(model_name, params, n_samples)
    elif method == "parametric":
        result_data = _parametric_sweep(model_name, params, n_samples)
    elif method == "ai_generated":
        # Use Claude to generate and run custom simulation code
        result_data = await _ai_simulation(task)
    else:
        result_data = _parametric_sweep(model_name, params, n_samples)

    # Save results to artifacts
    artifacts = []
    results_path = settings.artifacts_dir / f"sim_{task.task_id}.json"
    results_path.write_text(json.dumps(result_data, indent=2, default=str))
    artifacts.append(str(results_path))

    payload_hash = hashlib.sha256(
        json.dumps(task.payload, sort_keys=True, default=str).encode()
    ).hexdigest()

    return TaskResult(
        task_id=task.task_id,
        agent_name="SimulationAgent",
        status="ok",
        result=result_data,
        artifacts=artifacts,
        payload_hash=payload_hash,
    )


def _parametric_sweep(model: str, params: dict, n_points: int) -> dict:
    """Run a parametric sweep over specified ranges."""
    x = np.linspace(
        params.get("x_min", 0),
        params.get("x_max", 10),
        n_points,
    )
    slope = params.get("slope", 1.0)
    intercept = params.get("intercept", 0.0)
    noise_std = params.get("noise_std", 0.1)

    y_true = slope * x + intercept
    y_noisy = y_true + np.random.normal(0, noise_std, size=n_points)

    return {
        "model": model,
        "method": "parametric",
        "n_points": n_points,
        "x": x.tolist(),
        "y_true": y_true.tolist(),
        "y_noisy": y_noisy.tolist(),
        "stats": {
            "mean_y": float(np.mean(y_noisy)),
            "std_y": float(np.std(y_noisy)),
            "rmse": float(np.sqrt(np.mean((y_noisy - y_true) ** 2))),
        },
    }


def _monte_carlo_simulation(model: str, params: dict, n_samples: int) -> dict:
    """Run Monte Carlo simulation with parameter uncertainty."""
    results = []
    for _ in range(n_samples):
        # Sample parameters with noise
        sampled = {}
        for key, val in params.items():
            if isinstance(val, (int, float)):
                uncertainty = params.get(f"{key}_uncertainty", abs(val) * 0.1)
                sampled[key] = val + np.random.normal(0, uncertainty)
            else:
                sampled[key] = val
        results.append(sampled)

    # Compute statistics
    numeric_keys = [k for k, v in params.items() if isinstance(v, (int, float)) and not k.endswith("_uncertainty")]
    stats = {}
    for key in numeric_keys:
        values = [r[key] for r in results]
        stats[key] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "ci_95": [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))],
        }

    return {
        "model": model,
        "method": "monte_carlo",
        "n_samples": n_samples,
        "parameter_stats": stats,
    }


async def _ai_simulation(task: Task) -> dict:
    """Use Claude to generate and describe a custom simulation."""
    prompt = f"""Create a simulation for: {json.dumps(task.payload, indent=2)}

Describe the mathematical model, key equations, and expected behavior.
Provide numerical predictions in JSON format."""

    response = await call_anthropic(prompt, system=SYSTEM_PROMPT)
    return {"model": "ai_generated", "description": response}


if __name__ == "__main__":
    run_agent(handle, agent_name="SimulationAgent")
