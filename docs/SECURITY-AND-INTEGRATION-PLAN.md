# Security, Browser Tool, and PicoClaw–Paperclip Integration Plan

**Date:** 2026-03-19
**Status:** Strategic Analysis & Recommendations
**Audience:** DarkLab Technical Stakeholders

---

## Part 1: OneCLI-Informed Security Improvements for OAS

### 1.1 Current Security Gaps vs OneCLI Patterns

OneCLI implements several security patterns that are absent or partially implemented in the OAS swarm. Below is a gap analysis with prioritized recommendations.

| Security Pattern | OneCLI Implementation | OAS Current State | Priority |
|---|---|---|---|
| **Secret encryption at rest** | AES-256-GCM per secret (iv:tag:ciphertext) | Plaintext in `.env` files and JSON configs | **CRITICAL** |
| **Agent credential rotation** | `aoc_` tokens with one-click regeneration | Static API keys in env vars, no rotation | **HIGH** |
| **Graduated secret permissions** | "all" vs "selective" mode per agent | Every agent sees all env vars | **HIGH** |
| **Proxy-based secret injection** | Rust gateway injects headers at network layer | Secrets embedded in agent process env | **MEDIUM** |
| **Dual authentication** | API keys (service) + JWT sessions (UI) | Paperclip has this; DarkLab agents use none | **HIGH** |
| **Input validation schemas** | Zod on every API boundary | Partial — dispatch validates commands but not payloads | **MEDIUM** |
| **Ownership scoping** | All DB queries include `userId` WHERE clause | Paperclip does this; cluster agents trust env vars | **MEDIUM** |
| **Policy resolution caching** | 60s TTL on agent+host decisions | No caching — budget checks hit Paperclip every call | **LOW** |

### 1.2 Recommended Implementations

#### R1. Encrypted Secrets Store (CRITICAL)

**Problem:** DarkLab agents read API keys from `~/.darklab/.env` as plaintext. If a node is compromised, all keys are exposed.

**Solution — Adopt OneCLI's pattern via Paperclip:**

```
┌─────────────────────────────────────────────┐
│ Paperclip Server (companySecrets table)      │
│                                             │
│   AES-256-GCM encrypted secret versions     │
│   Decrypted only during agent execution     │
│   PAPERCLIP_SECRETS_STRICT_MODE=true        │
└─────────┬───────────────────────────────────┘
          │ /api/agents/{id}/secrets/resolve
          ▼
┌─────────────────────────────────────────────┐
│ Agent Runtime (heartbeat.ts)                │
│                                             │
│   resolveAdapterConfigForRuntime()          │
│   injects decrypted values into process env │
│   values never logged or persisted          │
└─────────────────────────────────────────────┘
```

Paperclip **already has** the `companySecrets` + `companySecretVersions` tables with the `local_encrypted` provider. The gap is that DarkLab agents bypass this by reading `.env` directly.

**Action items:**
1. Store `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_AI_API_KEY`, `PERPLEXITY_API_KEY` as Paperclip company secrets
2. Modify `shared/config.py` to fetch secrets from Paperclip at startup via `GET /api/companies/{id}/secrets/resolve`
3. Enable `PAPERCLIP_SECRETS_STRICT_MODE=true` on Leader
4. Remove plaintext keys from `~/.darklab/.env` (keep only non-sensitive config)

#### R2. Agent Credential Tokens (HIGH)

**Problem:** DarkLab agents authenticate to each other via static env vars. There is no concept of per-agent credentials that can be rotated.

**Solution — Adopt OneCLI's `aoc_` token pattern via Paperclip's `agentApiKeys`:**

Paperclip already has `agentApiKeys` with SHA256 hashing, `lastUsedAt` tracking, and revocation. Currently only the Paperclip adapters use this.

**Action items:**
1. Generate a `pcp_` API key for each DarkLab agent (Leader, Academic, Experiment) in Paperclip
2. Modify `shared/config.py` to load `PAPERCLIP_AGENT_KEY` (replacing `PAPERCLIP_AGENT_ID`)
3. Leader dispatch validates incoming requests against Paperclip agent keys
4. Academic/Experiment nodes authenticate via `Authorization: Bearer pcp_...` when calling back to Leader

#### R3. Selective Secret Binding (HIGH)

**Problem:** All agents on a node can see all API keys. The Academic agent doesn't need `OPENAI_API_KEY`; the Experiment agent doesn't need `PERPLEXITY_API_KEY`.

**Solution — OneCLI's "selective" secret mode:**

