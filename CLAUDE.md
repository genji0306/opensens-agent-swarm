# Opensens Agent Swarm (OAS) — Claude Code Project Guide

**Four-layer agentic research swarm on the DarkLab Mac mini cluster (v2, Phase 24+).**
Canonical plan: `docs/OAS-V2-MERGED-PLAN.md` — legacy history: `docs/OAS-DEVELOPMENT-PLAN.md`

## Architecture

```
Boss (human)        → sovereign intent · approval · override (MacBook/iPad/iPhone)
OAS Control Plane   → zero-LLM: plan store, approvals, timeline, override console
Leader (cyber02)    → strategic orchestration: plans, routes, synthesizes, escalates
DEV (cyber01)       → execution + compute pool: local models, code, sim, RL
```

**Two Leader↔DEV primitives**: Task delegation (JSON-RPC, DEV authority) · Inference borrowing (HTTP POST `/v1/borrow`, Leader authority retained)

**7-tier model taxonomy** — see skill `darklab-model-routing` for full degradation chain:

| Tier | Location | Gate |
|------|----------|------|
| `PLANNING_LOCAL` | Leader (Gemma 4 E4B) | Automatic |
| `REASONING_LOCAL` | DEV (Gemma 4 27B MoE, borrowed) | Automatic |
| `WORKER_LOCAL` | DEV (3× E4B pool, borrowed) | Automatic, time-sliced |
| `CODE_LOCAL` | DEV (Qwen2.5-Coder 7B) | DEV task delegation |
| `RL_EVOLVED` | DEV (Qwen3 + per-agent LoRA) | Automatic when LoRA available |
| `CLAUDE_SONNET` | Cloud | Per-mission budget cap |
| `CLAUDE_OPUS` | Cloud | **Per-call Boss approval — no bypass** |

## Directory Structure

```
cluster/          # DarkLab agents (agents/shared, leader, academic, experiment, dev) + 14 skills
core/oas_core/    # OAS framework: campaign, middleware, decision, scheduler, inference, kairos,
                  #   knowledge, eval, protocols/drvp, adapters, subagents (28+ modules)
office/src/       # React 19 + Vite 6 + Zustand 5 (gateway, store, drvp, components, pages)
paperclip/        # Governance platform (Express 5, React 19, Drizzle ORM, 37 tables)
frameworks/       # Read-only reference: langgraph, openviking, openclaw-rl, deerflow, ecc
.claude/          # Harness: 7 DarkLab skills + ECC skills/agents/rules/hooks
docs/             # Plans, integration docs
```

## Running Tests

```bash
.venv/bin/pytest cluster/tests/ -q   # ~291 tests
.venv/bin/pytest core/tests/ -q      # ~881 tests (9 skipped without langgraph)
cd office && npx vitest run           # ~28 tests
```
Run cluster and core separately — conftest collision. Use `.venv/bin/pytest`, not system pytest.

## Routing Table (slash commands → TaskType → device)

| Command | Device | TaskType | | Command | Device | TaskType |
|---------|--------|----------|-|---------|--------|----------|
| research | academic | RESEARCH | | dft | leader | DFT |
| literature | academic | LITERATURE | | ane-research | leader | ANE_RESEARCH |
| doe | academic | DOE | | gemma-swarm | leader | GEMMA_SWARM |
| paper | academic | PAPER | | unipat | leader | UNIPAT_SWARM |
| perplexity | academic | PERPLEXITY | | orchestrate | leader | ORCHESTRATE |
| simulate | experiment | SIMULATE | | kairos | leader | KAIROS |
| analyze | experiment | ANALYZE | | turboswarm | leader | TURBO_SWARM |
| synthetic | experiment | SYNTHETIC | | fullswarm | leader | FULL_SWARM |
| autoresearch | experiment | AUTORESEARCH | | paperreview | leader | PAPER_REVIEW |
| deerflow | leader | DEERFLOW | | debate | leader | DEBATE |
| deepresearch | leader | DEEP_RESEARCH | | rl-train/status/rollback/freeze | leader | RL_TRAIN |
| synthesize | leader | SYNTHESIZE | | parametergolf | experiment | PARAMETER_GOLF |

