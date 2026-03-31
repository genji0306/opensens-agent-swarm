# DeerFlow + Autoresearch Integration Plan for OpenSens Agent Swarm

> **Target:** Mac mini M4 16GB cluster (Leader + Academic + Experiment nodes)
> **Date:** 2026-03-22
> **Status:** Planning

---

## Executive Summary

This plan integrates ByteDance's DeerFlow 2.0 (a LangGraph-based super agent harness with sub-agents, sandbox, memory, and skills) into the existing OAS pipeline. DeerFlow replaces the single-shot autoresearch loop with a multi-step, governed research orchestrator that can plan campaigns, spawn sub-agents, and produce rich artifacts (reports, slides, websites) — all flowing through Paperclip governance, DRVP visualization, and OpenViking memory.

The integration also connects DeerFlow to the existing AIClient-2-API boost tier so it can leverage free client-account models (Gemini 3 Pro, Claude Opus 4.5 via Kiro/Antigravity) for research-heavy tasks.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Boss (MacBook) — Telegram / SSH                                    │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ /deerflow "research objective"
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Leader Mac mini (:8100)                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │ dispatch.py   │→│ BudgetMiddle │→│ GovernanceMiddleware       │ │
│  │ /deerflow cmd │  │ (Paperclip)  │  │ (auto issue creation)     │ │
│  └──────┬───────┘  └──────────────┘  └───────────────────────────┘ │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────────────────────────┐                       │
│  │  DeerFlow Adapter (core/oas_core/)       │                       │
│  │  ┌────────────────────────────────────┐  │                       │
│  │  │ Option A: DeerFlowClient (embed)   │  │  ← config.yaml       │
│  │  │ Option B: HTTP Gateway (:8001)     │  │  ← extensions.json   │
│  │  └────────────┬───────────────────────┘  │                       │
│  │               │                          │                       │
│  │  ┌────────────▼───────────────────────┐  │                       │
│  │  │ LangGraph Agent Runtime (:2024)    │  │                       │
│  │  │ • Lead Agent (11 middleware)       │  │                       │
│  │  │ • Sub-agents (max 3 concurrent)    │  │                       │
│  │  │ • Skills (research, report, etc.)  │  │                       │
│  │  │ • Sandbox (local filesystem)       │  │                       │
│  │  └────────────┬───────────────────────┘  │                       │
│  └───────────────┼──────────────────────────┘                       │
│                  │                                                   │
│  ┌───────────────▼──────────────────────────┐                       │
│  │  Model Backend (tiered)                   │                       │
│  │  • PLANNING:  Claude Sonnet 4.6 (API)    │                       │
│  │  • EXECUTION: Ollama llama3.1:8b (local) │                       │
│  │  • BOOST:     AIClient-2-API (:9999)     │                       │
│  │    → Gemini 3 Pro (Antigravity)          │                       │
│  │    → Claude 4.5 Opus (Kiro)              │                       │
│  └──────────────────────────────────────────┘                       │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Redis    │  │ Paperclip│  │ OpenViking│  │ DRVP SSE          │  │
│  │ :6379    │  │ :3100    │  │ :8200    │  │ /drvp/events/{id} │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                            │
              ┌─────────────┼──────────────┐
              ▼                            ▼
┌──────────────────────┐    ┌──────────────────────┐
│ Academic Mac mini     │    │ Experiment Mac mini   │
│ (delegated research   │    │ (autoresearch, sim,   │
│  via OAS campaign)    │    │  analysis)            │
└──────────────────────┘    └──────────────────────┘
```

---

## Phase 1: Install DeerFlow Backend on Leader (Day 1-2)

### 1.1 System Prerequisites

The Leader Mac mini M4 16GB already has Python 3.12, Node.js 22, Docker, and uv. Verify:

```bash
ssh "cyber 02@192.168.23.25"
python3 --version     # 3.12+
node --version        # 22+
uv --version          # any
```

### 1.2 Install DeerFlow as a Python Package

DeerFlow's backend is structured as an installable package (`deerflow-harness`). Install it into the OAS virtual environment:

```bash
cd "/path/to/Opensens Agent Swarm"

