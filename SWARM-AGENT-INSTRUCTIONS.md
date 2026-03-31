# Opensens Agent Swarm — Comprehensive Agent Instructions

> Universal instructions for any AI coding agent (Claude Code, Codex, Antigravity, Cursor, Windsurf, etc.) to run all DarkLab swarm agents on a given research topic.

## Quick Start

Given a research topic `<TOPIC>`, run the full swarm pipeline by sending HTTP POST requests to the Leader API at `http://192.168.23.25:8100`. Every command is a slash-prefixed dispatch routed through `dispatch.py`.

```bash
# Health check first
curl http://192.168.23.25:8100/health

# Run any command
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/<COMMAND> <TOPIC>"}'
```

---

## All Available Commands

### Academic Agents (run on Academic Mac mini)

| Command | What it does | Best for |
|---------|-------------|----------|
| `/research <topic>` | Literature search + gap analysis | Starting point — survey a field |
| `/literature <query>` | Deep literature review | Thorough bibliography on a specific question |
| `/doe <spec>` | Design of Experiments | Experimental design, parameter selection |
| `/paper <topic>` | Draft a paper | Generate a structured research paper |
| `/perplexity <query>` | Web research via Perplexity | Current events, non-academic info |

### Experiment Agents (run on Experiment Mac mini)

| Command | What it does | Best for |
|---------|-------------|----------|
| `/simulate <params>` | Run simulations | Computational experiments |
| `/analyze <data>` | Analyze data | Statistical analysis, data interpretation |
| `/synthetic <spec>` | Generate synthetic datasets | Training data, test datasets |
| `/report-data <scope>` | Publication-quality visualizations | Charts, figures, data plots |
| `/autoresearch <program>` | Autonomous ML training loop | Automated model training |
| `/parametergolf <spec>` | Parameter optimization | Hyperparameter tuning, search space optimization |

### Leader Agents (run locally on Leader Mac mini)

| Command | What it does | Best for |
|---------|-------------|----------|
| `/synthesize <topic>` | Synthesize findings from multiple agents | Combining results across runs |
| `/report <scope>` | Generate formatted report | Final deliverable reports |
| `/notebooklm <sources>` | Audio/study guide via NotebookLM | Audio summaries, study materials |
| `/deerflow <objective>` | Deep multi-step research (DeerFlow 2.0) | Complex research with sub-agents and artifacts |
| `/deepresearch <topic>` | Iterative deep research with academic sources | Converging research with quality scoring |
| `/swarmresearch <topic>` | 5-angle parallel research + synthesis | Multi-perspective comprehensive research |
| `/debate <topic>` | Multi-agent debate simulation (MiroShark) | Testing hypotheses, exploring counterarguments |

### Full Swarm Pipeline (run on Leader Mac mini)

| Command | What it does | Best for |
|---------|-------------|----------|
| `/fullswarm auto <topic>` | All 18 steps, fully autonomous | Overnight research, batch topics |
| `/fullswarm semi <topic>` | Discovery + analysis, pause for review | Guided research with checkpoint |
| `/fullswarm manual <topic>` | Show plan, require approval first | Budget-conscious, unfamiliar topics |
| `/fullswarm resume <id>` | Resume a paused or planned run | Continue after review |
| `/fullswarm status` | List all swarm runs | Monitor progress |
| `/fullswarm results` | List completed runs | Review outputs |

### RL / System Commands

| Command | What it does |
|---------|-------------|
| `/rl-train` | Start RL self-evolution training cycle |
| `/rl-status` | Check RL training status |
| `/rl-rollback` | Rollback to previous RL checkpoint |
| `/rl-freeze` | Freeze current RL baseline |
| `/turboq-status` | TurboQuant KV cache pool status |
| `/results` | List recent deep research results |
| `/schedule add\|list\|remove` | Manage recurring auto-research schedules |
| `/boost on\|off\|status` | Toggle AIClient boost tier |
| `/status` | Cluster health check |

---

## Full Swarm Run: Step-by-Step Protocol

To run **all agents** on a single topic, execute the following sequence. Each step builds on prior results. The recommended order respects the DAG dependencies.

### Phase 1: Discovery (parallel)

Run these simultaneously — they are independent:

```bash
# 1a. Literature survey
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/research <TOPIC>"}'

# 1b. Deep literature review
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/literature <TOPIC>"}'

# 1c. Web research
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/perplexity <TOPIC> latest advances 2025-2026"}'

# 1d. DeerFlow deep research
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/deerflow <TOPIC>"}'
```

### Phase 2: Deep Analysis (parallel, after Phase 1)

