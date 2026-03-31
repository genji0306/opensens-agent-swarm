# OpenClaw-RL + MiroShark Integration Plan

## Executive Summary

This document defines the strategy for integrating **OpenClaw-RL** (ambient RL training from live conversations) and **MiroShark** (multi-agent simulation for synthetic debate generation) into the Opensens Agent Swarm (OAS). The goal is to enable every DarkLab agent to self-evolve through reinforcement learning while preserving safe rollback to baseline versions.

The architecture works in three interconnected loops:

1. **Ambient RL Loop** -- OpenClaw-RL intercepts live agent conversations via an API proxy, scores turns using a Process Reward Model (PRM), and trains the underlying policy model in the background. Agents continue serving requests without interruption.

2. **Synthetic Debate Loop** -- MiroShark generates structured multi-agent debates on scientific topics, producing high-quality training trajectories with natural adversarial signals. These transcripts feed into OpenClaw-RL as additional training data.

3. **Evaluation Gate** -- Before any trained checkpoint is promoted to production, it passes through the existing OAS evaluation pipeline (`core/oas_core/evaluation.py`) extended with RL-specific metrics, plus MiroShark-generated adversarial stress tests.

The primary constraint is that the DarkLab cluster runs on Mac minis without discrete GPUs. This means all RL training must happen either on Tinker cloud (LoRA-based, zero local GPU), on a rented GPU node, or on the local Ollama instance for inference-only evaluation. The plan accounts for this by separating the training plane (cloud) from the serving plane (local).

---

## Architecture Overview

```
                                    TRAINING PLANE (Tinker Cloud / GPU Node)
                                    ========================================

                            +-------------------+       +-----------------+
                            | OpenClaw-RL       |       | Slime/Megatron  |
                            | Tinker Trainer    |<----->| Policy Gradient |
                            | (LoRA fine-tune)  |       | Optimizer       |
                            +--------^----------+       +-----------------+
                                     |
                                     | Scored rollouts
                                     | (conversation trajectories + PRM rewards)
                                     |
            +------------------------+-------------------------+
            |                                                  |
            |                                                  |
    +-------+--------+                              +----------+---------+
    | Live Rollouts  |                              | Synthetic Rollouts |
    | (from agents)  |                              | (from MiroShark)   |
    +-------^--------+                              +----------^---------+
            |                                                  |
============|==================================================|===============
            |           SERVING PLANE (Leader Mac mini)         |
            |           ====================================    |
            |                                                   |
    +-------+--------+     +------------------+     +-----------+---------+
    | OpenClaw-RL    |     | LiteLLM :4000    |     | MiroShark           |
    | API Proxy      |<--->| (routing layer)  |     | Simulation Engine   |
    | :30000         |     |                  |     | (Neo4j + OASIS)     |
    +-------^--------+     +--------^---------+     +-----------+---------+
            |                       |                           |
            |              +--------+---------+                 |
            |              | Model Router     |                 |
            |              | (model_router.py)|                 |
            |              | +RL_EVOLVED tier |                 |
            |              +--------^---------+                 |
            |                       |                           |
    +-------+--------+     +--------+---------+     +-----------+---------+
    | Leader         |     | Dispatch         |     | /debate command      |
    | Dispatch       |<--->| (dispatch.py)    |<--->| (new slash command)  |
    | Middleware      |     +--------+---------+     +---------------------+
    | Pipeline       |              |
    +----------------+     +--------+---------+
                           | Campaign Engine  |
                           | (campaign.py)    |
                           +------------------+


    CHECKPOINT MANAGEMENT
    =====================

    ~/.darklab/rl/
    +-- baselines/              # Frozen pre-RL snapshots
    |   +-- research-v0/        # Per-agent baseline
    |   +-- literature-v0/
    |   +-- ...
    +-- checkpoints/            # Training checkpoints (LoRA adapters)
    |   +-- research-ckpt-001/
    |   +-- research-ckpt-002/
    |   +-- ...
    +-- promoted/               # Currently active RL-trained adapters
    |   +-- research-latest -> ../checkpoints/research-ckpt-002
    |   +-- ...
    +-- rollouts/               # Conversation trajectory storage
    |   +-- live/               # From real agent conversations
    |   +-- synthetic/          # From MiroShark debates
    +-- evaluations/            # Checkpoint evaluation scores
        +-- research-ckpt-001.json
        +-- research-ckpt-002.json
```

---

## Part 1: OpenClaw-RL as Core RL Framework

### 1.1 How It Works Within OAS

OpenClaw-RL's architecture has four async components that map onto OAS as follows:

| OpenClaw-RL Component | OAS Mapping | Location |
|---|---|---|
| Agent serving (SGLang) | Ollama llama3.1:8b (or Qwen3-4B via Tinker) | Leader :11434 or Tinker cloud |
| Rollout collection | New `RolloutCollector` middleware in OAS pipeline | `core/oas_core/middleware/rl_rollout.py` |
| PRM/Judge evaluation | PRM model hosted on Tinker or cloud GPU | Tinker API |
| Policy training | Tinker LoRA trainer or remote GPU node | Tinker cloud |

The key insight: OAS already routes all LLM calls through `model_router.py` and `shared/llm_client.py`. By inserting an OpenClaw-RL-compatible API proxy between the model router and the actual model endpoint, every agent conversation becomes a training signal without changing any agent code.