# Add DeerFlow harness as a path dependency
# in pyproject.toml [project.optional-dependencies]
uv pip install -e "./frameworks/deer-flow-main/backend/packages/harness"
```

**Key dependencies DeerFlow brings** (from its `pyproject.toml`):
- `langgraph` (already in OAS core)
- `langchain-openai`, `langchain-anthropic`
- `langchain-mcp-adapters` (for MCP tool integration)
- `tavily-python` (web search)
- `jinja2` (prompt templates)

Conflicts to watch: DeerFlow requires Python 3.12+ and `langgraph>=0.3`. OAS already uses LangGraph — verify version compatibility in `pyproject.toml`.

### 1.3 Create DeerFlow Configuration

Create a dedicated config for DeerFlow running inside OAS:

```bash
mkdir -p ~/.darklab/deerflow
```

**~/.darklab/deerflow/config.yaml:**
```yaml
config_version: 2

models:
  # Planning tier — Anthropic direct
  - name: claude-sonnet
    display_name: Claude Sonnet 4.6
    use: langchain_openai:ChatOpenAI
    model: claude-sonnet-4-6-20260301
    api_key: $ANTHROPIC_API_KEY
    base_url: https://api.anthropic.com/v1
    max_tokens: 8192
    temperature: 0.3
    supports_thinking: true

  # Boost tier — via AIClient-2-API (free)
  - name: gemini-boost
    display_name: Gemini 3 Pro (Boost)
    use: langchain_openai:ChatOpenAI
    model: gemini-3-pro
    api_key: $AICLIENT_API_KEY
    base_url: http://localhost:9999/v1
    max_tokens: 8192
    temperature: 0.5

  # Execution tier — local Ollama
  - name: ollama-local
    display_name: Llama 3.1 8B (Local)
    use: langchain_openai:ChatOpenAI
    model: llama3.1:8b
    api_key: ollama
    base_url: http://localhost:11434/v1
    max_tokens: 4096
    temperature: 0.7

# Use local sandbox (no Docker-in-Docker overhead on M4)
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider

# Skills from DeerFlow + custom DarkLab skills
skills:
  path: ./frameworks/deer-flow-main/skills
  container_path: /mnt/skills

# Conservative memory to save RAM
memory:
  enabled: true
  injection_enabled: true
  storage_path: ~/.darklab/deerflow/memory.json
  debounce_seconds: 60
  max_facts: 50
  max_injection_tokens: 1500

# Sub-agents enabled for complex research
subagents:
  enabled: true

# Summarization enabled (critical for 16GB RAM / limited context)
summarization:
  enabled: true

