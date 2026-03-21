# DarkLab — Autonomous AI Research Lab

> Version 3.0 | March 2026

## Mission

**DarkLab** is a general-purpose autonomous AI research lab built on a Mac mini cluster. It performs literature review, simulation, data analysis, and publication-quality output generation across any scientific domain — driven by Telegram commands and governed by Paperclip AI.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Boss (MacBook)                                         │
│  Telegram + Paperclip Dashboard + Opensens Office       │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│  Leader (Mac mini M4 16GB) — 192.168.23.25              │
│                                                         │
│  ┌─────────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ OpenClaw GW │  │ Paperclip│  │ Opensens Office   │  │
│  │ :18789      │  │ :3100    │  │ :5180             │  │
│  └──────┬──────┘  └──────────┘  └───────────────────┘  │
│         │                                               │
│  ┌──────▼──────┐  ┌────────────┐  ┌──────────────┐     │
│  │ PicoClaw    │  │ LiteLLM    │  │ Dozzle       │     │
│  │ (Telegram)  │  │ :4000      │  │ :8081        │     │
│  └─────────────┘  └────────────┘  └──────────────┘     │
│         │                                               │
│    ┌────┴─────────────────────┐                         │
│    ▼                          ▼                         │
│  Academic Agent         Experiment Agent                │
│  (Mac mini M4 24GB)    (Mac mini M4 24GB)              │
│  Research · Literature  Simulation · Analysis           │
│  DOE · Paper · Web      Synthetic · ML · Figures        │
└─────────────────────────────────────────────────────────┘
```

---

## Aims

### Aim 1: Autonomous Literature Research Pipeline
Multi-AI literature search and validation across scientific domains.

**Pipeline**: Perplexity (web search) → Gemini (cross-validation) → Claude (synthesis + critique)

**Deliverables**: Structured literature reviews with citations, gap analysis, research direction recommendations.

### Aim 2: Parametric Simulation & Data Analysis
Computational simulation and statistical analysis for experimental design validation.

**Capabilities**: Monte Carlo sweeps, EIS/CV analysis, statistical hypothesis testing, sensitivity analysis.

**Deliverables**: Parameter maps, confidence intervals, analysis reports.

### Aim 3: Autonomous ML Experimentation
Self-directed machine learning on Apple Silicon (MPS acceleration).

**Capabilities**: Feature engineering, model selection, hyperparameter optimization, AutoResearch loop.

**Deliverables**: Trained models, performance benchmarks, experiment logs.

### Aim 4: Publication-Quality Output Generation
End-to-end deliverable creation from raw findings.

**Capabilities**: Word documents, PowerPoint decks, matplotlib/plotly figures, NotebookLM podcasts.

**Deliverables**: Camera-ready reports, presentation slides, data visualizations, audio summaries.

---

## Agents

### Boss — Chief Executive Officer
- **Type**: Human (Telegram + Dashboard)
- **Budget**: $0/day (human operator)
- **Responsibilities**:
  - Set research direction and priorities
  - Approve multi-step campaigns
  - Review deliverables
  - Monitor agent budgets and health

### DarkLab Leader — Chief Technology Officer
- **Type**: AI (Claude Opus 4.6)
- **Budget**: $50/day ($1,500/month)
- **Responsibilities**:
  - Route commands to correct agent via dispatch table
  - Plan multi-step research campaigns
  - Synthesize findings from Academic and Experiment agents
  - Generate Word/PPTX reports and media
  - Automate NotebookLM for podcast generation

| Command | Description |
|---------|-------------|
| `/synthesize <findings>` | Merge multi-source research into narrative |
| `/report <scope>` | Generate Word/PPTX deliverable |
| `/notebooklm <sources>` | Create NotebookLM podcast/study guide |

### DarkLab Academic — Research Director
- **Type**: AI (Claude Sonnet 4.6 + GPT-4o + Gemini)
- **Budget**: $30/day ($900/month)
- **Responsibilities**:
  - Multi-AI literature search with cross-validation
  - Deep literature reviews with citation chains
  - Design of Experiments (DOE) / Experiment Intent Protocol (EIP)
  - Manuscript drafting (multi-pass with AI review)
  - Web research via Perplexity API + browser automation

| Command | Description |
|---------|-------------|
| `/research <topic>` | Multi-AI literature search |
| `/literature <query>` | Deep review with citations |
| `/doe <spec>` | Design of Experiments |
| `/paper <topic>` | Draft manuscript |
| `/perplexity <query>` | Web research (API + browser) |

### DarkLab Experiment — Lab Director
- **Type**: AI (Claude Sonnet 4.6 + PyTorch MPS)
- **Budget**: $20/day ($600/month)
- **Responsibilities**:
  - Parametric sweep and Monte Carlo simulation
  - Electrochemical analysis (EIS, CV, DPV)
  - Statistical analysis and hypothesis testing
  - Synthetic dataset generation (XRD, CV, BET, sensor data)
  - Publication-quality figure generation
  - Autonomous ML experimentation loop

| Command | Description |
|---------|-------------|
| `/simulate <params>` | Parametric sweep / Monte Carlo |
| `/analyze <data>` | EIS, CV, statistical analysis |
| `/synthetic <spec>` | Generate synthetic datasets |
| `/report-data <scope>` | Publication-quality figures |
| `/autoresearch <program>` | Autonomous ML loop (MPS) |

---

## Workflows

### Simple Research Request
```
Boss: /research "graphene oxide membranes for water filtration"
  → Leader routes to Academic
  → Academic: Perplexity search → Gemini validation → Claude synthesis
  → Academic returns structured findings
  → Leader sends summary to Boss via Telegram
