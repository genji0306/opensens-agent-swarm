"""DarkLab Synthetic Data Agent: generates realistic synthetic datasets.

Creates synthetic data matching expected experimental distributions for
XRD patterns, CV curves, BET surface areas, sensor data, etc.
"""
from __future__ import annotations

import json
import hashlib

import numpy as np
from shared.models import Task, TaskResult
from shared.config import settings
from shared.node_bridge import run_agent


async def handle(task: Task) -> TaskResult:
    data_type = task.payload.get("data_type", "generic")
    n_samples = task.payload.get("n_samples", 100)
    params = task.payload.get("params", {})

    generators = {
        "xrd": _generate_xrd,
        "cv": _generate_cv,
        "bet": _generate_bet,
        "sensor": _generate_sensor,
        "generic": _generate_generic,
    }

    generator = generators.get(data_type, _generate_generic)
    data = generator(n_samples, params)

    # Save to file
    artifacts = []
    output_path = settings.artifacts_dir / f"synthetic_{data_type}_{task.task_id}.json"
    output_path.write_text(json.dumps(data, indent=2, default=str))
    artifacts.append(str(output_path))

    payload_hash = hashlib.sha256(
        json.dumps(task.payload, sort_keys=True, default=str).encode()
    ).hexdigest()

    return TaskResult(
        task_id=task.task_id,
        agent_name="SyntheticDataAgent",
        status="ok",
        result=data,
        artifacts=artifacts,
        payload_hash=payload_hash,
    )


def _generate_xrd(n_samples: int, params: dict) -> dict:
    """Generate synthetic XRD pattern with Gaussian peaks."""
    two_theta = np.linspace(params.get("min_2theta", 10), params.get("max_2theta", 80), n_samples)
    peaks = params.get("peaks", [
        {"position": 28.5, "intensity": 100, "fwhm": 0.5},
        {"position": 37.2, "intensity": 60, "fwhm": 0.4},
        {"position": 42.8, "intensity": 45, "fwhm": 0.6},
    ])

    intensity = np.zeros_like(two_theta)
    for peak in peaks:
        pos, amp, fwhm = peak["position"], peak["intensity"], peak["fwhm"]
        sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))
        intensity += amp * np.exp(-0.5 * ((two_theta - pos) / sigma) ** 2)

    # Add baseline and noise
    baseline = params.get("baseline", 5)
    noise_level = params.get("noise", 2)
    intensity += baseline + np.random.normal(0, noise_level, size=n_samples)
    intensity = np.maximum(intensity, 0)

    return {
        "data_type": "xrd",
        "two_theta": two_theta.tolist(),
        "intensity": intensity.tolist(),
        "peaks": peaks,
        "n_points": n_samples,
    }


def _generate_cv(n_samples: int, params: dict) -> dict:
    """Generate synthetic Cyclic Voltammetry curve."""
    scan_rate = params.get("scan_rate", 50)  # mV/s
    v_min = params.get("v_min", -0.5)
    v_max = params.get("v_max", 1.0)

    # Forward and reverse scans
    v_forward = np.linspace(v_min, v_max, n_samples // 2)
    v_reverse = np.linspace(v_max, v_min, n_samples // 2)
    voltage = np.concatenate([v_forward, v_reverse])

    # Capacitive current + redox peaks
    capacitance = params.get("capacitance", 1e-3)
    i_cap = capacitance * scan_rate / 1000  # A

    current_forward = np.full(n_samples // 2, i_cap)
    current_reverse = np.full(n_samples // 2, -i_cap)

    # Add redox peaks
    e_ox = params.get("e_oxidation", 0.5)
    e_red = params.get("e_reduction", 0.3)
    peak_current = params.get("peak_current", 5e-3)

    current_forward += peak_current * np.exp(-0.5 * ((v_forward - e_ox) / 0.05) ** 2)
    current_reverse -= peak_current * np.exp(-0.5 * ((v_reverse - e_red) / 0.05) ** 2)

    current = np.concatenate([current_forward, current_reverse])
    current += np.random.normal(0, peak_current * 0.02, size=len(current))

    return {
        "data_type": "cv",
        "voltage": voltage.tolist(),
        "current": (current * 1000).tolist(),  # Convert to mA
        "scan_rate_mVs": scan_rate,
        "n_points": len(voltage),
    }


def _generate_bet(n_samples: int, params: dict) -> dict:
    """Generate synthetic BET isotherm data."""
    p_p0 = np.linspace(0.01, 0.99, n_samples)
    surface_area = params.get("surface_area", 150)  # m2/g
    c_constant = params.get("c_constant", 50)
    vm = surface_area / (4.35 * c_constant)

    # BET equation
    quantity = vm * c_constant * p_p0 / ((1 - p_p0) * (1 + (c_constant - 1) * p_p0))
    quantity += np.random.normal(0, vm * 0.02, size=n_samples)
    quantity = np.maximum(quantity, 0)

    return {
        "data_type": "bet",
        "relative_pressure": p_p0.tolist(),
        "quantity_adsorbed": quantity.tolist(),
        "estimated_surface_area_m2g": surface_area,
        "n_points": n_samples,
    }


def _generate_sensor(n_samples: int, params: dict) -> dict:
    """Generate synthetic sensor time-series data."""
    duration = params.get("duration_s", 3600)
    baseline = params.get("baseline", 100)
    drift = params.get("drift_per_hour", 0.5)
    noise = params.get("noise_std", 2)

    t = np.linspace(0, duration, n_samples)
    signal = baseline + drift * (t / 3600)

    # Add events (step changes)
    events = params.get("events", [
        {"time": 600, "magnitude": 20, "duration": 300},
        {"time": 1800, "magnitude": -10, "duration": 200},
    ])
    for event in events:
        mask = (t >= event["time"]) & (t <= event["time"] + event["duration"])
        signal[mask] += event["magnitude"]

    signal += np.random.normal(0, noise, size=n_samples)

    return {
        "data_type": "sensor",
        "time_s": t.tolist(),
        "signal": signal.tolist(),
        "events": events,
        "n_points": n_samples,
    }


def _generate_generic(n_samples: int, params: dict) -> dict:
    """Generate generic multivariate data."""
    n_features = params.get("n_features", 5)
    means = params.get("means", np.zeros(n_features).tolist())
    stds = params.get("stds", np.ones(n_features).tolist())

    data = {}
    for i in range(n_features):
        col_name = f"feature_{i}"
        mean = means[i] if i < len(means) else 0
        std = stds[i] if i < len(stds) else 1
        data[col_name] = np.random.normal(mean, std, size=n_samples).tolist()

    return {
        "data_type": "generic",
        "data": data,
        "n_samples": n_samples,
        "n_features": n_features,
    }


if __name__ == "__main__":
    run_agent(handle, agent_name="SyntheticDataAgent")
