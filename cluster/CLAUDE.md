# DarkLab Installer — Claude Code Project Guide

## What This Is

Automated installer for the **DarkLab** distributed AI research cluster: Mac minis (Leader, Academic, Experiment) coordinated by OpenClaw (Node.js gateway) and governed by Paperclip AI. Each device runs role-specific Python agents that perform autonomous scientific research tasks across any scientific domain.

See `DARKLAB-PLAN.md` for the comprehensive mission, aims, and workflow documentation.

## Architecture

```
Boss (MacBook)      → SSH/Telegram control, Paperclip dashboard, Opensens Office
Leader (Mac mini)   → OpenClaw gateway (:18789), Paperclip (:3100), Opensens Office (:5180)
Academic (Mac mini) → OpenClaw node-host, literature/research/browser agents
Experiment (Mac mini) → OpenClaw node-host, simulation/analysis/ML agents
```

Commands flow: **Boss → Telegram → PicoClaw → Leader dispatch.py → OpenClaw node.invoke → Academic/Experiment agents**

## Leader Docker Stack (192.168.23.25)

| Service | Port | Image/Build |
|---------|------|-------------|
| OpenClaw Gateway | 18789 | Native process (loopback) |
| Paperclip AI | 3100 | `./paperclip` (PostgreSQL backend) |
| Opensens Office | 5180 | `./opensens-office` (Node.js) |
| DarkLab Leader | 8100 | `./darklab-installer` |
| LiteLLM | 4000 | `ghcr.io/berriai/litellm` |
| PicoClaw | — | `./picoclaw` (Telegram agent) |
| PicoClaw Exec | — | `./picoclaw` (sandboxed executor) |
| Liaison Broker | 8000 | `./liaison-broker` |
| Redis | 6379 | `redis:7-alpine` |
| Caddy | 80 | `caddy:2-alpine` (static files) |
| Cloudflared | — | `cloudflare/cloudflared` (tunnel) |
| Dozzle | 8081 | `amir20/dozzle` (log viewer) |
| PostgreSQL | 5432 | `postgres:17-alpine` (Paperclip DB) |

Docker compose: `~/darklab/docker-compose.yml`
Docker CLI requires full path: `/Applications/Docker.app/Contents/Resources/bin/docker`

## Paperclip Governance

Company "Opensens DarkLab" (prefix: DL) with 4 agents seeded via SQL:
- **Boss** (CEO, human) — $0 budget
- **DarkLab Leader** (CTO) — $1,500/month, reports to Boss
- **DarkLab Academic** (Research Director) — $900/month, reports to Leader
- **DarkLab Experiment** (Lab Director) — $600/month, reports to Leader

CEO user: steve@opensens.io. Deployment mode: `authenticated` with `better-auth`.
Seed script: `/tmp/seed-paperclip.sql` (run via `docker exec` into PostgreSQL container).

## Opensens Office

Visual agent monitoring frontend (React 19 + Vite 6 + TypeScript). Rebranded from "OpenClaw Office".
Located in `Agent office/` subdirectory with its own `CLAUDE.md`.

- Entry point: `bin/opensens-office.js`
- Dockerfile: `Agent office/Dockerfile` (node:22-alpine, serves on :5180)
- Deployed at http://192.168.23.25:5180

## Directory Structure

```
install.sh                 # Entry point — detects role, sources roles/*.sh
roles/                     # Per-device installer scripts (leader|academic|experiment|boss)
common/                    # Shared setup scripts (python-env, openclaw, tailscale, keys, browser)
configs/                   # OpenClaw YAML configs, env template, exec-approvals
scripts/                   # Cluster management scripts (status, connect, seed, backup)
agents/
  shared/                  # Shared modules: models, config, llm_client, node_bridge, audit, crypto
  leader/                  # dispatch.py (routing), synthesis.py, media_gen.py, notebooklm.py
  academic/                # research.py, literature.py, doe.py, paper.py, perplexity.py, browser_agent.py
  experiment/              # simulation.py, analysis.py, synthetic.py, report_data.py, autoresearch.py
skills/                    # OpenClaw SKILL.md files (14 skills)
tests/                     # pytest suite
Agent office/              # Opensens Office — visual agent monitoring frontend
docker/                    # Dockerfiles for leader agent
DARKLAB-PLAN.md            # Mission, aims, agents, workflows documentation
```