## Dispatch Flow

```
text → audit.log → memory.pre_load
  → parse_command → /cmd → ROUTING_TABLE
                 → free-form → swarm → campaign (approval gate → CampaignEngine DAG)
```

## Key Conventions

- Python 3.11+, Pydantic v2, async/await throughout
- Model IDs: `claude-opus-4-6-20260301`, `claude-sonnet-4-6-20260301`
- Config: `shared.config.Settings` (dotenv from `~/.darklab/.env`)
- `core/` uses `logging` (`oas.*`); `cluster/` uses `structlog` — don't mix
- `frameworks/` is read-only — import and wrap in `core/`
- Optional deps guarded: `SWARM_AVAILABLE`, `_WS_AVAILABLE`, `_NACL_AVAILABLE`, `DEERFLOW_AVAILABLE`, `_LANCEDB_AVAILABLE`
- All modules export via `__all__`; no circular imports
- Paths use `settings.darklab_home` (not `Path.home()`) for testability

## Infrastructure

| Service | Host | Port |
|---------|------|------|
| OpenClaw Gateway | leader.local | 18789 |
| Paperclip AI | 192.168.23.25 | 3100 |
| Opensens Office | 192.168.23.25 | 5180 |
| DarkLab Leader | 192.168.23.25 | 8100 |
| LiteLLM | 192.168.23.25 | 4000 |
| Redis | 192.168.23.25 | 6379 |

SSH: `ssh "cyber 02@192.168.23.25"` (password: Opensens26)

## Budget & Governance

Daily limits: Leader $50 · Academic $30 · Experiment $20 (file-locked JSON `~/.darklab/logs/spend-YYYY-MM-DD.json`)
Paperclip company "Opensens DarkLab" (DL): Boss $0 · Leader $1,500/mo · Academic $900/mo · Experiment $600/mo
Dashboard: http://192.168.23.25:3100 — CEO: steve@opensens.io

## Office Env

```bash
VITE_GATEWAY_URL=ws://localhost:18789
VITE_LEADER_URL=http://192.168.23.25:8100
VITE_PAPERCLIP_URL=http://192.168.23.25:3100
```

## Skills (load on demand)

| Skill | When to load |
|-------|-------------|
| `darklab-swarm-ops` | Dispatch, budget, browser security, PicoClaw hooks |
| `darklab-drvp-events` | DRVP event types, emission, consumer patterns |
| `darklab-model-routing` | route_v2(), OpusGate, SonnetBudget, compute borrowing |
| `darklab-kairos-ops` | KAIROS heartbeat, autoDream, proactive suggestions |
| `darklab-plan-authoring` | Plan file schema, PlanStoreWatcher, OrchestratorAgent |
| `darklab-memory-ops` | MemoryClient, OpenViking tiers, session continuity |
| `darklab-knowledge-wiki` | KnowledgeIngester, EntityStore, EmbeddingIndex, wiki pages |
| `darklab-eval-harness` | 5-dimension rubric, EvalScorer, golden fixtures, CI gates |
| `darklab-code-review` | DarkLab-specific code review checklist |

## Development Status

| Phase | Focus | Status | Tests |
|-------|-------|--------|-------|
| 1–9 | Foundation, swarm, governance, memory, middleware, security | **Complete** | → 405 |
| 10–14 | DeerFlow, RL, deep research, sources, swarm wiring | **Complete** | → 541 |
| 15–18 | TurboQuant, Qwen3, Office panels, research mgmt | **Complete** | → 581 |
| 19–23 | Live deploy, campaign intelligence, governance maturity, multi-node, webhooks | **Complete** | → 832 |
| 24 | v2 swarm redesign: plan-file, compute borrowing, 7-tier router, KAIROS, OrchestratorAgent | **In Progress** | → 1200 |
| 25 | Self-evolution, 6-gate promotion, Passkey/WebAuthn, iPad/iPhone UI | **Planned** | TBD |

Phase 24 pending (ops): Plan Store API server, Paperclip→DEV relocation, DEV provisioning, OAS→DEV relocation, dev-exec/dev-forge identities, PicoClaw refactor, feature flags.