### 1.2 Integration Architecture

```
Agent Request Flow (with RL interception):

  dispatch.py
      |
      v
  model_router.py  -- classifies tier (PLANNING / EXECUTION / BOOST / RL_EVOLVED)
      |
      v
  llm_client.py  -- calls LiteLLM proxy
      |
      v
  LiteLLM :4000  -- routes to appropriate backend
      |
      +---> Anthropic (PLANNING tier)
      +---> Ollama :11434 (EXECUTION tier)
      +---> AIClient (BOOST tier)
      +---> OpenClaw-RL Proxy :30000 (RL_EVOLVED tier)  <-- NEW
                |
                +---> Tinker cloud model (LoRA-adapted policy)
                |
                +---> [side channel] Rollout collector
                        |
                        v
                    Scored samples --> Tinker trainer
```

### 1.3 New Model Tier: RL_EVOLVED

Add a fourth tier to `model_router.py` that routes eligible tasks through the OpenClaw-RL proxy when an evolved checkpoint exists and passes the quality gate.

```python
# In core/oas_core/model_router.py

class ModelTier(str, Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    BOOST = "boost"
    RL_EVOLVED = "rl_evolved"  # NEW: RL-trained model via OpenClaw-RL proxy
```

The router checks whether an RL-evolved model is available and its evaluation score exceeds the minimum threshold before routing to it. Fallback order: `RL_EVOLVED -> BOOST -> EXECUTION`.

### 1.4 Rollout Collection Middleware

A new middleware module (`core/oas_core/middleware/rl_rollout.py`) intercepts conversations and formats them as OpenClaw-RL-compatible rollout sessions.

Responsibilities:
- Tag each conversation with `session_id` (maps to OAS `request_id`), `turn_type` (`main` vs `side`), and agent identity
- Forward the session metadata as HTTP headers (`X-Session-Id`, `X-Turn-Type`, `X-Session-Done`) matching the OpenClaw-RL extension protocol
- Write completed sessions to `~/.darklab/rl/rollouts/live/` as JSONL
- Emit DRVP events: `rl.rollout.collected`, `rl.training.step`, `rl.checkpoint.saved`

### 1.5 Per-Agent Training Isolation

Each of the 16 agent types gets its own LoRA adapter, trained on conversations specific to that agent's task type. This prevents cross-contamination (research agent learning simulation patterns).

Mapping from `TaskType` to LoRA adapter:

| TaskType | LoRA Adapter Name | Base Model |
|---|---|---|
| RESEARCH | `research-lora` | Qwen3-4B |
| LITERATURE | `literature-lora` | Qwen3-4B |
| DOE | `doe-lora` | Qwen3-4B |
| SIMULATE | `simulate-lora` | Qwen3-4B |
| ANALYZE | `analyze-lora` | Qwen3-4B |
| ... | ... | ... |

The OpenClaw-RL proxy selects the correct LoRA adapter based on the `X-Agent-Name` header injected by the rollout middleware.

### 1.6 Training Schedule

Training runs are **ambient** -- they do not block agent serving. The schedule:

1. **Continuous collection**: Every agent conversation is logged as a rollout
2. **Batch scoring**: Every 4 hours, accumulated rollouts are scored by the PRM on Tinker
3. **Training step**: When `batch_size` (16) scored samples accumulate, a training step fires
4. **Checkpoint**: Every 20 training steps, a LoRA checkpoint is saved
5. **Evaluation gate**: Each checkpoint is scored against held-out test prompts before promotion

A cron job on the Leader node (`/rl-train` command) can also trigger immediate training cycles.

---

## Part 2: Baseline Preservation and Rollback

### 2.1 Versioning Strategy

Before any RL training begins, freeze the current agent behavior as the immutable baseline:

```
~/.darklab/rl/baselines/
    research-v0.json          # Metadata: model, date, test scores
    research-v0-prompts.jsonl # 50 canonical test prompts + expected outputs
    literature-v0.json
    ...
```

Each baseline record contains:
- The base model identifier (e.g., `Qwen/Qwen3-4B-Instruct-2507`)
- SHA-256 hash of the model weights at freeze time
- Evaluation scores on the canonical test set (using `RuleBasedEvaluator`)
- The exact `TierConfig` used at freeze time

### 2.2 Checkpoint Lineage

Every RL checkpoint records its full lineage:

```json
{
  "checkpoint_id": "research-ckpt-042",
  "parent_checkpoint": "research-ckpt-041",
  "base_model": "Qwen/Qwen3-4B-Instruct-2507",
  "baseline_version": "research-v0",
  "training_method": "combine",
  "training_steps": 42,
  "rollout_sources": {
    "live": 312,
    "synthetic_debate": 87
  },
  "evaluation_score": 0.847,
  "baseline_score": 0.723,
  "delta": "+0.124",
  "promoted": true,
  "promoted_at": "2026-04-15T10:30:00Z"
}
```

### 2.3 Rollback Mechanism

Rollback is a single config change. The model router maintains a per-agent checkpoint reference:

```python
# In shared/config.py (new fields)
rl_checkpoint_dir: Path = Path.home() / ".darklab" / "rl"
rl_enabled_agents: set[str] = set()  # Empty = all agents use base model
```

Rollback procedure:
1. Remove the agent from `rl_enabled_agents` in config
2. The model router stops routing to `RL_EVOLVED` tier for that agent
3. Traffic immediately falls back to `EXECUTION` (Ollama base model)
4. No model weights are deleted -- checkpoints remain for analysis