```bash
# 2a. Iterative deep research (searches 9 academic sources, converges to quality >= 0.75)
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/deepresearch <TOPIC>"}'

# 2b. 5-perspective swarm research
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/swarmresearch <TOPIC>"}'

# 2c. Multi-agent debate to stress-test findings
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/debate <TOPIC>"}'
```

### Phase 3: Experimentation (after Phase 1-2 results)

```bash
# 3a. Design experiments based on findings
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/doe Design experiments for <TOPIC> based on literature gaps"}'

# 3b. Generate synthetic data
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/synthetic Generate training dataset for <TOPIC>"}'

# 3c. Run simulations
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/simulate Run simulation for <TOPIC>"}'

# 3d. Analyze results
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/analyze Analyze simulation and research results for <TOPIC>"}'
```

### Phase 4: Optimization (optional, after Phase 3)

```bash
# 4a. Parameter optimization
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/parametergolf Optimize parameters for <TOPIC>"}'

# 4b. Autonomous ML loop
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/autoresearch Train models for <TOPIC>"}'
```

### Phase 5: Synthesis & Deliverables (after all prior phases)

```bash
# 5a. Synthesize all findings
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/synthesize Synthesize all research findings on <TOPIC>"}'

# 5b. Generate data visualizations
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/report-data Generate publication-quality visualizations for <TOPIC>"}'

# 5c. Generate final report
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/report Generate comprehensive report on <TOPIC>"}'

# 5d. Draft paper
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/paper Write research paper on <TOPIC>"}'

# 5e. Generate audio study guide (optional)
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/notebooklm Generate audio overview of <TOPIC> research"}'
```

### Phase 6: Review Results

```bash
# Check what was produced
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/results"}'
```

---

## Free-Form Dispatch (Auto Campaign Planning)

Instead of manually sequencing commands, you can send a free-form research request. The Leader will use Claude to decompose it into a multi-step campaign with dependency tracking:

```bash
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "Conduct a comprehensive investigation of <TOPIC>. Survey the literature, identify gaps, design experiments, run simulations, analyze results, debate findings, and produce a final paper with visualizations."}'
```

The Leader will:
1. Call `plan_campaign()` — Claude decomposes the request into ordered steps with `depends_on` DAG
2. Create a Paperclip governance issue for tracking
3. Request approval for multi-step campaigns (>1 step)
4. Execute via `CampaignEngine` with parallel step execution where dependencies allow
5. Emit DRVP events throughout for real-time monitoring

---

## Python API (Programmatic Access)

For agents running in the same Python environment:

```python
import asyncio
import httpx

LEADER_URL = "http://192.168.23.25:8100"
API_KEY = "your-darklab-api-key"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

async def dispatch(command: str) -> dict:
    """Send a command to the Leader dispatch endpoint."""
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{LEADER_URL}/dispatch",
            json={"text": command},
            headers=HEADERS,
        )
        resp.raise_for_status()
        return resp.json()

async def run_full_swarm(topic: str):
    """Run all swarm agents on a topic in dependency order."""

    # Phase 1: Discovery (parallel)
    phase1 = await asyncio.gather(
        dispatch(f"/research {topic}"),
        dispatch(f"/literature {topic}"),
        dispatch(f"/perplexity {topic} latest advances"),
        dispatch(f"/deerflow {topic}"),
    )
    print(f"Phase 1 complete: {len(phase1)} results")

    # Phase 2: Deep analysis (parallel)
    phase2 = await asyncio.gather(
        dispatch(f"/deepresearch {topic}"),
        dispatch(f"/swarmresearch {topic}"),
        dispatch(f"/debate {topic}"),
    )
    print(f"Phase 2 complete: {len(phase2)} results")

    # Phase 3: Experimentation (sequential — each depends on prior)
    doe_result = await dispatch(f"/doe Design experiments for {topic}")
    synth_result = await dispatch(f"/synthetic Generate data for {topic}")
    sim_result = await dispatch(f"/simulate Run simulation for {topic}")
    analysis_result = await dispatch(f"/analyze Analyze results for {topic}")
    print("Phase 3 complete: experimentation done")

    # Phase 4: Optimization (parallel)
    phase4 = await asyncio.gather(
        dispatch(f"/parametergolf Optimize parameters for {topic}"),
        dispatch(f"/autoresearch Train models for {topic}"),
    )
    print(f"Phase 4 complete: {len(phase4)} results")

    # Phase 5: Deliverables (sequential)
    await dispatch(f"/synthesize Synthesize all findings on {topic}")
    await dispatch(f"/report-data Generate visualizations for {topic}")
    await dispatch(f"/report Comprehensive report on {topic}")
    await dispatch(f"/paper Research paper on {topic}")
    await dispatch(f"/notebooklm Audio overview of {topic}")
    print("Phase 5 complete: all deliverables generated")

    # Check results
    results = await dispatch("/results")
    return results

# Run it
asyncio.run(run_full_swarm("room-temperature superconductors"))
```

