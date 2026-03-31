# Memento-Skills + Codex-AutoResearch Integration Plan

## Autonomous Research Agent Swarm for Mac Mini M4 (16GB RAM)

**Goal:** Users send a research topic via Telegram → Codex-AutoResearch conducts research → Memento-Skills creates and refines a swarm of specialist agents → iterative improvement until satisfactory quality → result delivered via Telegram.

---

## 1. Conceptual Architecture

```
                         ┌─────────────────────────────┐
                         │       TELEGRAM USER          │
                         │    /research <topic>          │
                         └──────────┬──────────────────┘
                                    │
                         ┌──────────▼──────────────────┐
                         │    LIAISON-BROKER (Go)        │
                         │    __dispatch handler         │
                         └──────────┬──────────────────┘
                                    │
                    ┌───────────────▼───────────────────┐
                    │     RESEARCH ORCHESTRATOR          │
                    │     (Python daemon on Mac mini)     │
                    │                                     │
                    │  ┌─────────┐    ┌──────────────┐   │
                    │  │ Phase 1 │    │   Phase 2    │   │
                    │  │ CODEX   │───▶│  MEMENTO     │   │
                    │  │ Research│◀───│  Refinement  │   │
                    │  └─────────┘    └──────────────┘   │
                    │        │               │            │
                    │        ▼               ▼            │
                    │  ┌──────────────────────────────┐  │
                    │  │    CONVERGENCE EVALUATOR      │  │
                    │  │  Quality ≥ threshold? DONE    │  │
                    │  └──────────────────────────────┘  │
                    └───────────────┬───────────────────┘
                                    │
                         ┌──────────▼──────────────────┐
                         │   TELEGRAM REPORT            │
                         │   Structured research output  │
                         └─────────────────────────────┘
```

---

## 2. Detailed Workflow

### Phase 1: Research Generation (Codex-AutoResearch)

```
Input: "What are the latest advances in solid-state batteries?"
                    │
                    ▼
        ┌───────────────────────┐
        │  INTERACTION WIZARD   │
        │  (auto-configured)    │
        │                       │
        │  goal: comprehensive  │
        │  metric: quality_score│
        │  verify: eval script  │
        │  direction: higher    │
        └───────────┬───────────┘
                    │
            ┌───────▼────────┐
            │  RESEARCH LOOP │
            │                │
            │  1. Read prior │
            │  2. Baseline   │
            │  3. Ideate     │ ← 4 perspectives (optimist/skeptic/
            │  4. Search     │   historian/minimalist)
            │  5. Synthesize │
            │  6. Verify     │ ← quality metric check
            │  7. Decide     │ ← keep/discard/refine
            │  8. Log        │
            └───────┬────────┘
                    │
                    ▼
          Draft Research Output
          (papers, synthesis, gaps)
```

### Phase 2: Agent Refinement (Memento-Skills)

```
Draft Research Output
          │
          ▼
  ┌───────────────────────────────────────┐
  │        MEMENTO SKILL SWARM            │
  │                                        │
  │  ┌──────────┐  ┌──────────────────┐   │
  │  │ INTENT   │  │ Agent Pool       │   │
  │  │ Classify │  │                  │   │
  │  └────┬─────┘  │ ┌──────────────┐ │   │
  │       │        │ │ fact-checker  │ │   │
  │       ▼        │ │ (verify claims│ │   │
  │  ┌──────────┐  │ │  with sources)│ │   │
  │  │ PLANNING │  │ └──────────────┘ │   │
  │  │ Decompose│  │ ┌──────────────┐ │   │
  │  │ into     │  │ │ gap-finder   │ │   │
  │  │ sub-tasks│  │ │ (identify    │ │   │
  │  └────┬─────┘  │ │  missing     │ │   │
  │       │        │ │  areas)      │ │   │
  │       ▼        │ └──────────────┘ │   │
  │  ┌──────────┐  │ ┌──────────────┐ │   │
  │  │ EXECUTE  │  │ │ synthesizer  │ │   │
  │  │ Skills   │──│ │ (merge and   │ │   │
  │  │ in       │  │ │  structure)  │ │   │
  │  │ sandbox  │  │ └──────────────┘ │   │
  │  └────┬─────┘  │ ┌──────────────┐ │   │
  │       │        │ │ critic       │ │   │
  │       ▼        │ │ (score and   │ │   │
  │  ┌──────────┐  │ │  improve)    │ │   │
  │  │ REFLECT  │  │ └──────────────┘ │   │
  │  │ Evaluate │  └──────────────────┘   │
  │  │ results  │                          │
  │  └────┬─────┘                          │
  │       │                                │
  │       ▼                                │
  │  Skills updated, agents refined        │
  └───────────────────┬───────────────────┘
                      │
                      ▼
              Refined Research Output
```