Emergency rollback via Telegram:
```
/rl-rollback research    # Disable RL for research agent
/rl-rollback all         # Disable all RL-evolved models
/rl-status               # Show which agents use RL vs baseline
```

### 2.4 Promotion Gate

A checkpoint is promoted to production only when:
1. Evaluation score >= baseline score (no regression)
2. Evaluation score >= previous promoted checkpoint score
3. No single test prompt scores below 0.3 (catastrophic failure guard)
4. Human approval via Paperclip (optional, configurable)

---

## Part 3: MiroShark for Exponential Debates

### 3.1 The Problem MiroShark Solves

RL training quality depends on training data diversity. Live agent conversations in DarkLab tend to be:
- Narrow in scope (whatever the lab is currently researching)
- Low-conflict (agents follow instructions, rarely encounter adversarial pushback)
- Sparse in error signals (most turns score neutral, few score negative)

MiroShark solves this by generating **synthetic adversarial scenarios** where dozens of AI agents with distinct personalities debate scientific claims, challenge methodologies, and expose reasoning flaws.

### 3.2 Debate Scenario Types

| Scenario | MiroShark Config | Training Signal |
|---|---|---|
| **Peer Review Simulation** | Upload a research paper draft; agents simulate hostile reviewers | Teaches agents to anticipate and address methodological criticisms |
| **Hypothesis Debate** | Upload a research hypothesis; agents argue for and against | Teaches balanced evaluation, steel-manning opposing views |
| **Methodology Defense** | Upload an experimental design; agents challenge statistical validity | Strengthens DOE and analysis agents |
| **Literature Dispute** | Upload conflicting papers; agents debate which findings are more reliable | Teaches source credibility assessment |
| **Cross-Domain Challenge** | Upload findings from domain A; agents from domain B challenge applicability | Teaches interdisciplinary reasoning |
| **Budget Negotiation** | Upload a research proposal with budget; agents debate resource allocation | Strengthens planning and prioritization |

### 3.3 MiroShark Integration Architecture

```
                    +----------------------------+
                    |  OAS Dispatch (dispatch.py) |
                    +-------------+--------------+
                                  |
                                  | /debate <topic>
                                  v
                    +----------------------------+
                    | DebateOrchestrator          |
                    | (new: core/oas_core/        |
                    |  adapters/miroshark.py)     |
                    +-------------+--------------+
                                  |
                    +-------------v--------------+
                    | MiroShark Backend :5001     |
                    | +-----------+              |
                    | | Graph     | Upload topic  |
                    | | Builder   | as "document" |
                    | +-----------+              |
                    |       |                    |
                    | +-----v-----+              |
                    | | Agent     | Generate      |
                    | | Setup     | debate agents  |
                    | +-----------+ (pro/con/     |
                    |       |       neutral/       |
                    |       |       devil's adv.)  |
                    | +-----v-----+              |
                    | | Simulation| Run rounds    |
                    | | Engine    | (OASIS/CAMEL) |
                    | +-----------+              |
                    |       |                    |
                    | +-----v-----+              |
                    | | Report    | Structured    |
                    | | Agent     | transcript    |
                    | +-----------+              |
                    +-------------+--------------+
                                  |
                                  | Debate transcript
                                  v
                    +----------------------------+
                    | Transcript Converter        |
                    | (new: core/oas_core/        |
                    |  rl/transcript_converter.py)|
                    +-------------+--------------+
                                  |
                                  | OpenClaw-RL rollout format
                                  v
                    +----------------------------+
                    | ~/.darklab/rl/rollouts/     |
                    |   synthetic/<debate-id>.jsonl|
                    +----------------------------+
```

### 3.4 Debate Agent Persona Design

MiroShark generates agents from documents using its Neo4j knowledge graph. For scientific debates, we seed it with structured persona templates:

- **Domain Expert** (2-3 agents) -- Deep knowledge of the specific field, conservative methodology preferences
- **Methodologist** (1-2 agents) -- Focuses on statistical rigor, experimental design flaws, reproducibility
- **Contrarian** (1-2 agents) -- Systematically challenges assumptions, proposes alternative explanations
- **Cross-Domain Analyst** (1-2 agents) -- Brings perspectives from adjacent fields
- **Synthesizer** (1 agent) -- Attempts to reconcile opposing views, find common ground
- **Journal Reviewer** (1-2 agents) -- Evaluates publishability, clarity, novelty

The belief state tracking in MiroShark (stance, confidence, trust) provides natural reward signals: agents who shift others' beliefs while maintaining their own consistency score higher.

### 3.5 New Slash Command: /debate

```
/debate "Hypothesis: CRISPR-Cas9 off-target effects are under-reported in clinical trials"
/debate --rounds 10 --agents 20 "Should autonomous vehicles prioritize pedestrian safety over passenger safety?"
/debate --scenario peer-review --paper arxiv:2603.12345
```

This routes through `dispatch.py` to the new `MiroSharkAdapter`, which:
1. Submits the topic to MiroShark's `/api/simulation/create` endpoint
2. Configures debate-optimized agent profiles
3. Runs the simulation (10-40 rounds)
4. Extracts structured transcripts
5. Converts to OpenClaw-RL training format
6. Stores in `~/.darklab/rl/rollouts/synthetic/`