Map DarkLab agents to their required secrets:

| Agent | Required Secrets |
|---|---|
| Leader | `ANTHROPIC_API_KEY`, `AICLIENT_API_KEY` |
| Academic | `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `GOOGLE_AI_API_KEY` |
| Experiment | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` |

Bind via Paperclip's `agentConfig.env` with `secret_ref` type. Each agent receives only the secrets it needs at runtime.

#### R4. Browser SecurityWatchdog Domain Allowlist (MEDIUM)

**Problem:** The browser-use framework has `SecurityWatchdog` with domain filtering and IP blocking, but `browser_agent.py` does not configure these constraints.

**Current code in `browser_agent.py`:**
```python
browser = BrowserSession(
    BrowserConfig(
        headless=True,
        user_data_dir=str(profile_dir),
    )
)
```

No `allowed_domains`, no `block_ip_addresses`. The LLM-controlled browser agent could theoretically navigate to any URL.

**Solution — Enable browser-use security features:**

```python
from browser_use.browser.session import SecurityConfig

browser = BrowserSession(
    BrowserConfig(
        headless=True,
        user_data_dir=str(profile_dir),
        security=SecurityConfig(
            allowed_domains=[
                "*.perplexity.ai",
                "scholar.google.com",
                "*.arxiv.org",
                "*.doi.org",
                "*.ncbi.nlm.nih.gov",
                "*.semanticscholar.org",
            ],
            block_ip_addresses=True,
        ),
    )
)
```

**Action items:**
1. Define per-skill domain allowlists in `cluster/configs/browser-domains.yaml`
2. Pass allowlist to `BrowserConfig.security` in each browser agent function
3. Enable `block_ip_addresses=True` to prevent SSRF to internal network (192.168.23.x)

---

## Part 2: Browser Tool Revision for PicoClaw and Paperclip Agents

### 2.1 Current Browser Architecture

```
Telegram /perplexity "quantum computing"
    ↓
PicoClaw → dispatch.py → Academic node
    ↓
browser_agent.py:browse_perplexity()
    ↓
browser-use Agent + Claude Sonnet 4.6
    ↓
headless Chrome → perplexity.ai
    ↓
Custom Controller: save_citation(title, url, authors, year)
    ↓
Citations → ~/.darklab/artifacts/citations.jsonl
    ↓
TaskResult → dispatch.py → PicoClaw → Telegram
```

### 2.2 Identified Issues

| Issue | Severity | Description |
|---|---|---|
| **No domain restrictions** | HIGH | Browser agent can navigate anywhere the LLM directs |
| **No SSRF protection** | HIGH | No `block_ip_addresses` — agent could access internal services |
| **No session isolation** | MEDIUM | All browser sessions share `~/.darklab/browser-profiles/` — cookies, history leak between tasks |
| **No cost tracking** | MEDIUM | Browser-use's Claude calls bypass the DarkLab budget system |
| **No DRVP events** | LOW | Browser actions don't emit DRVP events — invisible in Office UI |
| **Hardcoded LLM model** | LOW | `claude-sonnet-4-6-20260301` hardcoded, doesn't respect model router |

### 2.3 Recommended Revisions

#### B1. Add SecurityWatchdog Configuration

Create a skill-specific domain allowlist configuration:

```yaml
# cluster/configs/browser-domains.yaml
perplexity:
  allowed_domains:
    - "*.perplexity.ai"
  block_ip_addresses: true

scholar:
  allowed_domains:
    - "scholar.google.com"
    - "*.google.com"
  block_ip_addresses: true

general_research:
  allowed_domains:
    - "*.arxiv.org"
    - "*.doi.org"
    - "*.ncbi.nlm.nih.gov"
    - "*.semanticscholar.org"
    - "*.nature.com"
    - "*.sciencedirect.com"
    - "*.springer.com"
    - "*.wiley.com"
    - "*.plos.org"
    - "*.biorxiv.org"
    - "*.medrxiv.org"
  block_ip_addresses: true
```

#### B2. Browser Session Isolation

Create per-task browser profiles to prevent cross-contamination:

```python
# Instead of shared profile:
profile_dir = settings.darklab_home / "browser-profiles" / "perplexity-research"

# Use per-task isolated profile:
profile_dir = settings.darklab_home / "browser-profiles" / f"task-{task.task_id}"

# Cleanup after task completes:
try:
    result = await agent.run()
finally:
    await browser.close()
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
```

#### B3. Route Browser LLM Calls Through Budget System