### Phase 3: Convergence Loop

```
┌──────────────────────────────────────────────┐
│           CONVERGENCE EVALUATOR              │
│                                              │
│  Criteria (all must pass):                   │
│  ┌────────────────────────────────────────┐  │
│  │ 1. Completeness  ≥ 0.8  (all gaps     │  │
│  │                          addressed)    │  │
│  │ 2. Source Quality ≥ 0.7  (cited papers,│  │
│  │                          verified)     │  │
│  │ 3. Structure      ≥ 0.8  (sections,   │  │
│  │                          flow, logic)  │  │
│  │ 4. Novelty        ≥ 0.5  (non-trivial │  │
│  │                          insights)     │  │
│  │ 5. Error-Free     = 1.0  (no factual  │  │
│  │                          errors found) │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  Score = weighted average                    │
│  Threshold = 0.75 (configurable)             │
│                                              │
│  ┌─────────┐     ┌──────────────────────┐   │
│  │ score < │────▶│ Feed back to Phase 1 │   │
│  │  0.75   │     │ with gap analysis    │   │
│  └─────────┘     └──────────────────────┘   │
│                                              │
│  ┌─────────┐     ┌──────────────────────┐   │
│  │ score ≥ │────▶│ DONE → Telegram      │   │
│  │  0.75   │     │ report               │   │
│  └─────────┘     └──────────────────────┘   │
│                                              │
│  Max iterations: 5 (safety cap)              │
└──────────────────────────────────────────────┘
```

---

## 3. Technical Implementation

### 3.1 Directory Structure

```
~/.darklab/
├── memento-codex/
│   ├── orchestrator.py          # Main daemon
│   ├── codex_phase.py           # Codex-AutoResearch wrapper
│   ├── memento_phase.py         # Memento-Skills wrapper
│   ├── evaluator.py             # Convergence scoring
│   ├── telegram_reporter.py     # Result formatting + delivery
│   ├── config.yaml              # System configuration
│   └── workspaces/              # Per-request isolated workspaces
│       └── <request-id>/
│           ├── research-results.tsv
│           ├── autoresearch-state.json
│           ├── autoresearch-lessons.md
│           ├── draft.md
│           ├── refined.md
│           └── skills/          # Memento skills created for this task
│
├── memento/                     # Memento-Skills installation
│   ├── skills/                  # Shared skill library (persists)
│   │   ├── web-search/
│   │   ├── paper-search/        # Custom: arXiv + Semantic Scholar
│   │   ├── fact-checker/
│   │   ├── gap-finder/
│   │   ├── synthesizer/
│   │   └── critic/
│   └── db/                      # SQLite (sessions, skills, embeddings)
│
└── codex-autoresearch/          # Codex-AutoResearch installation
    ├── scripts/
    └── references/
```

### 3.2 Component Installation

```bash
# On Mac Mini (192.168.23.25)
export PATH="$HOME/.bun/bin:/opt/homebrew/bin:$PATH"

# 1. Install Memento-Skills
cd ~/darklab
git clone https://github.com/Memento-Teams/Memento-Skills.git memento
cd memento
uv venv --python 3.13 .venv
uv pip install -e ".[all]"

# 2. Install Codex-AutoResearch
cd ~/darklab
git clone https://github.com/leo-lilinxiao/codex-autoresearch.git codex-autoresearch

# 3. Install shared dependencies
uv pip install httpx pyyaml structlog
```

