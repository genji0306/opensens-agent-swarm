---
name: darklab-doe
description: Design of Experiments agent -- proposes experimental setups with parameters, ranges, and optimization strategies.
metadata:
  {"openclaw": {"emoji": "test_tube", "requires": {"env": ["ANTHROPIC_API_KEY"]}}}
---

# DarkLab DOE Designer

Designs experimental setups based on research findings. Proposes parameter ranges, measurement protocols, and optimization strategies.

## Capabilities

- Design factorial, fractional factorial, and Bayesian optimization experiments
- Propose parameter ranges based on literature
- Define measurement protocols and success criteria
- Generate Experiment Intent Packages (EIPs) for the Experiment Agent

## Input

Requires research findings from darklab-research or darklab-literature:

```json
{
  "research_plan": "string",
  "target_properties": ["string"],
  "available_instruments": ["string"],
  "constraints": {"budget": "string", "time": "string"}
}
```

## Output: Experiment Intent Package (EIP)

```json
{
  "eip_id": "uuid",
  "objective": "string",
  "method": "string",
  "parameters": [
    {"name": "string", "type": "continuous", "min": 0, "max": 100, "unit": "string"}
  ],
  "measurements": [
    {"technique": "string", "conditions": {}, "expected_range": {}}
  ],
  "sequence": ["step1", "step2"],
  "optimization_strategy": "bayesian",
  "n_initial": 10,
  "n_iterations": 20
}
```