---

## Part 4: Framework Coordination

### 4.1 The Flywheel

```
                    Live Agent Work
                         |
                         v
              +--------------------+
              | Rollout Collection  |-----+
              +--------------------+     |
                                         |
                                         v
                               +-----------------+
            +----------------->| OpenClaw-RL     |
            |                  | Training Loop   |
            |                  +---------+-------+
            |                            |
            |                   Improved checkpoint
            |                            |
            |                            v
            |                  +-----------------+
            |                  | Evaluation Gate  |
            |                  +---------+-------+
            |                            |
            |                    Pass    |    Fail
            |                    +-------+-------+
            |                    |               |
            |                    v               v
            |           Promote to         Keep previous
            |           RL_EVOLVED         checkpoint
            |                    |
            |                    v
            |           Better Agent
            |           Performance
            |                    |
            |                    v
            |           Higher quality
            |           conversations
            |                    |
            +--------------------+
            |
            |    MiroShark Debates
            |         |
            |         v
            |  Synthetic training data
            |  (adversarial, diverse)
            |         |
            +---------+
```

### 4.2 Data Flow Between Frameworks

**MiroShark -> OpenClaw-RL:**

MiroShark produces debate transcripts in its native format (JSON with per-agent actions per round). The `TranscriptConverter` (`core/oas_core/rl/transcript_converter.py`) transforms these into OpenClaw-RL's expected format:

```json
{
  "session_id": "debate-2026-04-15-001",
  "turns": [
    {
      "role": "user",
      "content": "Evaluate this research claim: ...",
      "turn_type": "main"
    },
    {
      "role": "assistant",
      "content": "The claim has several methodological issues...",
      "turn_type": "main",
      "logprobs": [...]
    },
    {
      "role": "user",
      "content": "[Agent: Contrarian] I disagree because...",
      "turn_type": "main"
    }
  ]
}
```

The conversion maps MiroShark's multi-agent structure to OpenClaw-RL's single-agent-with-environment format:
- The OAS agent being trained plays "assistant"
- All other debate agents (combined) play "user/environment"
- Belief state changes serve as next-state signals for PRM scoring
- A strong counter-argument that shifts no beliefs = negative reward for the responding agent
- A well-reasoned defense that maintains beliefs = positive reward

**OpenClaw-RL -> MiroShark:**

As agents improve through RL training, MiroShark can use the improved agents as debate participants. This creates increasingly challenging debates -- the better the agents get, the harder MiroShark must push to find weaknesses.

Configure MiroShark to use OAS agents via LiteLLM:
```bash
# MiroShark .env
LLM_BASE_URL=http://192.168.23.25:4000/v1
LLM_MODEL_NAME=rl-evolved-research  # Routes through model_router
```

### 4.3 Scheduling and Orchestration

The coordination between frameworks runs as a background campaign via `CampaignEngine`:

```python
# Pseudo-campaign plan for weekly RL training cycle
[
  {"step": 1, "command": "debate", "args": "Generate 5 debate scenarios from recent research topics", "depends_on": []},
  {"step": 2, "command": "rl-collect", "args": "Gather live rollouts from past 7 days", "depends_on": []},
  {"step": 3, "command": "rl-train", "args": "Run training with live + synthetic rollouts", "depends_on": [1, 2]},
  {"step": 4, "command": "rl-eval", "args": "Evaluate new checkpoint against baseline", "depends_on": [3]},
  {"step": 5, "command": "rl-promote", "args": "Promote if evaluation passes gate", "depends_on": [4]}
]
```

This plan executes through the existing campaign engine with DRVP events for real-time monitoring in Agent Office.

---

## Part 5: Data Management

### 5.1 Data Flow Diagram

```
  Sources                    Storage                     Consumers
  =======                    =======                     =========

  Live agent       --->  ~/.darklab/rl/rollouts/live/
  conversations          (JSONL, 1 file per session)
                              |
                              +---> OpenClaw-RL Trainer
                              |     (PRM scoring + policy gradient)
                              |
  MiroShark        --->  ~/.darklab/rl/rollouts/synthetic/
  debates                (JSONL, 1 file per debate)
                              |
                              +---> OpenClaw-RL Trainer
                              |
  PRM scores       --->  ~/.darklab/rl/scores/
                         (JSONL, turn-level rewards)
                              |
                              +---> Training metrics dashboard
                              |     (Paperclip activity log)
                              |
  Checkpoints      --->  Tinker cloud storage
  (LoRA adapters)        (remote, pulled on demand)
                              |
                              +---> ~/.darklab/rl/checkpoints/
                              |     (local cache of active adapters)
                              |
  Evaluations      --->  ~/.darklab/rl/evaluations/
                         (JSON, per-checkpoint scores)
                              |
                              +---> Promotion gate logic
                              +---> Paperclip dashboard
                              +---> DRVP events
```

### 5.2 Storage Sizing

Estimated storage requirements per month of continuous operation:

| Data Type | Size/Unit | Volume/Month | Total/Month |
|---|---|---|---|
| Live rollouts | ~5 KB/session | ~3,000 sessions | ~15 MB |
| Synthetic debates | ~50 KB/debate | ~200 debates | ~10 MB |
| PRM scores | ~1 KB/session | ~3,200 scored | ~3 MB |
| LoRA checkpoints | ~50 MB/ckpt | ~30 checkpoints | ~1.5 GB |
| Evaluations | ~2 KB/eval | ~30 evals | ~60 KB |