### 3.3 Orchestrator Implementation

```python
# ~/.darklab/memento-codex/orchestrator.py (conceptual)

class ResearchOrchestrator:
    """
    Main daemon that coordinates Codex-AutoResearch + Memento-Skills.
    Polls claude-peers or HTTP endpoint for incoming requests.
    """

    def __init__(self, config_path: str):
        self.config = load_config(config_path)
        self.codex = CodexPhase(self.config)
        self.memento = MementoPhase(self.config)
        self.evaluator = ConvergenceEvaluator(self.config)
        self.telegram = TelegramReporter(self.config)

    async def handle_request(self, topic: str, request_id: str):
        """Full research pipeline: research → refine → converge → report."""

        workspace = create_workspace(request_id)
        self.telegram.send(f"🔬 Starting research: {topic}")

        iteration = 0
        max_iterations = self.config.get("max_iterations", 5)

        while iteration < max_iterations:
            iteration += 1
            self.telegram.send(f"📊 Iteration {iteration}/{max_iterations}...")

            # Phase 1: Codex-AutoResearch generates/improves draft
            draft = await self.codex.research(
                topic=topic,
                workspace=workspace,
                prior_feedback=self.evaluator.last_feedback,
                lessons=workspace / "autoresearch-lessons.md",
            )

            # Phase 2: Memento-Skills refines via agent swarm
            refined = await self.memento.refine(
                draft=draft,
                workspace=workspace,
                skills=["fact-checker", "gap-finder", "synthesizer", "critic"],
            )

            # Phase 3: Evaluate convergence
            score, feedback = await self.evaluator.evaluate(refined)

            if score >= self.config.get("threshold", 0.75):
                self.telegram.send_report(refined, score, iteration)
                return

            # Feed gaps back to next iteration
            self.evaluator.last_feedback = feedback
            self.telegram.send(
                f"⚡ Score: {score:.2f}/1.0 — refining (gaps: {feedback[:100]})"
            )

        # Max iterations reached
        self.telegram.send_report(refined, score, iteration, partial=True)
```

### 3.4 Codex Phase Wrapper

```python
# ~/.darklab/memento-codex/codex_phase.py (conceptual)

class CodexPhase:
    """Wraps Codex-AutoResearch's modify-verify-decide loop for research."""

    async def research(self, topic, workspace, prior_feedback, lessons):
        # Auto-configure the interaction wizard
        config = {
            "goal": f"Comprehensive research on: {topic}",
            "metric_name": "research_quality",
            "metric_command": f"python3 evaluate_draft.py {workspace}/draft.md",
            "metric_direction": "higher",
            "scope": [str(workspace)],
            "max_iterations": 10,  # Inner loop iterations
        }

        if prior_feedback:
            config["goal"] += f"\n\nAddress these gaps:\n{prior_feedback}"

        # Run the Codex loop (uses Ollama llama3.1:8b locally)
        state = init_state(config, workspace)
        for i in range(config["max_iterations"]):
            hypothesis = ideate(state, lessons)      # 4-perspective generation
            draft = modify(state, hypothesis)         # Apply research changes
            metric = verify(state, draft)             # Score the draft
            decision = decide(state, metric)          # Keep/discard

            if decision == "keep":
                state.update(metric)
            elif state.consecutive_discards >= 3:
                pivot(state)                          # Try different approach

        return workspace / "draft.md"
```

### 3.5 Memento Phase Wrapper