# No IM channels — OAS handles this via PicoClaw
channels: {}
```

### 1.4 Memory Budget for M4 16GB

| Process | Est. RAM | Notes |
|---------|----------|-------|
| Ollama (llama3.1:8b) | ~5.5 GB | Already running |
| DeerFlow LangGraph runtime | ~0.5 GB | Python process |
| DeerFlow sub-agents (max 3) | ~0.3 GB | Thread pools, not processes |
| Redis | ~0.1 GB | Already running |
| Paperclip + PostgreSQL | ~0.5 GB | Already running |
| AIClient-2-API | ~0.3 GB | Node.js process |
| OS + other services | ~3 GB | macOS, Docker, etc. |
| **Headroom** | **~5.8 GB** | Sufficient for spikes |

**Critical setting:** Set `MAX_CONCURRENT_SUBAGENTS=2` (down from DeerFlow's default 3) to prevent memory pressure:

```bash
# ~/.darklab/.env
DEERFLOW_MAX_SUBAGENTS=2
```

---

## Phase 2: Create DeerFlow Adapter in OAS Core (Day 2-3)

### 2.1 New Module: `core/oas_core/adapters/deerflow.py`

This adapter wraps DeerFlow's embedded `DeerFlowClient` and bridges it to OAS's `Task`/`TaskResult` model, DRVP events, and middleware pipeline.

```python
"""DeerFlow adapter for OAS — wraps DeerFlowClient with governance hooks."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

logger = logging.getLogger("oas.adapters.deerflow")

# Import guard (DeerFlow may not be installed)
try:
    from deerflow.client import DeerFlowClient
    DEERFLOW_AVAILABLE = True
except ImportError:
    DEERFLOW_AVAILABLE = False

__all__ = ["DeerFlowAdapter", "DEERFLOW_AVAILABLE"]

CONFIG_PATH = Path.home() / ".darklab" / "deerflow" / "config.yaml"


class DeerFlowAdapter:
    """Bridges DeerFlow into OAS dispatch pipeline."""

    def __init__(
        self,
        config_path: Path | None = None,
        model_name: str | None = None,
    ):
        if not DEERFLOW_AVAILABLE:
            raise ImportError("deerflow-harness not installed")
        self._config_path = config_path or CONFIG_PATH
        self._model_name = model_name
        self._client: DeerFlowClient | None = None

    def _get_client(self) -> "DeerFlowClient":
        if self._client is None:
            self._client = DeerFlowClient(
                config_path=str(self._config_path),
                model_name=self._model_name,
                thinking_enabled=True,
                subagent_enabled=True,
                plan_mode=False,
            )
        return self._client

    async def run_research(
        self,
        request_id: str,
        query: str,
        *,
        agent_name: str = "deerflow",
        device: str = "leader",
        thread_id: str | None = None,
        files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a DeerFlow research task with DRVP event emission."""
        client = self._get_client()
        thread_id = thread_id or request_id

        # Upload files if provided
        if files:
            client.upload_files(thread_id, files)

        # Emit start event
        await emit(DRVPEvent(
            event_type=DRVPEventType.AGENT_ACTIVATED,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"query": query[:200], "thread_id": thread_id},
        ))

        # Stream response, collecting full output
        output_parts = []
        try:
            for event in client.stream(query, thread_id=thread_id):
                if event.type == "messages-tuple":
                    data = event.data
                    if data.get("type") == "ai" and data.get("content"):
                        output_parts.append(str(data["content"]))
                        # Emit thinking events periodically
                        await emit(DRVPEvent(
                            event_type=DRVPEventType.AGENT_THINKING,
                            request_id=request_id,
                            agent_name=agent_name,
                            device=device,
                            payload={"progress": len(output_parts)},
                        ))
        except Exception as exc:
            await emit(DRVPEvent(
                event_type=DRVPEventType.AGENT_ERROR,
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={"error": str(exc)},
            ))
            raise

        result_text = "\n".join(output_parts)

        await emit(DRVPEvent(
            event_type=DRVPEventType.AGENT_IDLE,
            request_id=request_id,
            agent_name=agent_name,
            device=device,
            payload={"output_length": len(result_text)},
        ))

        return {
            "output": result_text,
            "thread_id": thread_id,
            "artifacts": [],  # Populated from DeerFlow's artifact system
        }

    def list_models(self) -> dict:
        return self._get_client().list_models()

    def list_skills(self) -> dict:
        return self._get_client().list_skills()

    def reset(self) -> None:
        if self._client:
            self._client.reset_agent()
            self._client = None
```

### 2.2 New Agent Handler: `cluster/agents/experiment/deerflow_research.py`

```python
"""DeerFlow research handler — dispatched via /deerflow command."""

import logging
from shared.models import Task, TaskResult, TaskType
from shared.node_bridge import run_agent

logger = logging.getLogger("oas.agents.deerflow")

async def handle(task: Task) -> TaskResult:
    """Handle a DeerFlow research task."""
    from oas_core.adapters.deerflow import DeerFlowAdapter

    query = task.payload.get("query") or task.payload.get("args", "")
    model = task.payload.get("model")
    files = task.payload.get("files", [])

    adapter = DeerFlowAdapter(model_name=model)
    result = await adapter.run_research(
        request_id=task.task_id,
        query=query,
        agent_name="deerflow",
        device="leader",  # Runs on Leader (has DeerFlow installed)
        files=files,
    )

    return TaskResult(
        task_id=task.task_id,
        agent_name="DeerFlowResearch",
        status="ok",
        result=result,
        artifacts=result.get("artifacts", []),
    )