Total: approximately 1.5 GB/month, dominated by LoRA checkpoints. Implement a retention policy: keep the 10 most recent checkpoints plus the baseline; archive older ones to external storage.

### 5.3 Data Formats

**Rollout format** (compatible with OpenClaw-RL `openclaw_api_server.py`):

```json
{
  "session_id": "req-abc123",
  "agent_type": "research",
  "source": "live",
  "started_at": "2026-04-15T10:00:00Z",
  "completed_at": "2026-04-15T10:02:30Z",
  "turns": [
    {
      "role": "system",
      "content": "You are a research agent...",
      "turn_type": "side"
    },
    {
      "role": "user",
      "content": "/research CRISPR off-target effects",
      "turn_type": "main"
    },
    {
      "role": "assistant",
      "content": "Based on recent literature...",
      "turn_type": "main",
      "token_logprobs": [-0.12, -0.08, ...],
      "response_tokens": 847
    }
  ]
}
```

**Evaluation format:**

```json
{
  "checkpoint_id": "research-ckpt-042",
  "evaluated_at": "2026-04-15T14:00:00Z",
  "test_set": "research-canonical-v1",
  "n_prompts": 50,
  "aggregate_score": 0.847,
  "criteria_scores": {
    "completeness": 0.88,
    "structure": 0.92,
    "sources": 0.76,
    "error_free": 0.85
  },
  "per_prompt_scores": [
    {"prompt_id": "p001", "score": 0.91, "quality": "excellent"},
    {"prompt_id": "p002", "score": 0.74, "quality": "good"}
  ],
  "regression_check": {
    "baseline_score": 0.723,
    "delta": 0.124,
    "regressed_prompts": [],
    "passed": true
  }
}
```

### 5.4 DRVP Event Extensions

New event types for RL visibility in Agent Office:

```python
# In core/oas_core/protocols/drvp.py -- new event types

# RL training lifecycle
RL_ROLLOUT_COLLECTED = "rl.rollout.collected"      # A conversation was recorded
RL_TRAINING_STEP = "rl.training.step"              # A gradient step completed
RL_CHECKPOINT_SAVED = "rl.checkpoint.saved"         # New checkpoint available
RL_EVALUATION_COMPLETED = "rl.evaluation.completed" # Checkpoint evaluated
RL_CHECKPOINT_PROMOTED = "rl.checkpoint.promoted"   # Checkpoint went live
RL_CHECKPOINT_ROLLED_BACK = "rl.checkpoint.rolledback"

# MiroShark debate lifecycle
DEBATE_STARTED = "debate.started"
DEBATE_ROUND_COMPLETED = "debate.round.completed"
DEBATE_COMPLETED = "debate.completed"
DEBATE_TRANSCRIPT_READY = "debate.transcript.ready"
```

---

## Part 6: Implementation Phases

### Phase 1: Foundation (Weeks 1-2)

**Goal:** Establish baseline preservation, rollout collection infrastructure, and the RL_EVOLVED tier in the model router.

| # | Task | Files | Tests |
|---|---|---|---|
| 46 | Add `RL_EVOLVED` tier to `ModelRouter` | `core/oas_core/model_router.py` | Unit: tier routing, fallback chain |
| 47 | Create `RolloutCollector` middleware | `core/oas_core/middleware/rl_rollout.py` | Unit: session tagging, JSONL writing |
| 48 | Add RL config fields to `Settings` | `cluster/agents/shared/config.py` | Unit: config loading, defaults |
| 49 | Implement baseline freeze command | `cluster/agents/leader/rl_commands.py` | Unit: snapshot creation, hash verification |
| 50 | Add RL DRVP event types | `core/oas_core/protocols/drvp.py` | Unit: event serialization |
| 51 | Create `~/.darklab/rl/` directory structure | `cluster/agents/leader/rl_commands.py` | Integration: directory creation, permissions |

**Milestone:** Running `/.rl-freeze research` creates a baseline snapshot. All agent conversations generate rollout JSONL files. The model router recognizes `RL_EVOLVED` but falls back to `EXECUTION` since no checkpoints exist yet.

### Phase 2: OpenClaw-RL Integration (Weeks 3-4)

**Goal:** Connect the OpenClaw-RL training pipeline to OAS rollout data. Establish the Tinker-based training loop.

| # | Task | Files | Tests |
|---|---|---|---|
| 52 | Create `OpenClawRLAdapter` | `core/oas_core/adapters/openclaw_rl.py` | Unit: session formatting, API compatibility |
| 53 | Implement Tinker training client wrapper | `core/oas_core/rl/tinker_client.py` | Unit: API calls, checkpoint download |
| 54 | Build rollout-to-training pipeline | `core/oas_core/rl/training_pipeline.py` | Integration: end-to-end rollout scoring |
| 55 | Implement checkpoint evaluation | `core/oas_core/rl/checkpoint_eval.py` | Unit: scoring against canonical prompts |
| 56 | Implement promotion gate | `core/oas_core/rl/promotion_gate.py` | Unit: gate logic, regression check |
| 57 | Add `/rl-train` and `/rl-status` commands to dispatch | `cluster/agents/leader/dispatch.py`, `cluster/agents/leader/rl_commands.py` | Integration: command routing |
| 58 | Add `/rl-rollback` command | `cluster/agents/leader/rl_commands.py` | Unit: rollback logic, config update |