Currently browser-use creates its own Anthropic client, bypassing DarkLab's `llm_client.py`:

```python
# Current (bypasses budget):
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model_name="claude-sonnet-4-6-20260301")

# Recommended (budget-aware via model router):
from shared.llm_client import call_routed
# Pass call_routed as the LLM backend to browser-use
```

Since browser-use expects a LangChain-compatible LLM, wrap `call_routed` in a LangChain adapter or use the LiteLLM proxy URL which already has budget tracking.

#### B4. Emit DRVP Events for Browser Actions

Add DRVP events so browser activity is visible in Office:

```python
from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

await emit(DRVPEvent(
    event_type=DRVPEventType.TOOL_CALL_STARTED,
    request_id=task.task_id,
    agent_name="AcademicBrowser",
    device="academic",
    payload={"tool_name": "browse_perplexity", "query": query},
))
```

---

## Part 3: PicoClaw–Paperclip Integration Strategy

### 3.1 Current State: How Each Agent Operates

#### PicoClaw (Telegram Gateway)

```
┌──────────────────────────────────────────┐
│ PicoClaw (OpenClaw Telegram Extension)   │
│                                          │
│  Input:  Telegram DM/group messages      │
│  Auth:   Pairing codes + user allowlist  │
│  Logic:  Message → parse → forward to    │
│          Leader dispatch.py via HTTP POST │
│  Output: TaskResult text → Telegram reply│
│                                          │
│  No persistent state                     │
│  No awareness of Paperclip governance    │
│  No cost visibility                      │
│  No approval flow for campaigns          │
└──────────────────────────────────────────┘
```

#### Paperclip (Governance Platform)

```
┌──────────────────────────────────────────┐
│ Paperclip AI (Express + React + Drizzle) │
│                                          │
│  Input:  REST API + WebSocket events     │
│  Auth:   Better-auth (OAuth) + Agent JWT │
│  Logic:  Agent scheduling, issue CRUD,   │
│          approval workflows, cost events │
│  Output: Dashboard, real-time events,    │
│          activity log                    │
│                                          │
│  37 PostgreSQL tables                    │
│  DRVP bridge from Redis                  │
│  Agent adapter system (9 adapters)       │
│  No connection to Telegram               │
│  No awareness of PicoClaw commands       │
└──────────────────────────────────────────┘
```

### 3.2 Integration Gap

PicoClaw and Paperclip currently operate as **parallel, disconnected systems** that both touch the same agents but through different interfaces:

```
                    ┌─ PicoClaw (Telegram)
User → Telegram ───┤
                    └→ dispatch.py → agents → results → Telegram
                       (fire-and-forget, no governance)

Admin → Browser ──→ Paperclip UI ──→ issues, approvals, costs
                    (governance, no command interface)
```

The DRVP bridge partially connects them (dispatch emits events → Redis → Paperclip), but the connection is **one-directional** (DarkLab → Paperclip). Paperclip decisions (approvals, budget pauses) don't flow back to PicoClaw.

### 3.3 Integration Architecture: Bidirectional Link

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTEGRATED ARCHITECTURE                       │
│                                                                 │
│  ┌─────────┐         ┌──────────┐         ┌─────────────┐     │
│  │PicoClaw │ ──HTTP──→│ Leader   │ ──DRVP──→│ Paperclip   │     │
│  │Telegram │         │dispatch  │ ←─REST──│ Server      │     │
│  │         │ ←─Notif─┤          │         │             │     │
│  └─────────┘         └──────────┘         └─────────────┘     │
│       │                   │                       │             │
│       │              ┌────┴────┐                  │             │
│       │              │Academic │                  │             │
│       │              │Experiment│                  │             │
│       │              └─────────┘                  │             │
│       │                                           │             │
│       └───────── Paperclip Webhook Notifications ─┘             │
│                  (approval results, budget alerts,              │
│                   issue status changes)                         │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 Implementation: Four Integration Hooks

#### Hook 1: PicoClaw → Paperclip Issue Creation (pre-dispatch)

Before forwarding to dispatch, PicoClaw creates a Paperclip issue so every Telegram request is tracked:

```python
# In PicoClaw message handler (pseudocode):
async def handle_telegram_message(message, user_id):
    # 1. Create Paperclip issue
    issue = await paperclip.post(f"/api/companies/{company_id}/issues", json={
        "title": f"Telegram: {message[:80]}",
        "status": "in_progress",
        "assigneeAgentId": leader_agent_id,
        "metadata": {
            "source": "telegram",
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
        },
    })

    # 2. Forward to dispatch with issue context
    result = await dispatch(text=message, issue_id=issue["id"])

    # 3. Update issue with result
    await paperclip.patch(f"/api/companies/{company_id}/issues/{issue['id']}", json={
        "status": "done" if result.status == "ok" else "blocked",
    })
```