if __name__ == "__main__":
    run_agent(handle, agent_name="DeerFlowResearch")
```

### 2.3 Register in Dispatch

**Add to `cluster/agents/shared/models.py`:**
```python
class TaskType(str, Enum):
    # ... existing ...
    DEERFLOW = "deerflow"
```

**Add to `cluster/agents/leader/dispatch.py`:**
```python
ROUTING_TABLE["deerflow"] = Route("leader", "darklab-deerflow", TaskType.DEERFLOW)
```

**Add to `cluster/agents/leader/swarm_registry.py`:**
```python
from experiment.deerflow_research import handle as deerflow_handle

registry["deerflow"] = {
    "handler": deerflow_handle,
    "task_type": "deerflow",
    "device": "leader",
    "description": (
        "Deep research agent powered by DeerFlow. Spawns sub-agents for "
        "multi-step research, generates reports, slides, and web pages. "
        "Use for complex research that requires planning and multiple sources."
    ),
}
```

---

## Phase 3: Connect DeerFlow to AIClient Boost Tier (Day 3-4)

### 3.1 Model Routing Strategy

DeerFlow's `config.yaml` already points to AIClient-2-API at `http://localhost:9999/v1`. The OAS model router determines which tier to use. Wire DeerFlow to respect the OAS tier decision:

```python
# In deerflow adapter, select model based on OAS tier
from shared.llm_client import get_model_router, ModelTier

router = get_model_router()
decision = router.route(query, task_type="DEERFLOW")

model_map = {
    ModelTier.PLANNING: "claude-sonnet",     # Anthropic API
    ModelTier.EXECUTION: "ollama-local",      # Local Ollama
    ModelTier.BOOST: "gemini-boost",          # AIClient free tier
}
model_name = model_map.get(decision.tier, "ollama-local")
adapter = DeerFlowAdapter(model_name=model_name)
```

### 3.2 AIClient Configuration for DeerFlow

AIClient-2-API is already deployed at `:9999` on the Leader. Ensure these models are configured:

```json
// AIClient configs/config.json — add DeerFlow-compatible routes
{
  "DEFAULT_MODEL": "gemini-3-pro",
  "ENABLE_GEMINI": true,
  "ENABLE_ANTIGRAVITY": true,
  "ENABLE_KIRO": true
}
```

DeerFlow uses OpenAI-compatible protocol, which AIClient natively supports. No protocol conversion needed.

### 3.3 Cost Tracking

DeerFlow's internal token usage flows through the OAS `BudgetMiddleware` because the adapter runs inside the governed pipeline. Additionally, emit boost events:

```python
# After DeerFlow completes, report cost
if decision.tier == ModelTier.BOOST:
    await emit(DRVPEvent(
        event_type=DRVPEventType.LLM_CALL_BOOSTED,
        request_id=request_id,
        agent_name="deerflow",
        device="leader",
        payload={
            "model": decision.model,
            "provider": "aiclient",
            "input_tokens": estimated_input,
            "output_tokens": estimated_output,
            "cost_usd": 0.0,  # Free via client accounts
        },
    ))
```

---

## Phase 4: DeerFlow ↔ Autoresearch Bridge (Day 4-5)

### 4.1 Campaign-Based Integration

The most powerful integration: DeerFlow can plan a multi-step campaign that includes autoresearch as one step. The CampaignEngine already supports DAG execution:

```python
# DeerFlow plans a campaign like:
plan = [
    {"step": 1, "command": "literature", "args": "survey neural architecture search for edge devices", "depends_on": []},
    {"step": 2, "command": "doe", "args": "design experiments for NAS on M4", "depends_on": [1]},
    {"step": 3, "command": "autoresearch", "args": "run NAS experiments", "depends_on": [2]},
    {"step": 4, "command": "analyze", "args": "analyze autoresearch results", "depends_on": [3]},
    {"step": 5, "command": "deerflow", "args": "generate final report with findings", "depends_on": [4]},
]
```