**Milestone:** Running `/rl-train research` triggers a training cycle on Tinker. The checkpoint is evaluated and, if it passes, promoted. `/rl-status` shows per-agent training state. `/rl-rollback research` disables the RL model and reverts to baseline.

### Phase 3: MiroShark Integration (Weeks 5-6)

**Goal:** Deploy MiroShark on the Leader node. Build the debate generation pipeline and transcript converter.

| # | Task | Files | Tests |
|---|---|---|---|
| 59 | Create `MiroSharkAdapter` | `core/oas_core/adapters/miroshark.py` | Unit: API client, simulation config |
| 60 | Implement `TranscriptConverter` | `core/oas_core/rl/transcript_converter.py` | Unit: MiroShark -> OpenClaw-RL format |
| 61 | Design debate persona templates | `cluster/skills/darklab-debate/SKILL.md` | -- |
| 62 | Add `/debate` command to dispatch and routing table | `cluster/agents/leader/dispatch.py`, `cluster/agents/shared/models.py` | Integration: command routing |
| 63 | Add MiroShark to Docker stack | `cluster/docker/docker-compose.services.yml` | -- |
| 64 | Add Neo4j to Docker stack | `cluster/docker/docker-compose.services.yml` | -- |
| 65 | Wire debate transcripts to rollout storage | `core/oas_core/rl/training_pipeline.py` | Integration: synthetic data ingestion |

**Milestone:** Running `/debate "topic"` generates a multi-agent debate, converts the transcript to training format, and stores it alongside live rollouts. MiroShark runs on the Leader Mac mini using Ollama for simulation rounds.

### Phase 4: Framework Coordination (Weeks 7-8)

**Goal:** Connect the two frameworks into a self-reinforcing flywheel. Implement automated training campaigns.

| # | Task | Files | Tests |
|---|---|---|---|
| 66 | Build weekly RL training campaign template | `cluster/agents/leader/rl_commands.py` | Unit: campaign plan generation |
| 67 | Implement mixed rollout batching (live + synthetic) | `core/oas_core/rl/training_pipeline.py` | Unit: batch composition, ratio control |
| 68 | Configure MiroShark to use RL-evolved agents | `core/oas_core/adapters/miroshark.py` | Integration: LiteLLM routing |
| 69 | Add RL metrics to Paperclip dashboard | `core/oas_core/adapters/paperclip.py` | Unit: metrics posting |
| 70 | Add RL training DRVP events to Office consumers | `office/src/drvp/drvp-consumer.ts` | Unit: event handling |
| 71 | Implement training data retention policy | `core/oas_core/rl/data_manager.py` | Unit: cleanup logic |

**Milestone:** A weekly cron job runs a full training cycle: generate debates, collect live rollouts, train, evaluate, promote or reject. Agent Office shows RL training progress in real time.

### Phase 5: Hardening and Observability (Weeks 9-10)

**Goal:** Production-grade reliability, monitoring, and documentation.

| # | Task | Files | Tests |
|---|---|---|---|
| 72 | E2E test: full RL cycle (collect -> train -> eval -> promote) | `core/tests/test_rl_e2e.py` | E2E: mocked Tinker |
| 73 | E2E test: debate -> transcript -> training | `core/tests/test_debate_rl_e2e.py` | E2E: mocked MiroShark |
| 74 | Add circuit breaker for Tinker API failures | `core/oas_core/rl/tinker_client.py` | Unit: retry, fallback |
| 75 | Implement A/B comparison: RL vs baseline on same prompts | `core/oas_core/rl/ab_comparison.py` | Unit: comparison logic |
| 76 | Add RL section to Paperclip dashboard (training curves, per-agent scores) | Paperclip UI changes | -- |
| 77 | Update CLAUDE.md with RL integration docs | `CLAUDE.md` | -- |

**Milestone:** The full system runs reliably with monitoring, fallback handling, and documented operational procedures.

---

## Key Considerations and Risks

### Hardware Constraints

**Risk:** The Mac mini cluster has no discrete GPUs. All RL training must happen remotely.

**Mitigation:** Use Tinker cloud for all training and PRM evaluation. Only inference happens locally (Ollama). The OpenClaw-RL proxy on the Leader node is CPU-only -- it just forwards requests and collects rollouts. If Tinker becomes unavailable, training pauses but agents continue serving normally on the base model.

**Alternative:** If Tinker costs become prohibitive, rent a single A100 node on-demand (RunPod, Lambda) for training batches. The architecture supports this -- just change the training endpoint.

### Training Data Quality

**Risk:** Low-quality rollouts (ambiguous tasks, partially failed requests) pollute the training signal.

**Mitigation:**
1. Filter rollouts through the existing `RuleBasedEvaluator` before scoring -- discard sessions where the output scored below 0.3
2. Use the PRM's majority voting (m=3) to reduce scoring noise
3. Weight synthetic (MiroShark) data more heavily in early training when live data is sparse
4. Monitor PRM score distribution -- if most scores are neutral (0), the PRM needs recalibration

### Catastrophic Forgetting

**Risk:** RL training on narrow task distributions causes the model to forget general capabilities.