**Benefit:** Every Telegram command creates a traceable governance record. The dashboard shows all requests, not just those that happen to emit DRVP events.

#### Hook 2: Paperclip → PicoClaw Notifications (approval results)

When a campaign approval is approved/rejected in Paperclip UI, notify the requesting user via Telegram:

```typescript
// In paperclip/server/src/services/approvals.ts — after approve/reject:

async function notifyPicoClaw(approval: Approval, decision: "approved" | "rejected") {
  const issue = await findIssue(approval.issueId);
  const telegramMeta = issue?.metadata?.source === "telegram"
    ? issue.metadata
    : null;

  if (!telegramMeta) return; // Not a Telegram-originated request

  const message = decision === "approved"
    ? `✅ Campaign "${approval.title}" approved. Executing ${approval.stepCount} steps.`
    : `❌ Campaign "${approval.title}" rejected. Reason: ${approval.decisionNote}`;

  // POST to PicoClaw notification webhook
  await fetch(`${PICOCLAW_WEBHOOK_URL}/notify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: telegramMeta.telegram_chat_id,
      text: message,
    }),
  });
}
```

**PicoClaw webhook endpoint** (add to PicoClaw):

```typescript
// GET/POST /notify — receives Paperclip notifications
app.post("/notify", async (req, res) => {
  const { chat_id, text } = req.body;
  await bot.api.sendMessage(chat_id, text, { parse_mode: "Markdown" });
  res.json({ ok: true });
});
```

**Benefit:** Users don't need to check the dashboard — approval decisions arrive directly in Telegram.

#### Hook 3: PicoClaw Budget Status Command

Add `/budget` command to PicoClaw that queries Paperclip in real time:

```
User: /budget

PicoClaw: 💰 DarkLab Budget Status
  Leader:     $12.50 / $50.00 (25%)
  Academic:   $8.30 / $30.00 (28%)
  Experiment: $3.10 / $20.00 (16%)
  Boost:      12/100 calls today

  Monthly: $287 / $3,000 (10%)
```

Implementation:

```python
async def handle_budget_command(chat_id):
    dashboard = await paperclip.get(
        f"/api/companies/{company_id}/dashboard"
    )
    agents = dashboard["agents"]
    lines = ["💰 *DarkLab Budget Status*\n"]
    for agent in agents:
        if agent["monthlyBudgetCents"] > 0:
            spent = agent["spentThisMonthCents"] / 100
            budget = agent["monthlyBudgetCents"] / 100
            pct = (spent / budget * 100) if budget > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            lines.append(f"  {agent['name']}: ${spent:.2f} / ${budget:.2f} [{bar}]")

    await bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
```

#### Hook 4: Paperclip Agent Adapter for PicoClaw

Register PicoClaw as a Paperclip agent adapter so Paperclip can assign tasks to it and track its execution:

```typescript
// packages/adapters/picoclaw/src/index.ts
import type { ServerAdapterModule } from "@paperclipai/adapter-utils";