This is already supported — the CampaignEngine resolves the DAG, runs steps in dependency order, and delegates each command to the appropriate agent via the routing table.

### 4.2 DeerFlow as Campaign Planner

Instead of Claude planning campaigns (current behavior), DeerFlow's lead agent can be the planner. It's better at decomposing research tasks because it has access to skills and memory:

```python
async def plan_via_deerflow(request: str) -> list[dict]:
    """Use DeerFlow to plan a research campaign."""
    adapter = DeerFlowAdapter(model_name="claude-sonnet")
    result = await adapter.run_research(
        request_id=f"plan-{uuid4().hex[:8]}",
        query=f"""Plan a research campaign for: {request}

Available commands: {list(ROUTING_TABLE.keys())}
Output a JSON array of steps with: step, command, args, depends_on.
Each step uses one command from the available list.""",
    )
    # Parse JSON from response
    return parse_campaign_plan(result["output"])
```

### 4.3 Autoresearch Enhancement

The existing `autoresearch.py` handler stays unchanged. DeerFlow orchestrates it as a campaign step. However, add DRVP events to autoresearch for visibility:

```python
# In cluster/agents/experiment/autoresearch.py, add:
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

# Inside run loop, emit per-iteration events:
await emit(DRVPEvent(
    event_type=DRVPEventType.AGENT_THINKING,
    request_id=task.task_id,
    agent_name="autoresearch",
    device="experiment",
    payload={
        "iteration": i,
        "max_iterations": max_iterations,
        "best_metric": best_so_far,
    },
))
```

---

## Phase 5: Custom DarkLab Skills for DeerFlow (Day 5-6)

### 5.1 Create DarkLab Skill Pack

DeerFlow loads skills from `SKILL.md` files. Create DarkLab-specific research skills:

```bash
mkdir -p frameworks/deer-flow-main/skills/custom/darklab-research
```

**`skills/custom/darklab-research/SKILL.md`:**
```markdown
---
name: darklab-research
description: Autonomous scientific research using the DarkLab cluster
license: MIT
version: 1.0.0
author: Opensens DarkLab
allowed-tools:
  - bash
  - read_file
  - write_file
  - web_search
  - web_fetch
---

# DarkLab Research Skill

You are conducting autonomous scientific research on the Opensens DarkLab
cluster. You have access to:

- Literature search via Perplexity and academic databases
- Design of experiments (DOE) planning
- Computational simulation via Python/NumPy/SciPy
- Data analysis with pandas and matplotlib
- Report generation with LaTeX or Markdown

## Workflow

1. **Literature Review** — Search for relevant prior work
2. **Hypothesis Formation** — Based on gaps in the literature
3. **Experiment Design** — Create a DOE plan
4. **Execution** — Run experiments (simulations or data analysis)
5. **Analysis** — Statistical analysis of results
6. **Report** — Generate a structured research report

## Output Format

All research outputs should be saved to the workspace as:
- `report.md` — Main research report
- `data/` — Raw data and analysis scripts
- `figures/` — Generated visualizations
```

### 5.2 MCP Server Integration

DeerFlow supports MCP servers. Register the existing OAS tools as MCP tools:

**`~/.darklab/deerflow/extensions_config.json`:**
```json
{
  "mcpServers": {
    "bioRxiv": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-biorxiv"],
      "description": "bioRxiv/medRxiv preprint search"
    }
  },
  "skills": {
    "research": {"enabled": true},
    "report-generation": {"enabled": true},
    "darklab-research": {"enabled": true},
    "slide-creation": {"enabled": false},
    "web-page": {"enabled": false},
    "image-generation": {"enabled": false}
  }
}
```

---

## Phase 6: DRVP Visualization for DeerFlow (Day 6-7)

### 6.1 Office Store Updates

Add DeerFlow agent to the Office visualization. In [office/src/store/office-store.ts](office/src/store/office-store.ts), add the DeerFlow agent definition:

