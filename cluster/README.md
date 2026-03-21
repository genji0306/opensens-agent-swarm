# DarkLab Installer

Automated installer for the **DarkLab** distributed AI research cluster — a multi-device Mac mini platform for autonomous scientific research, built on [OpenClaw](https://github.com/nicosql/openclaw) and [Paperclip AI](https://github.com/paperclipai/paperclip).

**Version:** 2.0.0

---

## Architecture

```
 ┌─────────────────────────────────────────────────────┐
 │  Boss (MacBook)                                     │
 │  Telegram + Paperclip Dashboard (http://leader:3100)│
 └──────────────────────┬──────────────────────────────┘
                        │  SSH / HTTP
 ┌──────────────────────▼──────────────────────────────┐
 │  Leader (Mac mini M4, 16GB)                         │
 │  OpenClaw Gateway :18789  │  Paperclip AI :3100     │
 │  Claude OPUS · Gemini · NotebookLM                  │
 ├──────────────────────┬──────────────────────────────┤
 │         WebSocket    │    WebSocket                 │
 │     ┌────────────────┘────────────────┐             │
 ┌─────▼──────────────┐  ┌──────────────▼────────────┐│
 │ Academic Agent      │  │ Experiment Agent          ││
 │ Mac mini M4, 24GB   │  │ Mac mini M4, 24GB         ││
 │ Perplexity · OpenAI │  │ PyTorch MPS · AutoResearch││
 │ Gemini · Claude     │  │ Claude · scikit-learn      ││
 └─────────────────────┘  └──────────────────────────┘│
 └─────────────────────────────────────────────────────┘
```

### Device Roles

| Device | Hardware | Role | Key Services |
|--------|----------|------|--------------|
| **Boss** | MacBook (any) | Command & Control | Paperclip dashboard, shell aliases, cluster scripts |
| **Leader** | Mac mini M4, 16GB | Gateway + Orchestrator | OpenClaw gateway, Paperclip AI, NotebookLM |
| **Academic** | Mac mini M4, 24GB | Research Agent | Literature search, paper drafting, browser automation |
| **Experiment** | Mac mini M4, 24GB | Simulation Agent | Data analysis, simulations, AutoResearch ML loop |

---

## Quick Start

### 1. Install on each device

```bash
git clone <this-repo> ~/darklab-installer
cd ~/darklab-installer
chmod +x install.sh
./install.sh
```

Select the role when prompted:
```
1) Leader      (Mac mini M4 16GB  -- gateway + orchestrator)
2) Academic    (Mac mini M4 24GB  -- research agent)
3) Experiment  (Mac mini M4 24GB  -- simulation agent)
4) Lab Agent   (Mac mini M4 24GB+ -- instrument control [future])
5) Boss        (MacBook           -- command & control dashboard)
```

### 2. Connect the cluster (on Leader)

```bash
# Start the gateway
openclaw gateway start

# Start Paperclip dashboard
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist

# Wait for nodes and approve pairing
./scripts/connect-cluster.sh
```

### 3. Start nodes (on Academic and Experiment)

```bash
openclaw node start
# Note the pairing code, then approve on Leader:
# openclaw pairing approve darklab-academic <CODE>
```

### 4. Verify (from Boss or any device)

```bash
./scripts/test-connectivity.sh   # 6-test diagnostics
./scripts/verify-cluster.sh      # comprehensive check
./scripts/cluster-status.sh      # cluster health overview
```

### 5. Seed Paperclip org chart (on Leader)

```bash
./scripts/seed-paperclip.sh
# Creates: Boss (CEO), Leader (CTO $50/day), Academic ($30/day), Experiment ($20/day)
```

---

## Project Structure

```
darklab-installer/
├── install.sh                          # Main entry point (5-role selector)
│
├── roles/                              # Role-specific installers
│   ├── leader.sh                       # Gateway + Paperclip + exec approvals
│   ├── academic.sh                     # Node-host + research tools + scientific skills
│   ├── experiment.sh                   # Node-host + compute stack + AutoResearch
│   ├── boss.sh                         # Dashboard access + management scripts
│   └── lab-agent.sh                    # Instrument control (future)
│
├── common/                             # Shared setup scripts
│   ├── prerequisites.sh                # Homebrew, Node.js >=22.16.0, Python, uv, pnpm
│   ├── openclaw-setup.sh               # OpenClaw global install
│   ├── python-env.sh                   # Venv + role-specific dependencies
│   ├── keys-setup.sh                   # Ed25519 signing keypair
│   ├── browser-setup.sh                # Chrome profiles (NotebookLM, Perplexity)
│   └── tailscale-setup.sh              # Optional mesh networking
│
├── configs/                            # Configuration files
│   ├── env.template                    # Environment variables template
│   ├── leader.config.yaml              # Gateway config (agents, discovery)
│   ├── academic.config.yaml            # Academic node-host config
│   ├── experiment.config.yaml          # Experiment node-host config
│   ├── exec-approvals.json             # OpenClaw system.run whitelist
│   └── paperclip-openclaw-adapter.json # Paperclip → OpenClaw WebSocket adapter
│
├── agents/                             # Python agent code
│   ├── shared/                         # Shared utilities (8 modules)
│   │   ├── models.py                   # Task, TaskResult, TaskType (15 types)
│   │   ├── config.py                   # Settings from ~/.darklab/.env
│   │   ├── llm_client.py              # Anthropic/OpenAI/Gemini + budget enforcement
│   │   ├── node_bridge.py             # OpenClaw system.run JSON contract
│   │   ├── audit.py                    # JSONL append-only audit log
│   │   ├── crypto.py                   # Ed25519 sign/verify (PyNaCl)
│   │   └── schemas.py                  # EIP + RunRecord Pydantic models
│   ├── academic/                       # Research agent (6 modules)
│   │   ├── research.py                 # Multi-AI literature research
│   │   ├── literature.py               # Deep reviews (Perplexity → Gemini → Claude)
│   │   ├── doe.py                      # Design of Experiments / EIP generation
│   │   ├── paper.py                    # Paper drafting (OpenAI + Claude)
│   │   ├── perplexity.py               # API-first with browser-use fallback
│   │   └── browser_agent.py            # LLM-driven browser automation
│   └── experiment/                     # Simulation agent (5 modules)
│       ├── simulation.py               # Parametric sweep, Monte Carlo
│       ├── analysis.py                 # EIS, CV, statistical analysis
│       ├── synthetic.py                # Synthetic data (XRD, CV, BET, sensors)
│       ├── report_data.py              # Publication-quality figures
│       └── autoresearch.py             # Autonomous ML loop (Apple Silicon MPS)
│
├── skills/                             # 14 OpenClaw skills (SKILL.md + scripts/run.sh)
│   ├── darklab-leader/                 # Routing, coordination, Paperclip governance
│   ├── darklab-synthesis/              # Narrative synthesis from multi-source results
│   ├── darklab-media-gen/              # Word docs, PPTX, infographics
│   ├── darklab-notebooklm/             # NotebookLM browser automation
│   ├── darklab-research/               # Multi-AI literature search
│   ├── darklab-literature/             # Deep reviews with citations
│   ├── darklab-doe/                    # Design of Experiments
│   ├── darklab-paper/                  # Manuscript drafting
│   ├── darklab-perplexity/             # Web research (API + browser fallback)
│   ├── darklab-simulation/             # Parametric simulations
│   ├── darklab-analysis/               # Statistical analysis (EIS, CV, etc.)
│   ├── darklab-synthetic/              # Synthetic dataset generation
│   ├── darklab-report-data/            # Data visualization
│   └── darklab-autoresearch/           # Autonomous ML experimentation
│
└── scripts/                            # Cluster management
    ├── connect-cluster.sh              # Connect devices (gateway + pairing)
    ├── cluster-status.sh               # Health check (OpenClaw native + SSH)
    ├── test-connectivity.sh            # 6-test diagnostics
    ├── verify-cluster.sh               # Comprehensive verification (~400 lines)
    ├── seed-paperclip.sh               # Paperclip org chart seeder
    ├── update-cluster.sh               # Rolling update from Boss
    ├── pair-devices.sh                 # Interactive pairing helper
    ├── setup-notebooklm-profile.sh     # NotebookLM Chrome profile setup (Leader)
    └── backup-cluster.sh               # Backup configs and keys
```

---

## Skills

| Skill | Agent | Purpose |
|-------|-------|---------|
| `darklab-leader` | Leader | Route commands, manage research campaigns, Paperclip governance |
| `darklab-synthesis` | Leader | Merge multi-source findings into coherent narratives |
| `darklab-media-gen` | Leader | Generate Word docs, PPTX, infographics |
| `darklab-notebooklm` | Leader | NotebookLM audio/video summaries via browser |
| `darklab-research` | Academic | Multi-AI literature search (Perplexity + Gemini + Claude) |
| `darklab-literature` | Academic | Deep reviews with structured citations |
| `darklab-doe` | Academic | Design of Experiments / EIP generation |
| `darklab-paper` | Academic | Paper drafting (OpenAI + Claude, LaTeX/Word output) |
| `darklab-perplexity` | Academic | Web research (API-first, browser-use fallback) |
| `darklab-simulation` | Experiment | Parametric sweeps, Monte Carlo, kinetic modeling |
| `darklab-analysis` | Experiment | EIS fitting, CV peak detection, statistical analysis |
| `darklab-synthetic` | Experiment | Synthetic XRD, CV, BET, sensor data generation |
| `darklab-report-data` | Experiment | Publication-quality matplotlib/plotly figures |
| `darklab-autoresearch` | Experiment | Autonomous ML loop on Apple Silicon MPS |

---

## Configuration

### Environment Variables (`~/.darklab/.env`)

| Variable | Devices | Description |
|----------|---------|-------------|
| `DARKLAB_ROLE` | All | `leader`, `academic`, `experiment`, or `boss` |
| `DARKLAB_VERSION` | All | Installer version (2.0.0) |
| `ANTHROPIC_API_KEY` | Leader, Academic, Experiment | Claude API access |
| `GOOGLE_AI_API_KEY` | Leader, Academic | Gemini API access |
| `OPENAI_API_KEY` | Academic | GPT-4o API access |
| `PERPLEXITY_API_KEY` | Academic (optional) | Perplexity API (fallback: browser-use) |
| `TELEGRAM_BOT_TOKEN` | Leader | Telegram bot for Boss commands |
| `DARKLAB_LEADER_HOST` | Academic, Experiment | Leader hostname (e.g., `leader.local`) |
| `DARKLAB_LEADER_PORT` | Academic, Experiment | Gateway port (default: `18789`) |
| `PAPERCLIP_URL` | Leader, Boss | Dashboard URL (`http://leader.local:3100`) |

### Key Config Files

| File | Location | Purpose |
|------|----------|---------|
| `exec-approvals.json` | `~/.openclaw/exec-approvals.json` | Whitelist for `system.run` commands |
| `node.json` | `~/.openclaw/node.json` | Node-host gateway connection config |
| `config.yaml` | `~/.openclaw/config.yaml` | OpenClaw gateway/node configuration |
| `.env` | `~/.darklab/.env` | API keys and role configuration |

---

## Cluster Operations

| Script | Run From | Purpose |
|--------|----------|---------|
| `connect-cluster.sh` | Leader | Start gateway, discover nodes, approve pairing |
| `cluster-status.sh` | Boss/Leader | Health check of all devices and services |
| `test-connectivity.sh` | Any device | DNS, TCP, HTTP, service, and Paperclip diagnostics |
| `verify-cluster.sh` | Any device | Comprehensive component verification (PASS/FAIL/WARN) |
| `seed-paperclip.sh` | Leader | Create org chart in Paperclip (agents + budgets) |
| `update-cluster.sh` | Boss | Rolling update across all devices |
| `pair-devices.sh` | Leader | Interactive pairing of Academic/Experiment nodes |
| `setup-notebooklm-profile.sh` | Leader | Interactive Chrome profile setup for NotebookLM |
| `backup-cluster.sh` | Boss | Backup .env, keys, and configs from all devices |

---

## Security

- **Ed25519 signing keys** — generated per-device via PyNaCl (`~/.darklab/keys/`)
- **Exec approvals** — allowlist-based security for `system.run` commands (`~/.openclaw/exec-approvals.json`)
- **Budget enforcement** — per-role daily limits (Leader $50, Academic $30, Experiment $20) checked before every LLM call
- **API key isolation** — `.env` files with `chmod 600`, never committed to git
- **Tailscale mesh** — optional encrypted networking with MagicDNS

---

## Budget Enforcement

Built into `agents/shared/llm_client.py`:

| Role | Daily Budget | Models |
|------|-------------|--------|
| Leader | $50 | Claude OPUS, Gemini |
| Academic | $30 | Claude Sonnet, GPT-4o, Gemini, Perplexity |
| Experiment | $20 | Claude Sonnet, PyTorch MPS |

- Spend tracked in `~/.darklab/logs/spend-YYYY-MM-DD.json`
- `_check_budget()` called before every API call
- Auto-pause when exceeded; Boss approval required to increase

---

## Prerequisites

Installed automatically by `common/prerequisites.sh`:

| Tool | Version | Purpose |
|------|---------|---------|
| Homebrew | Latest | Package manager |
| Node.js | >=22.16.0 | OpenClaw runtime |
| Python | >=3.11 | Agent code |
| uv | Latest | Fast Python package manager |
| pnpm | Latest | Paperclip build tool |
| Tailscale | Latest (optional) | Mesh networking |

---

## Post-Install Verification

After installing all devices:

```bash
# 1. On Leader: start services
openclaw gateway start
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist

# 2. On Academic/Experiment: start nodes
openclaw node start

# 3. On Leader: connect cluster
./scripts/connect-cluster.sh

# 4. From Boss: verify
./scripts/test-connectivity.sh    # All 6 tests should PASS
./scripts/verify-cluster.sh       # Check PASS/FAIL/WARN summary
open http://leader.local:3100     # Paperclip dashboard

# 5. On Leader: seed org chart
./scripts/seed-paperclip.sh
```

---

## License

Proprietary — Opensens / DarkLab