## Agent Pattern

All agents follow this pattern:

```python
from shared.models import Task, TaskResult
from shared.node_bridge import run_agent

async def handle(task: Task) -> TaskResult:
    # Do work using task.payload
    return TaskResult(
        task_id=task.task_id,
        agent_name="MyAgent",
        status="ok",
        result={...},
        artifacts=[...],
    )

if __name__ == "__main__":
    run_agent(handle, agent_name="MyAgent")
```

OpenClaw invokes agents via `system.run`: `python3 -m academic.research '{"task_type":"research","payload":{...}}'`

## Key Modules

- **`agents/shared/models.py`** — `Task`, `TaskResult`, `TaskType` (15 enum values), `AgentInfo`
- **`agents/shared/config.py`** — Pydantic `Settings` loaded from env vars / `.env`
- **`agents/shared/llm_client.py`** — Async wrappers for Anthropic, OpenAI, Gemini, Perplexity with atomic budget enforcement (`_check_and_record_spend` under `fcntl.LOCK_EX`)
- **`agents/shared/node_bridge.py`** — stdin/argv JSON → Task → handler → TaskResult → stdout JSON
- **`agents/leader/dispatch.py`** — `ROUTING_TABLE` maps 13 slash commands to (device, skill, TaskType); `plan_campaign()` uses LLM to decompose complex requests

## Routing Table (dispatch.py)

| Command | Device | Skill | TaskType |
|---------|--------|-------|----------|
| research | academic | darklab-research | RESEARCH |
| literature | academic | darklab-literature | LITERATURE |
| doe | academic | darklab-doe | DOE |
| paper | academic | darklab-paper | PAPER |
| perplexity | academic | darklab-perplexity | PERPLEXITY |
| simulate | experiment | darklab-simulation | SIMULATE |
| analyze | experiment | darklab-analysis | ANALYZE |
| synthetic | experiment | darklab-synthetic | SYNTHETIC |
| report-data | experiment | darklab-report-data | REPORT_DATA |
| autoresearch | experiment | darklab-autoresearch | AUTORESEARCH |
| synthesize | leader | darklab-synthesis | SYNTHESIZE |
| report | leader | darklab-media-gen | MEDIA_GEN |
| notebooklm | leader | darklab-notebooklm | NOTEBOOKLM |

## Budget System

Daily per-role limits enforced via file-locked JSON (`~/.darklab/logs/spend-YYYY-MM-DD.json`):
- Leader: $50, Academic: $30, Experiment: $20
- `_check_and_record_spend()` is the single atomic check+record function — no separate pre-check
- Paperclip dashboard shows monthly budgets at http://192.168.23.25:3100

## Running Tests

```bash
cd darklab-installer
uv run pytest          # all tests
uv run pytest -x -v    # stop on first failure, verbose
```

`pyproject.toml` sets `pythonpath = ["agents"]` so imports like `from shared.models import Task` resolve correctly.

## Conventions

- Python 3.11+, Pydantic v2, async/await throughout
- Model IDs: `claude-opus-4-6-20260301`, `claude-sonnet-4-6-20260301`
- All shell scripts use `set -euo pipefail`
- Config via env vars loaded by `shared.config.Settings` (dotenv from `~/.darklab/.env`)
- Paths use `settings.darklab_home` (not `Path.home()`) for testability
- Each skill has a `skills/<name>/SKILL.md` matching an entry in the routing table
- Browser automation uses `browser-use` + `langchain-anthropic` (not raw Playwright selectors)

## SSH Access (Leader Mac mini)

```bash
# Username has a space — use expect or quotes
ssh "cyber 02@192.168.23.25"  # password: Opensens26
```