export const picoClawAdapter: ServerAdapterModule = {
  type: "picoclaw-telegram",
  supportsLocalAgentJwt: false,

  async execute(context) {
    const { issue, agent, env } = context;

    // Forward task to DarkLab dispatch via HTTP
    const response = await fetch(`${env.LEADER_URL}/dispatch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: issue.title,
        issue_id: issue.id,
        agent_name: agent.name,
      }),
    });

    const result = await response.json();

    return {
      status: result.status === "ok" ? "succeeded" : "failed",
      output: result.result?.summary || JSON.stringify(result),
      tokensUsed: { input: 0, output: 0, cached: 0 },
      costCents: 0, // Costs tracked by DarkLab middleware
    };
  },

  async testEnvironment(context) {
    try {
      const health = await fetch(`${context.env.LEADER_URL}/health`);
      return { available: health.ok, message: "Leader dispatch reachable" };
    } catch {
      return { available: false, message: "Leader dispatch unreachable" };
    }
  },

  agentConfigurationDoc: `
## PicoClaw Telegram Adapter

Routes Paperclip issues to DarkLab Leader dispatch for execution.

### Environment Variables
- \`LEADER_URL\`: DarkLab Leader HTTP endpoint (e.g., \`http://192.168.23.25:8100\`)
  `,
};
```

**Benefit:** Paperclip can schedule DarkLab tasks directly (not just receive events). The heartbeat system can wake agents, and issues assigned to the "DarkLab Leader" agent are forwarded to dispatch.

### 3.5 Data Flow After Integration

```
TELEGRAM REQUEST FLOW:
User → /research quantum computing
    ↓
PicoClaw
    ├→ Paperclip: POST /issues (title, telegram metadata)  [HOOK 1]
    └→ Leader dispatch.py (text, issue_id)
         ├→ DRVP: request.created (→ Redis → Paperclip bridge)
         ├→ Budget middleware: check + report
         ├→ Academic: execute research
         ├→ DRVP: llm.call.completed (costs)
         └→ TaskResult
              ├→ PicoClaw: reply to Telegram
              └→ Paperclip: PATCH /issues → done

CAMPAIGN APPROVAL FLOW:
User → Investigate graphene synthesis methods
    ↓
PicoClaw → Paperclip issue → dispatch.py
    ↓
plan_campaign() → 3 steps (literature → research → synthesize)
    ↓
Governance: campaign.approval.required → DRVP → Paperclip
    ↓
Paperclip: create approval, DRVP issue linker
    ↓
Boss opens Paperclip dashboard → approves          [HOOK 2]
    ↓
Paperclip: POST /notify → PicoClaw webhook
    ↓
PicoClaw: "✅ Campaign approved. Executing 3 steps."
    ↓
CampaignEngine executes → DRVP events → Office + Paperclip
    ↓
Final result → PicoClaw → Telegram
```

### 3.6 Implementation Priority

| Hook | Effort | Impact | Priority |
|---|---|---|---|
| Hook 1: Issue creation pre-dispatch | 0.5 day | Full governance traceability for Telegram | **P1** |
| Hook 2: Approval notifications | 0.5 day | Closes the feedback loop for campaigns | **P1** |
| Hook 3: `/budget` command | 0.25 day | User visibility into spend | **P2** |
| Hook 4: Paperclip adapter | 1 day | Bidirectional task assignment | **P3** |

---

## Part 4: Summary of Recommendations

### Security (from OneCLI analysis)

| # | Recommendation | Impact | Effort |
|---|---|---|---|
| R1 | Encrypt secrets via Paperclip `companySecrets` | Eliminates plaintext key exposure | 2 days |
| R2 | Agent credential tokens (`pcp_` keys) for inter-node auth | Rotatable, auditable agent identity | 1 day |
| R3 | Selective secret binding per agent role | Least-privilege secret access | 0.5 day |
| R4 | Browser SecurityWatchdog domain allowlists | Prevents SSRF and unrestricted browsing | 0.5 day |

### Browser Tool

| # | Recommendation | Impact | Effort |
|---|---|---|---|
| B1 | Domain allowlists per browser skill | Prevents LLM-directed browsing to arbitrary sites | 0.5 day |
| B2 | Per-task browser profile isolation | Prevents cookie/history leakage between tasks | 0.25 day |
| B3 | Route browser LLM calls through budget system | Accurate cost tracking for browser automation | 1 day |
| B4 | DRVP events for browser actions | Browser activity visible in Office UI | 0.5 day |

### PicoClaw–Paperclip Integration

| # | Recommendation | Impact | Effort |
|---|---|---|---|
| H1 | Pre-dispatch issue creation in PicoClaw | Every Telegram request is a governed issue | 0.5 day |
| H2 | Paperclip → PicoClaw approval notifications | Users get campaign decisions in Telegram | 0.5 day |
| H3 | `/budget` Telegram command | Real-time spend visibility from Telegram | 0.25 day |
| H4 | Paperclip picoclaw-telegram adapter | Bidirectional task routing | 1 day |

**Total estimated effort: ~8.5 developer-days**

### Recommended Sequencing

**Week 1:** R4 (browser domains) + B1-B2 (browser hardening) + H1-H2 (PicoClaw–Paperclip hooks)
**Week 2:** R1 (encrypted secrets) + R2 (agent credentials) + H3 (budget command)
**Week 3:** R3 (selective binding) + B3-B4 (browser cost/DRVP) + H4 (Paperclip adapter)

This sequencing addresses the highest-severity security gaps first (browser SSRF, plaintext secrets), then builds the integration hooks that deliver the most user-facing value (Telegram governance traceability, approval notifications).