```typescript
{
  id: "deerflow",
  name: "DeerFlow Orchestrator",
  role: "Research Orchestrator",
  status: "idle",
  position: { x: 7, y: 3 },  // Near experiment zone
  zone: "research-lab",
  avatar: "🦌",
}
```

### 6.2 DRVP Consumer Extension

In [office/src/drvp/drvp-consumer.ts](office/src/drvp/drvp-consumer.ts), handle DeerFlow-specific events:

```typescript
// DeerFlow emits standard DRVP events (agent.thinking, agent.activated, etc.)
// which are already handled. Add enhanced payload rendering:
case "agent.thinking":
  if (event.agent_name === "deerflow" && event.payload.progress) {
    // Show sub-agent progress in the EventTimeline
    updateAgentMetric(event.agent_name, "steps_completed", event.payload.progress);
  }
  break;
```

### 6.3 DeerFlow Thread Viewer

The Opensens Office chat dock can connect to DeerFlow threads for live streaming:

```typescript
// In ChatDockBar, add DeerFlow as a chat backend option
const DEERFLOW_BACKENDS = {
  deerflow: {
    label: "DeerFlow Research",
    stream: (query: string, threadId: string) =>
      fetch(`http://192.168.23.25:8001/api/threads/${threadId}/chat`, {
        method: "POST",
        body: JSON.stringify({ message: query }),
      }),
  },
};
```

---

## Phase 7: Docker Deployment (Day 7-8)

### 7.1 Add DeerFlow to Leader Docker Stack

Add to `docker-compose.services.yml`:

```yaml
services:
  deerflow-gateway:
    build:
      context: ./frameworks/deer-flow-main/backend
      dockerfile: Dockerfile
    command: ["python", "-m", "uvicorn", "app.gateway.app:app", "--host", "0.0.0.0", "--port", "8001"]
    ports:
      - "8001:8001"
    environment:
      DEER_FLOW_CONFIG_PATH: /app/config.yaml
      DEER_FLOW_EXTENSIONS_CONFIG_PATH: /app/extensions_config.json
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      TAVILY_API_KEY: ${TAVILY_API_KEY}
      AICLIENT_API_KEY: ${AICLIENT_API_KEY}
    volumes:
      - ~/.darklab/deerflow/config.yaml:/app/config.yaml:ro
      - ~/.darklab/deerflow/extensions_config.json:/app/extensions_config.json
      - ~/.darklab/deerflow/memory.json:/app/.deer-flow/memory.json
      - ./frameworks/deer-flow-main/skills:/app/skills:ro
    networks:
      - darklab
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G

  deerflow-langgraph:
    build:
      context: ./frameworks/deer-flow-main/backend
      dockerfile: Dockerfile
    command: ["langgraph", "dev", "--host", "0.0.0.0", "--port", "2024"]
    ports:
      - "2024:2024"
    environment:
      DEER_FLOW_CONFIG_PATH: /app/config.yaml
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    volumes:
      - ~/.darklab/deerflow/config.yaml:/app/config.yaml:ro
      - ./frameworks/deer-flow-main/skills:/app/skills:ro
    networks:
      - darklab
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
```

### 7.2 Alternative: Embedded Mode (Recommended for M4 16GB)

To save RAM, use the embedded `DeerFlowClient` directly in the OAS Python process instead of running separate Gateway + LangGraph services. This is what the adapter in Phase 2 already does.

**Embedded mode advantages:**
- No extra Docker containers (saves ~1.5 GB RAM)
- No HTTP overhead between OAS and DeerFlow
- Single process, simpler debugging
- Direct access to OAS middleware pipeline

**Embedded mode limitations:**
- No DeerFlow web UI (use Opensens Office instead)
- No separate scaling of DeerFlow workers

**Recommendation:** Start with embedded mode. Only deploy Docker services if you need the DeerFlow web UI or independent scaling.

---

## Phase 8: Testing (Day 8-9)

### 8.1 Unit Tests

```python
# core/tests/test_deerflow_adapter.py