```

### Full Research Campaign
```
Boss: "Complete literature review on perovskite solar cells with simulated performance data"
  → Leader plan_campaign() decomposes into steps:
    1. /research "perovskite solar cells efficiency" → Academic
    2. /literature "perovskite stability degradation" → Academic
    3. /simulate "perovskite IV curve parametric sweep" → Experiment
    4. /report-data "perovskite simulation results" → Experiment
    5. /synthesize [all results] → Leader
    6. /report "perovskite review + simulation" → Leader
  → Boss receives Word document + figures via Telegram
```

### Autonomous Experiment
```
Boss: /autoresearch "optimize battery electrolyte formulation"
  → Leader routes to Experiment
  → Experiment: AutoResearch loop on Apple Silicon MPS
    - Feature engineering → Model training → Evaluation → Iterate
  → Experiment returns best model + performance report
  → Leader synthesizes and forwards to Boss
```

---

## Governance (Paperclip AI)

### Org Chart
```
Boss (CEO, human)
 └── DarkLab Leader (CTO, $50/day)
      ├── DarkLab Academic (Research Director, $30/day)
      └── DarkLab Experiment (Lab Director, $20/day)
```

### Budget Enforcement
- Atomic per-call budget check with `fcntl.LOCK_EX` file lock
- Daily spend tracked in `~/.darklab/logs/spend-YYYY-MM-DD.json`
- Auto-pause when daily limit reached
- Paperclip dashboard shows real-time spend at http://192.168.23.25:3100

### Audit Trail
- All tasks logged to `~/.darklab/logs/audit.jsonl`
- Ed25519 signed payloads for tamper detection
- Config revisions tracked in Paperclip for rollback

---

## Infrastructure

### Docker Stack (Mac Mini Leader)

| Service | Port | Purpose |
|---------|------|---------|
| OpenClaw Gateway | 18789 | Agent orchestration (WebSocket) |
| Paperclip AI | 3100 | Governance dashboard + API |
| Opensens Office | 5180 | Visual agent monitoring |
| PicoClaw | — | Telegram AI agent |
| PicoClaw Exec | — | Sandboxed task executor |
| LiteLLM | 4000 | LLM proxy with model routing |
| Liaison Broker | 8000 | Telegram webhook routing |
| Redis | 6379 | Message queue |
| Caddy | 80 | Static file server |
| Cloudflared | — | Cloudflare tunnel |
| Dozzle | 8081 | Docker log viewer |
| PostgreSQL | 5432 | Paperclip database |

### Access URLs
| Dashboard | URL |
|-----------|-----|
| Paperclip | http://192.168.23.25:3100 |
| Opensens Office | http://192.168.23.25:5180 |
| Dozzle Logs | http://192.168.23.25:8081 |
| OpenClaw WebChat | http://192.168.23.25:18789 |

---

## Next Steps

1. Complete Academic and Experiment Mac mini hardware setup
2. Run end-to-end research campaign to validate full pipeline
3. Tune LLM model routing for cost/quality balance
4. Build custom Paperclip skills for DarkLab-specific workflows
5. Add Lab Agent role for instrument control (future)