**Mitigation:**
1. LoRA training (rank 32) limits the parameter space that can change
2. KL divergence penalty (`kl_loss_coef=0.02`) keeps the policy close to the base model
3. Per-agent LoRA adapters prevent cross-task interference
4. The evaluation gate tests general capability alongside task-specific improvement
5. MiroShark debates provide diverse training signals that counteract narrowing

### Reward Hacking

**Risk:** Agents learn to game the PRM (producing outputs that score well but are not actually useful).

**Mitigation:**
1. Rotate PRM prompts periodically
2. Use MiroShark adversarial debates as out-of-distribution evaluation
3. The promotion gate includes human-readable evaluation summaries posted to Paperclip for manual review
4. Implement a "canary" test set that is never used for training -- only for evaluation

### Budget Impact

**Risk:** Tinker API costs and MiroShark simulation costs add to the existing budget.

**Mitigation:**
1. Track RL training costs as a separate budget category in Paperclip
2. Set hard daily limits on Tinker API calls ($10/day default)
3. MiroShark uses Ollama locally for simulation rounds (free) and only Tinker/cloud for report generation
4. Training runs are batched, not continuous -- 1 cycle per week by default

### Model Drift Detection

**Risk:** Gradual performance degradation that passes individual evaluation gates but trends downward.

**Mitigation:**
1. Track evaluation scores over time (stored in `~/.darklab/rl/evaluations/`)
2. Alert (via Paperclip issue + DRVP event) if 3 consecutive checkpoints show decreasing scores
3. Weekly A/B comparison between RL-evolved and baseline on 10 random production prompts
4. Monthly manual review of training curves posted to the Paperclip dashboard

---

## Integration Point Reference

This section maps every new component to its exact location in the OAS codebase.

### New Files

| File | Purpose |
|---|---|
| `core/oas_core/middleware/rl_rollout.py` | Rollout collection middleware for the OAS pipeline |
| `core/oas_core/adapters/openclaw_rl.py` | OpenClaw-RL API proxy client |
| `core/oas_core/adapters/miroshark.py` | MiroShark simulation engine client |
| `core/oas_core/rl/__init__.py` | RL subpackage init |
| `core/oas_core/rl/tinker_client.py` | Tinker cloud training API wrapper |
| `core/oas_core/rl/training_pipeline.py` | Rollout scoring and batch assembly |
| `core/oas_core/rl/transcript_converter.py` | MiroShark transcript to OpenClaw-RL format |
| `core/oas_core/rl/checkpoint_eval.py` | Checkpoint evaluation against canonical tests |
| `core/oas_core/rl/promotion_gate.py` | Promotion/regression gate logic |
| `core/oas_core/rl/data_manager.py` | Retention policy, cleanup |
| `core/oas_core/rl/ab_comparison.py` | A/B comparison between checkpoints |
| `cluster/agents/leader/rl_commands.py` | /rl-train, /rl-status, /rl-rollback, /rl-freeze handlers |
| `cluster/skills/darklab-debate/SKILL.md` | Debate skill definition |
| `cluster/skills/darklab-rl-train/SKILL.md` | RL training skill definition |
| `core/tests/test_rl_rollout.py` | Rollout middleware tests |
| `core/tests/test_openclaw_rl_adapter.py` | OpenClaw-RL adapter tests |
| `core/tests/test_miroshark_adapter.py` | MiroShark adapter tests |
| `core/tests/test_training_pipeline.py` | Training pipeline tests |
| `core/tests/test_promotion_gate.py` | Promotion gate tests |
| `core/tests/test_rl_e2e.py` | End-to-end RL cycle test |
| `core/tests/test_debate_rl_e2e.py` | End-to-end debate-to-training test |
| `cluster/tests/test_rl_commands.py` | RL command dispatch tests |

### Modified Files

| File | Change |
|---|---|
| `core/oas_core/model_router.py` | Add `RL_EVOLVED` tier, per-agent checkpoint routing |
| `core/oas_core/protocols/drvp.py` | Add 8 new RL/debate event types |
| `cluster/agents/shared/models.py` | Add `DEBATE` and `RL_TRAIN` TaskType values |
| `cluster/agents/shared/config.py` | Add RL config fields (checkpoint dir, enabled agents, Tinker key) |
| `cluster/agents/leader/dispatch.py` | Add /debate, /rl-train, /rl-status, /rl-rollback, /rl-freeze routes |
| `cluster/agents/leader/swarm_registry.py` | Add debate agent entry |
| `cluster/docker/docker-compose.services.yml` | Add MiroShark, Neo4j services |
| `office/src/drvp/drvp-types.ts` | Add RL/debate event type definitions |
| `office/src/drvp/drvp-consumer.ts` | Handle RL/debate events for visual state |
| `core/oas_core/middleware/__init__.py` | Add `RolloutCollector` to pipeline |
| `core/oas_core/adapters/__init__.py` | Export new adapters |

### Docker Stack Additions

```yaml
# In cluster/docker/docker-compose.services.yml

  miroshark:
    build: ../../frameworks/MiroShark-main
    ports:
      - "5001:5001"
    environment:
      LLM_BASE_URL: http://litellm:4000/v1
      LLM_API_KEY: ${LITELLM_API_KEY}
      LLM_MODEL_NAME: llama3.1
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD:-miroshark}
      EMBEDDING_PROVIDER: ollama
      EMBEDDING_MODEL: nomic-embed-text
      EMBEDDING_BASE_URL: http://host.docker.internal:11434
    depends_on:
      - neo4j
      - litellm

  neo4j:
    image: neo4j:5.15-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-miroshark}
    volumes:
      - neo4j_data:/data
```