import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_deerflow_client():
    with patch("oas_core.adapters.deerflow.DeerFlowClient") as mock:
        client = MagicMock()
        client.stream.return_value = iter([
            MagicMock(type="messages-tuple", data={"type": "ai", "content": "Result"}),
            MagicMock(type="end", data={}),
        ])
        client.list_models.return_value = {"models": [{"name": "test"}]}
        mock.return_value = client
        yield client

class TestDeerFlowAdapter:
    async def test_run_research(self, mock_deerflow_client):
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter()
        result = await adapter.run_research("req-1", "test query")
        assert result["output"] == "Result"
        assert result["thread_id"] == "req-1"

    async def test_model_selection(self, mock_deerflow_client):
        from oas_core.adapters.deerflow import DeerFlowAdapter
        adapter = DeerFlowAdapter(model_name="gemini-boost")
        # Verify model_name passed to DeerFlowClient
        ...

    async def test_import_guard(self):
        with patch.dict("sys.modules", {"deerflow": None, "deerflow.client": None}):
            from importlib import reload
            import oas_core.adapters.deerflow as mod
            reload(mod)
            assert not mod.DEERFLOW_AVAILABLE
```

### 8.2 Integration Test

```python
# core/tests/test_deerflow_campaign.py

async def test_deerflow_in_campaign():
    """DeerFlow step in a multi-step campaign."""
    plan = [
        {"step": 1, "command": "literature", "args": "quantum computing"},
        {"step": 2, "command": "deerflow", "args": "synthesize findings", "depends_on": [1]},
    ]
    # Mock handlers, run campaign engine
    ...
```

### 8.3 End-to-End Smoke Test

```bash
# Via PicoClaw / dispatch
curl -X POST http://192.168.23.25:8100/dispatch \
  -H "Content-Type: application/json" \
  -d '{"text": "/deerflow Research the latest advances in on-device LLM inference on Apple Silicon"}'
```

Expected flow:
1. `dispatch.py` → routes to `ROUTING_TABLE["deerflow"]`
2. `BudgetMiddleware` → pre-check passes
3. `GovernanceMiddleware` → creates Paperclip issue DL-XX
4. `deerflow_research.handle()` → DeerFlowClient streams response
5. DRVP events visible in Opensens Office
6. Result returned, issue marked done

---

## Phase 9: PicoClaw Command Registration (Day 9)

### 9.1 Add `/deerflow` Command

The `/deerflow` command is automatically available once registered in `ROUTING_TABLE`. PicoClaw routes any `/command args` through `dispatch.py → parse_command()`.

**Usage examples via Telegram:**
```
/deerflow Research the impact of quantization on LLM accuracy for edge deployment
/deerflow Analyze these papers and generate a comparison report [attach PDFs]
/deerflow Plan a study on federated learning for medical imaging
```

### 9.2 Boost-Aware Dispatch

Add DeerFlow to the boost-eligible task list:

```python
# In model_router.py
BOOST_ELIGIBLE_TASKS = {
    "RESEARCH", "LITERATURE", "PAPER", "DOE", "SYNTHESIZE",
    "AUTORESEARCH", "DEERFLOW",  # Add this
}
```

---

## Critical Considerations

### Memory Management (16GB M4)

| Constraint | Mitigation |
|------------|------------|
| Ollama uses ~5.5 GB | Consider `llama3.1:8b-q4` (4-bit) to save ~2 GB |
| DeerFlow sub-agents default to 3 concurrent | Set `MAX_CONCURRENT_SUBAGENTS=2` |
| Long research sessions grow context | Enable DeerFlow's `summarization` middleware |
| DeerFlow memory.json grows over time | Set `max_facts: 50` (not default 100) |
| Multiple Python processes | Use embedded mode (single process) |

### Network Architecture

```
Telegram → PicoClaw → dispatch.py (:8100)
                          │
                          ├── DeerFlow (embedded, same process)
                          │     └── AIClient-2-API (:9999) for boost
                          │     └── Anthropic API (direct) for planning
                          │     └── Ollama (:11434) for execution
                          │
                          ├── Academic (:SSH) for literature/research
                          └── Experiment (:SSH) for simulation/analysis
