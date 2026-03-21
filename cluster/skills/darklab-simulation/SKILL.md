---
name: darklab-simulation
description: Parametric simulation, Monte Carlo models, and physics-based simulations using Python compute stack.
metadata:
  {"openclaw": {"emoji": "gear", "requires": {"env": ["ANTHROPIC_API_KEY"], "bins": ["python3"]}}}
---

# DarkLab Simulation Agent

Creates and runs computational simulations based on experimental designs from the Academic Agent.

## Capabilities

- Parametric sweeps across experimental parameter spaces
- Monte Carlo uncertainty quantification
- Physics-based models (reaction kinetics, transport phenomena)
- Sensitivity analysis
- Model validation against known data

## Supported Simulation Types

| Type | Description | Libraries |
|------|-------------|-----------|
| parametric | Sweep parameter ranges | numpy, scipy |
| monte_carlo | Stochastic sampling | numpy, scipy.stats |
| kinetic | Reaction rate modeling | scipy.integrate |
| transport | Mass/heat transfer | scipy, numpy |
| optimization | Response surface | scipy.optimize |

## Input (from EIP)

```json
{
  "model_type": "parametric",
  "parameters": [
    {"name": "temperature", "min": 25, "max": 200, "steps": 20, "unit": "C"}
  ],
  "model_equation": "arrhenius",
  "n_samples": 1000
}
```

## Output

```json
{
  "status": "complete",
  "results": {
    "parameter_grid": {},
    "response_surface": {},
    "statistics": {"mean": 0, "std": 0, "ci_95": [0, 0]},
    "sensitivity": {"param1": 0.75, "param2": 0.25}
  },
  "artifacts": ["simulation_data.json", "figures/response_surface.png"]
}
```

## Running

Simulations execute in the Python venv at `~/.darklab/venv` with numpy, scipy, pandas, matplotlib, and scikit-learn available.