---

## One-Command Full Swarm (Recommended)

Run the entire 18-step pipeline with a single command. Three modes available:

```bash
# AUTONOMOUS (overnight, $0 cost with local LLM)
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/fullswarm auto <TOPIC>"}'

# SEMI-MANUAL (runs discovery + analysis, pauses for review)
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/fullswarm semi <TOPIC>"}'
# ... review results, then resume:
# curl -X POST ... -d '{"text": "/fullswarm resume <RUN_ID>"}'

# MANUAL (shows plan, requires approval)
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/fullswarm manual <TOPIC>"}'
```

From Telegram: just send `/fullswarm auto quantum error correction`

---

## Minimal Run (3 Commands)

For a quick research pass on any topic with just the essentials:

```bash
# 1. Deep research with convergence (searches 9 academic sources)
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/deepresearch <TOPIC>"}'

# 2. Multi-perspective swarm research
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/swarmresearch <TOPIC>"}'

# 3. Synthesize into final report
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DARKLAB_API_KEY" \
  -d '{"text": "/synthesize Synthesize deepresearch and swarmresearch on <TOPIC>"}'
```

---

## DAG Dependency Map

```
             /research ─────┐
             /literature ───┤
             /perplexity ───┼──→ /deepresearch ──→ /doe ──→ /simulate ──→ /analyze ──┐
             /deerflow ─────┤    /swarmresearch ──────────────────────────────────────┤
                            │    /debate ─────────────────────────────────────────────┤
                            │                                                         │
                            │    /synthetic ──→ /autoresearch ──→ /parametergolf ─────┤
                            │                                                         │
                            └──→ /synthesize ←────────────────────────────────────────┘
                                      │
                                      ├──→ /report-data
                                      ├──→ /report
                                      ├──→ /paper
                                      └──→ /notebooklm
```

---

## Environment Setup

### Required Environment Variables

Set these in `~/.darklab/.env` or export before running:

```bash
# Core
DARKLAB_API_KEY=<leader-api-key>

# AI Providers (at least one required)
ANTHROPIC_API_KEY=<key>             # Claude (primary)
OPENAI_API_KEY=<key>                # GPT fallback
GEMINI_API_KEY=<key>                # Gemini fallback
PERPLEXITY_API_KEY=<key>            # Perplexity search

# Governance (Paperclip)
DARKLAB_PAPERCLIP_URL=http://192.168.23.25:3100
DARKLAB_PAPERCLIP_API_KEY=<key>
DARKLAB_PAPERCLIP_COMPANY_ID=<uuid>
DARKLAB_PAPERCLIP_AGENT_ID=<uuid>

# Memory (OpenViking)
DARKLAB_OPENVIKING_URL=http://192.168.23.25:8200

# Redis (DRVP events)
DARKLAB_REDIS_URL=redis://192.168.23.25:6379

# RL (optional)
DARKLAB_RL_ENABLED=true
DARKLAB_MIROSHARK_ENABLED=true

# Boost (optional — free AIClient models)
DARKLAB_BOOST_ENABLED=true
DARKLAB_AICLIENT_BASE_URL=http://localhost:8787

# TurboQuant (optional — KV cache compression)
DARKLAB_TURBOQUANT_ENABLED=true
DARKLAB_TURBOQUANT_BITS=4
DARKLAB_TURBOQUANT_POOL_MB=4096
```

### Network Topology

```
Agent's machine ──HTTP──→ Leader (192.168.23.25:8100) ──→ Academic Mac mini
                                                      ──→ Experiment Mac mini
                                                      ──→ Redis (DRVP events)
                                                      ──→ Paperclip (governance)
                                                      ──→ LiteLLM (model routing)
                                                      ──→ Ollama (local models)
```

---

## Monitoring

### DRVP Event Stream (real-time)

Subscribe to the SSE endpoint to watch all agent activity:

```bash
curl -N http://192.168.23.25:8100/drvp/events/<COMPANY_ID>
```

Events emitted during a full swarm run:
- `request.created` — dispatch received
- `handoff.initiated` / `handoff.completed` — agent-to-agent routing
- `llm.call.started` / `llm.call.completed` — every LLM call with model + tokens
- `campaign.step.started` / `campaign.step.completed` — campaign progress
- `deep_research.iteration` / `deep_research.scored` — convergence tracking
- `debate.round` — debate simulation rounds
- `budget.warning` / `budget.exhausted` — cost alerts
- `request.completed` / `request.failed` — final status