```

### Security

- DeerFlow's sandbox runs in `local` mode (filesystem isolation only, no Docker container). This is acceptable for trusted research tasks.
- AIClient tokens are stored in `~/.darklab/.env` — already secured by OAS conventions.
- DeerFlow's MCP servers inherit the host's network access. The browser domain allowlist from OAS does NOT automatically apply to DeerFlow's web_fetch tool. Add Tavily/Jina API keys to restrict search scope.

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| AIClient-2-API down | Boost tier unavailable | Falls back to EXECUTION (Ollama) |
| Ollama OOM | Local model crashes | Restart Ollama; queue retries |
| DeerFlow hangs | Thread blocked | 15-min timeout on sub-agents; adapter timeout |
| Anthropic API rate limit | Planning tier throttled | Exponential backoff; fall to boost |
| OpenViking unreachable | No memory injection | Graceful degradation (empty context) |

### Scaling Path

When cluster grows beyond M4 16GB:
1. **Academic M4 Pro (36GB):** Move DeerFlow's LangGraph runtime there, run as HTTP service
2. **Experiment M4 (16GB):** Dedicated to autoresearch + simulation
3. **Leader:** Pure routing + governance, no LLM execution
4. **GPU node (future):** Run larger Ollama models (70B+)

---

## Implementation Checklist

| # | Task | Phase | Priority | Est. Hours |
|---|------|-------|----------|------------|
| 1 | Install `deerflow-harness` in OAS venv | 1 | Critical | 2 |
| 2 | Create `~/.darklab/deerflow/config.yaml` | 1 | Critical | 1 |
| 3 | Write `core/oas_core/adapters/deerflow.py` | 2 | Critical | 3 |
| 4 | Write `cluster/agents/experiment/deerflow_research.py` | 2 | Critical | 2 |
| 5 | Register `TaskType.DEERFLOW` + route + swarm entry | 2 | Critical | 1 |
| 6 | Configure AIClient models in DeerFlow config | 3 | High | 1 |
| 7 | Add DRVP cost events for boost usage | 3 | High | 1 |
| 8 | Create DarkLab custom skill (`SKILL.md`) | 5 | Medium | 2 |
| 9 | Configure MCP servers (bioRxiv, etc.) | 5 | Medium | 1 |
| 10 | Add DeerFlow agent to Office visualization | 6 | Medium | 2 |
| 11 | Write unit tests (adapter, handler) | 8 | High | 3 |
| 12 | E2E smoke test via PicoClaw | 8 | High | 2 |
| 13 | Add `DEERFLOW` to `BOOST_ELIGIBLE_TASKS` | 9 | Medium | 0.5 |
| 14 | (Optional) Docker deployment | 7 | Low | 3 |
| | **Total** | | | **~24 hrs** |

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Edit | Add `deerflow-harness` path dependency |
| `core/oas_core/adapters/deerflow.py` | Create | DeerFlowClient wrapper with DRVP events |
| `cluster/agents/experiment/deerflow_research.py` | Create | Task handler for `/deerflow` command |
| `cluster/agents/shared/models.py` | Edit | Add `DEERFLOW` to `TaskType` enum |
| `cluster/agents/leader/dispatch.py` | Edit | Add route to `ROUTING_TABLE` |
| `cluster/agents/leader/swarm_registry.py` | Edit | Register `deerflow` handler |
| `core/oas_core/model_router.py` | Edit | Add `DEERFLOW` to `BOOST_ELIGIBLE_TASKS` |
| `~/.darklab/deerflow/config.yaml` | Create | DeerFlow model + sandbox + memory config |
| `~/.darklab/deerflow/extensions_config.json` | Create | MCP servers + skill toggles |
| `frameworks/deer-flow-main/skills/custom/darklab-research/SKILL.md` | Create | DarkLab research skill |
| `core/tests/test_deerflow_adapter.py` | Create | Unit tests |
| `core/tests/test_deerflow_campaign.py` | Create | Integration tests |
| `docker-compose.services.yml` | Edit (optional) | DeerFlow Gateway + LangGraph services |