### Routing Table Extension

```python
# In cluster/agents/leader/dispatch.py -- ROUTING_TABLE additions

"debate":     Route("leader", "darklab-debate",    TaskType.DEBATE),
"rl-train":   Route("leader", "darklab-rl-train",  TaskType.RL_TRAIN),
"rl-status":  Route("leader", "darklab-rl-train",  TaskType.RL_TRAIN),
"rl-rollback":Route("leader", "darklab-rl-train",  TaskType.RL_TRAIN),
"rl-freeze":  Route("leader", "darklab-rl-train",  TaskType.RL_TRAIN),
```

### Environment Variables

```bash
# In ~/.darklab/.env -- new RL-related variables

# OpenClaw-RL / Tinker
DARKLAB_RL_ENABLED=false                    # Master switch
DARKLAB_TINKER_API_KEY=                     # Tinker cloud API key
DARKLAB_RL_CHECKPOINT_DIR=~/.darklab/rl     # Local RL data directory
DARKLAB_RL_TRAINING_METHOD=combine          # rl | opd | combine
DARKLAB_RL_BATCH_SIZE=16                    # Samples per training step
DARKLAB_RL_PRM_M=3                          # PRM majority vote count
DARKLAB_RL_LORA_RANK=32                     # LoRA rank
DARKLAB_RL_MIN_PROMOTION_SCORE=0.7          # Minimum eval score for promotion
DARKLAB_RL_DAILY_BUDGET=10.00               # Daily Tinker spend limit ($)

# MiroShark
DARKLAB_MIROSHARK_URL=http://localhost:5001 # MiroShark backend URL
DARKLAB_MIROSHARK_ENABLED=false             # Master switch
DARKLAB_DEBATE_DEFAULT_ROUNDS=10            # Default debate rounds
DARKLAB_DEBATE_DEFAULT_AGENTS=15            # Default debate agent count
```

---

## Decision Records

### ADR-011: Use Tinker Cloud for RL Training Instead of Local GPU

**Status:** Proposed

**Context:** The DarkLab cluster runs on Mac minis (M-series Apple Silicon) which lack the CUDA-capable discrete GPUs required by OpenClaw-RL's Slime/Megatron training backend. Training requires at minimum 4 GPUs for the default configuration (2 actor + 1 rollout + 1 PRM).

**Decision:** Use Tinker cloud for all RL training operations. The local cluster handles only inference (via Ollama) and rollout collection. LoRA training on Tinker requires no local GPU and supports all three optimization methods.

**Consequences:**
- (+) No hardware investment needed
- (+) Training scales independently of cluster capacity
- (+) LoRA keeps adapter sizes small (~50MB), fast to download
- (-) Training depends on Tinker availability and API costs
- (-) LoRA may be less effective than full fine-tuning (per OpenClaw-RL docs: "may not be as effective")
- (-) Network latency between local rollout collection and cloud training

### ADR-012: Per-Agent LoRA Adapters Over Shared Fine-Tuning

**Status:** Proposed

**Context:** The 16 DarkLab agents serve very different tasks (literature review vs simulation vs synthesis). A single fine-tuned model would face conflicting optimization signals.

**Decision:** Train separate LoRA adapters for each agent type. The base model remains unchanged. The OpenClaw-RL proxy selects the appropriate adapter based on request metadata.

**Consequences:**
- (+) No cross-task interference
- (+) Independent rollback per agent
- (+) Clear evaluation: each adapter tested against its own task domain
- (-) 16x more checkpoints to manage
- (-) Cold-start problem: new agents have no training data
- (-) Adapter switching adds latency (~100ms)

### ADR-013: MiroShark for Synthetic Training Data Over Manual Curation

**Status:** Proposed

**Context:** High-quality RL training requires diverse, adversarial training data. Manual curation of such data is expensive and does not scale. Live agent conversations alone are too narrow and cooperative.

**Decision:** Use MiroShark to generate structured scientific debates that serve as synthetic training data for OpenClaw-RL. MiroShark's multi-agent simulation with belief state tracking provides natural reward signals.

**Consequences:**
- (+) Unlimited synthetic training data at the cost of Ollama compute time
- (+) Adversarial scenarios that live data rarely produces
- (+) Belief state changes as natural reward signals (richer than binary thumbs-up/down)
- (-) Synthetic data may not perfectly represent real user interactions
- (-) Neo4j and MiroShark add operational complexity to the Docker stack
- (-) Debate quality depends on Ollama model quality (llama3.1:8b may be too weak for nuanced debates)

---

## Summary

This integration creates a self-improving research platform where:

1. Every agent conversation becomes a learning opportunity (via OpenClaw-RL rollout collection)
2. MiroShark generates challenging adversarial debates that push agents beyond their comfort zone
3. Training happens in the background on Tinker cloud without interrupting production work
4. Baseline preservation and promotion gates ensure agents only improve, never regress
5. The full lifecycle is visible through DRVP events in Agent Office and Paperclip governance

The total estimated effort is 32 tasks across 5 phases (10 weeks), adding approximately 3,000 lines of Python and 500 lines of TypeScript to the codebase. Expected test coverage: 60+ new tests bringing the total from 474 to approximately 535.
