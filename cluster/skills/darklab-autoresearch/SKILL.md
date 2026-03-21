---
name: darklab-autoresearch
description: Autonomous ML experimentation loop on Apple Silicon MPS. Proposes, runs, and evaluates ML training experiments using Karpathy's autoresearch pattern.
metadata:
  {"openclaw": {"emoji": "robot_face", "requires": {"env": ["ANTHROPIC_API_KEY"], "bins": ["python3", "git"]}}}
---

# DarkLab AutoResearch Agent

Autonomous ML experimentation engine based on Karpathy's autoresearch-macos,
adapted for the DarkLab cluster on Apple Silicon (MPS backend).

## Workflow

1. Receive a research protocol (`program.md`) and initial training script (`train.py`)
2. Initialize git-tracked experiment workspace
3. Loop: read state → propose experiment → modify train.py → commit → train → evaluate → keep/revert
4. Track all experiments in `results.tsv` with metrics
5. Return best configuration, training curves, and git history

## Input

```json
{
  "program_md": "string (research protocol guiding the agent)",
  "train_py": "string (initial training script)",
  "max_iterations": 20,
  "time_limit_min": 5,
  "workspace": "optional workspace name"
}
```

## Output

```json
{
  "status": "completed",
  "best_metric": 0.89,
  "experiments": [{"commit": "a1b2c3d", "val_bpb": 0.997, "status": "keep"}],
  "git_log": "string",
  "stdout_tail": "string"
}
```

## Constraints

- Single-instance only (lock file prevents MPS memory contention)
- Runs on Experiment Agent devices with Apple Silicon
- Requires PyTorch with MPS backend
- Each experiment trains for `time_limit_min` minutes wall-clock

## Example

```
/autoresearch --program "Minimize val_bpb on nanochat. Try attention variants." --iterations 10
```