```python
# ~/.darklab/memento-codex/memento_phase.py (conceptual)

class MementoPhase:
    """Wraps Memento-Skills' agent framework for research refinement."""

    def __init__(self, config):
        self.skill_provider = SkillProvider.create_default()

    async def refine(self, draft, workspace, skills):
        draft_text = draft.read_text()

        # Run each refinement skill in sequence
        refined = draft_text

        # 1. Fact-checker: verify claims against sources
        result = await self.execute_skill("fact-checker", {
            "request": f"Verify all claims in this research:\n\n{refined}",
            "workspace": str(workspace),
        })
        if result.success:
            refined = apply_corrections(refined, result.output)

        # 2. Gap-finder: identify missing topics
        result = await self.execute_skill("gap-finder", {
            "request": f"Identify gaps in this research:\n\n{refined}",
        })
        gaps = result.output if result.success else ""

        # 3. Synthesizer: fill gaps and restructure
        result = await self.execute_skill("synthesizer", {
            "request": f"Improve this research by addressing gaps:\n\nResearch:\n{refined}\n\nGaps:\n{gaps}",
        })
        if result.success:
            refined = result.output

        # 4. Critic: final quality scoring
        result = await self.execute_skill("critic", {
            "request": f"Score this research 0-1 on: completeness, sources, structure, novelty, accuracy:\n\n{refined}",
        })

        (workspace / "refined.md").write_text(refined)
        return workspace / "refined.md"

    async def execute_skill(self, skill_name, args):
        skill = self.skill_provider.get(skill_name)
        return await skill.execute(args)
```

---

## 4. Mac Mini M4 16GB Resource Management

### 4.1 Memory Budget

```
┌──────────────────────────────────────────────┐
│          16GB RAM ALLOCATION                  │
├──────────────────────────────────────────────┤
│                                              │
│  macOS System          ~3.0 GB               │
│  Docker Services       ~2.5 GB               │
│  ├─ Paperclip           0.5 GB               │
│  ├─ PostgreSQL           0.5 GB               │
│  ├─ Redis                0.1 GB               │
│  ├─ LiteLLM              0.3 GB               │
│  ├─ Leader               0.5 GB               │
│  ├─ Liaison-Broker        0.1 GB               │
│  └─ Other (caddy etc)    0.5 GB               │
│                                              │
│  Ollama llama3.1:8b    ~4.0 GB               │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │ RESEARCH PIPELINE    ~4.0 GB         │    │
│  │ ├─ Orchestrator       0.2 GB         │    │
│  │ ├─ Codex Phase        0.5 GB         │    │
│  │ ├─ Memento Skills     0.5 GB         │    │
│  │ │  ├─ SQLite + cache  0.2 GB         │    │
│  │ │  └─ UV sandbox      0.3 GB         │    │
│  │ ├─ Paper Search       0.3 GB         │    │
│  │ └─ Headroom           2.5 GB         │    │
│  └──────────────────────────────────────┘    │
│                                              │
│  Swap available        ~8.0 GB (SSD)         │
│                                              │
│  Total: ~13.5 GB active + 2.5 GB headroom    │
└──────────────────────────────────────────────┘
```

### 4.2 Performance Optimizations

| Strategy | Implementation | Impact |
|----------|---------------|--------|
| **Sequential not parallel** | Run Codex then Memento, never both | -50% peak RAM |
| **Ollama model sharing** | Single llama3.1:8b instance via API | -4GB vs dual |
| **Lazy skill loading** | Load Memento skills on-demand, not all at startup | -200MB |
| **Workspace cleanup** | Delete intermediate files after each iteration | -500MB |
| **Streaming verify** | Codex verify commands use streaming output | -100MB |
| **SQLite WAL mode** | Memento DB in WAL mode for concurrent reads | Better I/O |
| **Embedding offload** | Use LiteLLM for embeddings, not local model | -2GB |

### 4.3 Timing Estimates

| Phase | Duration | Bottleneck |
|-------|----------|-----------|
| Paper search (arXiv + S2) | 5-10s | Network I/O |
| Codex inner loop (×10) | 2-5 min | Ollama inference (12s/call × 10) |
| Memento fact-checker | 30-60s | Ollama + web verification |
| Memento gap-finder | 15-30s | Ollama inference |
| Memento synthesizer | 30-60s | Ollama inference |
| Memento critic | 15-30s | Ollama inference |
| Convergence eval | 5-10s | Ollama scoring |
| **Total per iteration** | **5-10 min** | |
| **Full pipeline (3-5 iters)** | **15-50 min** | |