### Dashboards

- **Opensens Office**: http://192.168.23.25:5180 — visual agent floor plan, 3D view, panels
- **Paperclip AI**: http://192.168.23.25:3100 — governance, costs, issues, approvals
- **Dozzle**: http://192.168.23.25:8081 — Docker container logs

---

## Budget Awareness

Daily per-role limits:
- **Leader**: $50/day, $1,500/month
- **Academic**: $30/day, $900/month
- **Experiment**: $20/day, $600/month

A full swarm run on a single topic costs approximately **$5-15** depending on depth and model selection. Use `/boost on` to route eligible tasks through free AIClient models (Gemini Flash, Grok) to reduce costs.

The pre-dispatch hook will block requests if budget is exhausted. Check with `/boost status`.

---

## Output Locations

Results are stored in the project under:

| Output | Location |
|--------|----------|
| Deep research reports | `results/research/YYYY-MM-DD_<slug>.md` |
| Research lessons | `results/research/YYYY-MM-DD_<slug>_lessons.md` |
| Source citations | `results/research/YYYY-MM-DD_<slug>_sources.json` |
| Debate transcripts | `results/debates/` |
| Knowledge base | `~/.darklab/knowledge/knowledge.jsonl` |
| Global lessons | `~/.darklab/knowledge/global_lessons.jsonl` |
| Audit trail | `~/.darklab/logs/audit.jsonl` |
| Spend tracking | `~/.darklab/logs/spend-YYYY-MM-DD.json` |
| RL rollouts | `~/.darklab/rl/rollouts/` |
| Generated artifacts | Returned in `TaskResult.artifacts[]` paths |

---

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Missing/wrong `DARKLAB_API_KEY` | Set `Authorization: Bearer <key>` header |
| `budget_exhausted` | Daily limit hit | Wait for next day or `/boost on` |
| `swarm_unavailable` | LangGraph not installed | Free-form requests fall back to `plan_campaign()` |
| `local_handler_failed` | Agent dependency missing | Check `uv pip install` for the handler's deps |
| `http_forward_failed` | Academic/Experiment node unreachable | Check SSH to node, verify service is running |
| Timeout (120s default) | Long-running research | Increase `httpx.AsyncClient(timeout=...)` |

---

## Example: Full Run on "Quantum Error Correction"

```bash
export TOPIC="quantum error correction codes for fault-tolerant quantum computing"
export API="http://192.168.23.25:8100/dispatch"
export AUTH="Authorization: Bearer $DARKLAB_API_KEY"
export CT="Content-Type: application/json"

# Phase 1 — Discovery (run all 4 in parallel)
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/research $TOPIC\"}" &
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/literature $TOPIC\"}" &
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/perplexity $TOPIC latest 2025-2026\"}" &
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/deerflow $TOPIC\"}" &
wait

# Phase 2 — Deep analysis
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/deepresearch $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/swarmresearch $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/debate $TOPIC\"}"

# Phase 3 — Experiments
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/doe Design experiments for $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/synthetic Generate training data for $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/simulate $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/analyze $TOPIC results\"}"

# Phase 4 — Optimize
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/parametergolf $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/autoresearch $TOPIC\"}"

# Phase 5 — Deliverables
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/synthesize All findings on $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/report-data Visualizations for $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/report Final report on $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/paper Research paper on $TOPIC\"}"
curl -X POST $API -H "$CT" -H "$AUTH" -d "{\"text\": \"/notebooklm Audio overview of $TOPIC\"}"

# Check all results
curl -X POST $API -H "$CT" -H "$AUTH" -d '{"text": "/results"}'
```

---

## Agent-Specific Notes

### For Claude Code / Codex
- Use `Bash` tool to execute `curl` commands
- Parse JSON responses to chain results between phases
- Use `asyncio` Python script for parallel execution

### For Cursor / Windsurf / Antigravity
- Use terminal to run the bash commands above
- Or use the Python `httpx` script in a scratch file
- Results come back as JSON — pipe through `jq` for readability

### For Telegram (via PicoClaw)
- Just send the slash command directly in chat: `/deepresearch <TOPIC>`
- PicoClaw forwards to Leader dispatch with full governance

### For LangGraph Swarm (internal)
- Free-form text (no slash command) triggers the swarm router
- The swarm uses leader LLM to select the best agent automatically
- Falls back to `plan_campaign()` if swarm is unavailable
