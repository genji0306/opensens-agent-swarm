# darklab-rl-train

Reinforcement learning training lifecycle management for DarkLab agents.
Controls the OpenClaw-RL training pipeline including baseline management,
training triggers, status monitoring, and rollback.

## Commands

### /rl-status
Show RL training status for all agents.

```
/rl-status
```

Returns: enabled agents, rollout counts, baselines, recent checkpoints.

### /rl-freeze
Freeze current agent behavior as a baseline snapshot before RL training.

```
/rl-freeze research
/rl-freeze all
```

Creates an immutable baseline in `~/.darklab/rl/baselines/` that serves
as the regression check for all future checkpoints.

### /rl-train
Trigger a training cycle for an agent type.

```
/rl-train research
```

Assembles a training batch from live + synthetic rollouts, scores via PRM,
and submits to Tinker cloud for LoRA training.

### /rl-rollback
Disable RL for an agent, reverting to the base model immediately.

```
/rl-rollback research
/rl-rollback all
```

Traffic immediately falls back to the EXECUTION tier (Ollama base model).
Checkpoints are preserved for analysis.

## Requirements

- DARKLAB_RL_ENABLED=true
- DARKLAB_TINKER_API_KEY set (for training)
- Rollout data available in ~/.darklab/rl/rollouts/