---

## 5. Telegram Integration

### 5.1 Command Registration

Add to liaison-broker `docker-compose.yml`:
```yaml
LB_COMMANDS__DEEPRESEARCH: "__dispatch"
```

Add to Leader dispatch routing table:
```python
"deepresearch": Route("leader", "darklab-deepresearch", TaskType.DEEP_RESEARCH),
```

### 5.2 User Interaction Flow

```
User:  /deepresearch solid-state battery commercialization timeline

Bot:   🔬 Starting deep research: solid-state battery commercialization timeline
       Estimated time: 15-30 minutes
       I'll send updates as I progress.

Bot:   📊 Iteration 1/5 — Searching arXiv, Semantic Scholar...
       Found 12 papers. Generating initial synthesis...

Bot:   ⚡ Iteration 1 score: 0.62/1.0
       Gaps: missing cost analysis, no timeline projections
       Refining...

Bot:   📊 Iteration 2/5 — Addressing cost + timeline gaps...

Bot:   ⚡ Iteration 2 score: 0.71/1.0
       Gaps: weak source diversity
       Refining...

Bot:   📊 Iteration 3/5 — Broadening sources...

Bot:   ✅ Iteration 3 score: 0.82/1.0 — Quality threshold met!

Bot:   📋 DarkLab Deep Research Report
       ━━━━━━━━━━━━━━━━━━━━━━━━━━
       Topic: Solid-State Battery Commercialization Timeline
       Quality: 0.82/1.0 (3 iterations, 22 minutes)
       Sources: 18 papers, 7 industry reports

       [Full structured report with citations...]
```

### 5.3 Progress Reporting

```python
class TelegramReporter:
    def __init__(self, bot_token, chat_id="1269510690"):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text):
        """Send a progress update."""
        httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": self.chat_id, "text": text[:4000]},
        )

    def send_report(self, result_path, score, iterations, partial=False):
        """Send the final formatted report."""
        result = Path(result_path).read_text()
        status = "✅" if not partial else "⚠️ Partial"
        header = (
            f"{status} DarkLab Deep Research Report\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Quality: {score:.2f}/1.0 ({iterations} iterations)\n\n"
        )
        self.send(header + result[:3500])
```

---

## 6. Iterative Refinement: Ensuring Convergence

### 6.1 Quality Metrics

| Metric | Weight | How Measured | Source |
|--------|--------|-------------|--------|
| Completeness | 0.25 | % of sub-topics covered | Gap-finder skill |
| Source Quality | 0.25 | Peer-reviewed ratio + citation count | Paper search metadata |
| Structure | 0.20 | Sections present, logical flow | Critic skill rubric |
| Novelty | 0.15 | Non-trivial insights vs. generic statements | Critic skill |
| Accuracy | 0.15 | Claims verified against sources | Fact-checker skill |

### 6.2 Stuck Recovery (from Codex-AutoResearch)

```
Iteration 1-2:  Normal research + refine loop
Iteration 3:    If score not improving → REFINE strategy
                (different search queries, broader sources)
Iteration 4:    Still stuck → PIVOT approach
                (change research angle entirely)
Iteration 5:    Hard cap → deliver best result with caveats
```

### 6.3 Cross-Run Learning (from Memento-Skills)

```
autoresearch-lessons.md accumulates across requests:

### L-1: Biotech Topics Need bioRxiv
- Strategy: DuckDuckGo only
- Outcome: low source quality
- Insight: Always include bioRxiv for biology topics
- Applied to: future biotech requests

### L-2: Narrow Queries Beat Broad
- Strategy: Single broad search query
- Outcome: generic results
- Insight: Decompose into 3-5 specific sub-queries
- Applied to: all future requests
```

### 6.4 Skill Evolution

Memento's self-evolving skill system means:
- **Round 1**: Generic `web-search` skill with DuckDuckGo
- **Round 3**: Skill refined to include arXiv + Semantic Scholar
- **Round 5**: Skill auto-creates `domain-specific-search` for recurring topics
- **Round 10**: Optimized skill library with proven strategies

Each successful refinement persists in the skill library for future requests.

---

## 7. Implementation Phases

### Phase A: Foundation (Week 1)

- [ ] Clone Memento-Skills + Codex-AutoResearch to Mac mini
- [ ] Create Python venv with shared dependencies
- [ ] Build custom Memento skills: `paper-search`, `fact-checker`, `gap-finder`, `synthesizer`, `critic`
- [ ] Write `orchestrator.py` with basic loop
- [ ] Wire Telegram reporting

### Phase B: Integration (Week 2)

- [ ] Implement `codex_phase.py` wrapping Codex's modify-verify-decide loop
- [ ] Implement `memento_phase.py` wrapping Memento's skill execution
- [ ] Build `evaluator.py` with 5-metric scoring
- [ ] Add to Leader dispatch routing table
- [ ] Add `__dispatch` to liaison-broker for `/deepresearch`

### Phase C: Optimization (Week 3)

- [ ] Tune memory allocation for 16GB constraint
- [ ] Implement workspace cleanup after each request
- [ ] Add lesson persistence across requests
- [ ] Build skill auto-refinement based on failure patterns
- [ ] Add convergence visualization to Opensens Office

### Phase D: Production (Week 4)

- [ ] LaunchAgent daemon for auto-start
- [ ] Health monitoring + restart on crash
- [ ] Rate limiting (max 3 concurrent research requests)
- [ ] Cost tracking via Paperclip (for API-backed models)
- [ ] DRVP events for research progress visualization

---

## 8. Configuration

```yaml
# ~/.darklab/memento-codex/config.yaml

orchestrator:
  max_iterations: 5
  threshold: 0.75           # Quality score to stop
  workspace_dir: ~/.darklab/memento-codex/workspaces
  cleanup_after_hours: 24   # Delete old workspaces

codex:
  inner_iterations: 10      # Modify-verify cycles per outer loop
  model: llama3.1:8b        # Via Ollama (free)
  api_base: http://localhost:11434/v1
  perspectives:             # Hypothesis generation lenses
    - optimist
    - skeptic
    - historian
    - minimalist

memento:
  db_path: ~/.darklab/memento/db/memento.sqlite
  skills_dir: ~/.darklab/memento/skills
  embedding_model: text-embedding-3-small  # Via LiteLLM
  embedding_base: http://localhost:4000/v1
  sandbox: uv              # Isolated Python execution
  max_skill_timeout: 120   # Seconds per skill execution

search:
  arxiv_max_results: 10
  semantic_scholar_max: 10
  duckduckgo_max: 5
  biorxiv_enabled: true     # Via MCP server

telegram:
  bot_token: ${TELEGRAM_BOT_TOKEN}
  chat_id: "1269510690"
  progress_updates: true    # Send per-iteration updates

resources:
  max_ram_gb: 4.0           # Pipeline budget (of 16GB total)
  parallel_workers: 1       # Sequential only on 16GB
  ollama_model: llama3.1:8b # 4GB VRAM
```

---

## 9. Summary

| Aspect | Details |
|--------|---------|
| **Input** | `/deepresearch <topic>` via Telegram |
| **Research Engine** | Codex-AutoResearch (modify-verify-decide loop) |
| **Refinement Engine** | Memento-Skills (self-evolving agent swarm) |
| **LLM** | Ollama llama3.1:8b ($0 cost) or Claude via LiteLLM |
| **Quality Scoring** | 5 metrics, 0.75 threshold, max 5 iterations |
| **Time per Request** | 15-50 minutes |
| **RAM Usage** | ~4GB pipeline + 4GB Ollama + 5.5GB system/Docker |
| **Output** | Structured report with citations → Telegram |
| **Learning** | Cross-run lessons + skill evolution |
| **Cost** | $0 with Ollama; ~$0.10-0.50 with Claude API |
