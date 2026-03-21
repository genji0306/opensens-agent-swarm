# AIClient-2-API Integration Plan for DarkLab Agents

**Status:** Strategic Proposal — Draft
**Date:** 2026-03-19
**Author:** DarkLab R&D
**Classification:** Internal — Technical Stakeholders

---

## 1. Executive Summary

AIClient-2-API is an open-source proxy that converts **client-only AI accounts** (Gemini CLI OAuth, Kiro free tier, Codex OAuth, Grok SSO) into standard **OpenAI-compatible endpoints**. It achieves this by simulating the client application's OAuth flow, managing token lifecycle, and translating between protocols (OpenAI ↔ Claude ↔ Gemini) in real time.

This document proposes integrating AIClient-2-API as an **optional, temporary fallback provider** within the DarkLab cluster. The goal is to give PicoClaw and Paperclip agents access to high-quality models (Claude Opus 4.5 via Kiro, Gemini 3 Pro via OAuth) at **zero marginal cost** when the primary API budget is exhausted or when tasks are non-critical. This is explicitly designed as a **non-permanent, best-effort supplement** — not a replacement for direct API access.

---

## 2. How AIClient-2-API Works

### 2.1 Core Mechanism

AIClient-2-API does **not** use API keys. Instead, it:

1. **Acquires OAuth tokens** from provider-specific login flows (Google OAuth for Gemini, AWS Builder ID for Kiro, PKCE for Codex, SSO cookies for Grok).
2. **Simulates client headers** (User-Agent, X-Goog-Api-Client, TLS fingerprints) to appear as the official CLI or desktop application.
3. **Manages an account pool** with health checks, priority tiers, round-robin scheduling, and automatic failover across provider types.
4. **Converts protocols** bidirectionally — any incoming request format (OpenAI, Claude, Gemini) is translated to the target provider's native API on the fly.
5. **Serves a unified endpoint** at `http://localhost:3000/v1/chat/completions` that any OpenAI-compatible client can call.

### 2.2 Key Provider Capabilities

| Provider Route | Source | Models Available | Cost | Token Refresh |
|---|---|---|---|---|
| `gemini-cli-oauth` | Google OAuth | Gemini 2.5 Flash, Gemini 3 Pro | Free (quota-limited) | Auto, 5 min before expiry |
| `claude-kiro-oauth` | Kiro client token | Claude Sonnet 4.5, Claude Opus 4.5 | Free (credit-limited) | Auto refresh |
| `codex-oauth` | OpenAI PKCE | Codex models | Free tier | Auto refresh |
| `grok-custom` | SSO cookie + TLS sidecar | Grok 3, Grok 4 | Free (rate-limited) | Manual cookie rotation |
| `qwen-oauth` | Alibaba OAuth | Qwen3 Coder Plus | Free | Auto refresh |

### 2.3 What Makes This Different from API Access

| Aspect | Direct API (current) | AIClient-2-API |
|---|---|---|
| Authentication | API key (billed per token) | OAuth token (client quota) |
| Cost model | Per-token billing | Free within client quotas |
| Rate limits | High (paid tier) | Lower (client tier, varies) |
| Reliability | 99.9%+ SLA | Best-effort, quota may exhaust |
| Provider TOS | Fully compliant | Grey area — simulates client |
| Token management | None needed | OAuth lifecycle + pool rotation |

---

## 3. Integration Architecture

### 3.1 Deployment Topology

```
┌─────────────────────────────────────────────────────────────┐
│ Leader Mac mini (192.168.23.25)                             │
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐  │
│  │ LiteLLM  │    │AIClient  │    │  DarkLab Leader      │  │
│  │ :4000    │    │ :3000    │    │  :8100               │  │
│  │          │    │          │    │                       │  │
│  │ Anthropic│    │ Gemini   │    │  dispatch.py          │  │
│  │ (paid)   │    │ Kiro     │    │   ↓                  │  │
│  │          │    │ Codex    │    │  llm_client.py        │  │
│  │ Ollama   │    │ Grok     │    │   ├─ call_routed()   │  │
│  │ (local)  │    │ Qwen     │    │   │  ├─ Tier 1 → L  │  │
│  └──────────┘    └──────────┘    │   │  └─ Tier 2 → L  │  │
│       ↑               ↑          │   └─ Tier 3 → A ←NEW│  │
│       │               │          └──────────────────────┘  │
│       └───────────────┘                                     │
│         OpenAI-compatible                                   │
└─────────────────────────────────────────────────────────────┘

L = LiteLLM (primary)
A = AIClient-2-API (fallback)
```

### 3.2 Tiered Routing with AIClient Fallback

The existing two-tier router (`model_router.py`) gains a third tier:

| Tier | Purpose | Provider | Cost | When Used |
|---|---|---|---|---|
| **1 — PLANNING** | Campaign planning, architecture | Claude Sonnet via LiteLLM (Anthropic API) | $0.003/$0.015 per 1K tok | Planning prompts detected |
| **2 — EXECUTION** | Research, synthesis, analysis | Ollama llama3.1:8b via LiteLLM | Free (local) | Default for all other work |
| **3 — BOOST** (new) | High-quality execution fallback | Claude/Gemini via AIClient-2-API | Free (client quota) | Explicitly requested or Tier 1 budget exhausted |

**Routing logic:**

```python
def select_tier(task_type, budget_remaining, boost_enabled):
    if is_planning_prompt(task_type):
        if budget_remaining > 0:
            return Tier.PLANNING          # Anthropic API
        elif boost_enabled:
            return Tier.BOOST             # AIClient (Kiro Claude)
        else:
            return Tier.EXECUTION         # Ollama fallback

    if boost_enabled and task_type in BOOST_ELIGIBLE:
        return Tier.BOOST                 # AIClient for quality tasks

    return Tier.EXECUTION                 # Default: Ollama
```

### 3.3 Boost-Eligible Task Types

Not all tasks warrant consuming client quotas. The following task types would be eligible for Tier 3 boost when available:

| Task Type | Boost Rationale |
|---|---|
| `RESEARCH` | Quality of synthesis matters, Ollama often insufficient |
| `LITERATURE` | Academic precision requires stronger reasoning |
| `PAPER` | Writing quality directly benefits from Claude/Gemini |
| `DOE` | Design of Experiments needs structured reasoning |
| `SYNTHESIZE` | Cross-source synthesis is LLM-capability dependent |
| `AUTORESEARCH` | Autonomous research chains need strong planning |

**Not eligible** (Ollama is sufficient): `SIMULATE`, `ANALYZE`, `SYNTHETIC`, `REPORT_DATA`, `STATUS`

---

## 4. Implementation Steps

### Phase 1: Deploy AIClient-2-API (1 day)

**Step 1.1** — Add to Docker Compose stack:

```yaml
# cluster/docker/docker-compose.leader.yml
aiclient-api:
  image: justlikemaki/aiclient-2-api:latest
  restart: unless-stopped
  ports:
    - "3000:3000"
    - "8085-8086:8085-8086"
    - "19876-19880:19876-19880"
  volumes:
    - ./configs/aiclient:/app/configs
  environment:
    - REQUIRED_API_KEY=${AICLIENT_API_KEY:-darklab-internal}
  networks:
    - darklab
```

**Step 1.2** — Generate OAuth credentials via Web UI (`http://192.168.23.25:3000`):
- Authorize one Google account for Gemini CLI OAuth
- Install Kiro client and extract `kiro-auth-token.json`
- Optionally authorize Codex via PKCE flow

**Step 1.3** — Configure provider pool (`configs/aiclient/provider_pools.json`):

```json
{
  "gemini-cli-oauth": [
    {
      "uuid": "gemini-darklab-1",
      "priority": 1,
      "checkHealth": true
    }
  ],
  "claude-kiro-oauth": [
    {
      "uuid": "kiro-darklab-1",
      "priority": 1,
      "checkHealth": true,
      "notSupportedModels": ["claude-opus-4-5"]
    }
  ]
}
```

**Step 1.4** — Verify endpoint health:

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Authorization: Bearer darklab-internal" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash","messages":[{"role":"user","content":"ping"}]}'
```

### Phase 2: Add Boost Tier to Model Router (0.5 day)

**Step 2.1** — Add `AICLIENT_BASE_URL` to `config.py`:

```python
aiclient_base_url: str = Field(
    default="", env="AICLIENT_BASE_URL",
    description="AIClient-2-API endpoint for boost tier (empty = disabled)"
)
aiclient_api_key: str = Field(
    default="darklab-internal", env="AICLIENT_API_KEY"
)
boost_enabled: bool = Field(
    default=False, env="DARKLAB_BOOST_ENABLED",
    description="Enable Tier 3 boost via AIClient-2-API"
)
```

**Step 2.2** — Add `call_aiclient()` to `llm_client.py`:

```python
async def call_aiclient(
    prompt: str,
    system: str = "",
    model: str = "gemini-2.5-flash",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Call AIClient-2-API (client-account fallback). Zero cost."""
    settings = get_settings()
    if not settings.aiclient_base_url:
        raise RuntimeError("AIClient-2-API not configured")

    client = AsyncOpenAI(
        api_key=settings.aiclient_api_key,
        base_url=settings.aiclient_base_url,
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=_build_messages(system, prompt),
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # Log as zero-cost call
    await _record_spend(model, 0, 0, cost_usd=0.0)
    return resp.choices[0].message.content or ""
```

**Step 2.3** — Extend `call_routed()` with boost fallback:

```python
async def call_routed(prompt, system="", task_type=None, **kwargs):
    tier = _select_tier(task_type)

    if tier == Tier.PLANNING:
        try:
            return await call_litellm(prompt, system, model="claude-sonnet-4-6", **kwargs)
        except BudgetExhaustedError:
            if get_settings().boost_enabled:
                logger.info("Planning budget exhausted, falling back to AIClient boost")
                return await call_aiclient(prompt, system, model="claude-sonnet-4-5", **kwargs)
            return await call_litellm(prompt, system, model="llama3.1:8b", **kwargs)

    if tier == Tier.BOOST:
        try:
            return await call_aiclient(prompt, system, model="gemini-2.5-flash", **kwargs)
        except Exception:
            logger.warning("AIClient boost unavailable, falling back to Ollama")
            return await call_litellm(prompt, system, model="llama3.1:8b", **kwargs)

    return await call_litellm(prompt, system, model="llama3.1:8b", **kwargs)
```

### Phase 3: Paperclip Governance Integration (0.5 day)

**Step 3.1** — Add boost budget tracking to Paperclip:
- AIClient calls report `cost_cents = 0` but log as `provider: "aiclient"`
- Dashboard shows AIClient call count separately
- Daily boost usage limit (e.g., 100 calls/day) prevents abuse

**Step 3.2** — Add boost toggle to Paperclip dashboard:
- CEO (Boss) can enable/disable boost per agent via UI toggle
- Stored as agent metadata flag: `boostEnabled: boolean`
- PicoClaw `/boost on|off` Telegram command for quick toggling

**Step 3.3** — DRVP event for boost usage:
- New event type: `llm.call.boosted` emitted when AIClient is used
- Office EventTimeline shows boost calls with distinct icon
- PaperclipPanel shows "X boost calls today" counter

### Phase 4: PicoClaw Integration (0.5 day)

**Step 4.1** — Add `/boost` command to PicoClaw:

```
/boost on       — Enable Tier 3 boost for current session
/boost off      — Disable boost, revert to standard tiers
/boost status   — Show AIClient health, quota remaining, calls today
```

**Step 4.2** — Auto-boost for specific commands:
When a user sends `/research` or `/literature` via Telegram, PicoClaw can automatically use boost tier if:
- Boost is enabled for the requesting agent
- AIClient health check passes
- Daily boost limit not exhausted

---

## 5. Benefits

### 5.1 Cost Reduction

| Scenario | Without AIClient | With AIClient Boost |
|---|---|---|
| Planning when API budget exhausted | Falls back to Ollama (poor quality) | Uses Claude Sonnet via Kiro (free, high quality) |
| Research task (non-critical) | $0.003-0.015 per call via Anthropic | $0.00 via Gemini/Kiro |
| Weekend autonomous research | Limited by $50/day budget | Supplemented by free client quota |
| Cross-validation | Expensive across multiple APIs | One paid + one free via AIClient |

**Estimated monthly savings:** $200-400 (30-50% of current $900 Academic + $600 Experiment budget) when boost handles execution-tier tasks that currently consume paid API tokens.

### 5.2 Quality Improvement

- **Research tasks** currently running on Ollama llama3.1:8b (8B params) can optionally use Gemini 2.5 Flash (significantly more capable) at zero cost.
- **Literature reviews** benefit from Claude Sonnet's superior comprehension, available free through Kiro.
- **Cross-validation** becomes practical: run the same prompt through Anthropic API and AIClient-Gemini to compare.

### 5.3 Resilience

- If Anthropic API goes down, agents can continue via AIClient → Kiro (still Claude models).
- If LiteLLM proxy fails, AIClient provides independent model access.
- Account pool rotation across multiple OAuth tokens extends effective rate limits.

---

## 6. Risks and Limitations

### 6.1 Terms of Service

| Risk | Severity | Mitigation |
|---|---|---|
| **Provider TOS violation** — Using client OAuth tokens in a server context may violate Gemini CLI / Kiro / Codex terms of service | **HIGH** | Treat as temporary R&D fallback only. Never use for production customer-facing workloads. Can be disabled instantly via env var. |
| **Account suspension** — Providers may detect non-client usage patterns and suspend accounts | **MEDIUM** | Use dedicated research accounts (not personal). Account pool distributes load. Health checks detect suspensions immediately. |
| **Quota exhaustion** — Free tiers have daily/monthly limits (Kiro: 500 credits, Gemini: RPD caps) | **LOW** | Pool manager handles 429s gracefully. Automatic fallback to Ollama when exhausted. |

### 6.2 Reliability

| Risk | Severity | Mitigation |
|---|---|---|
| **Token expiry during long tasks** — OAuth tokens expire (typically 1h) | **MEDIUM** | AIClient auto-refreshes 5 min before expiry. Pool manager rotates to fresh tokens. |
| **Rate limiting** — Client quotas are lower than paid API | **MEDIUM** | Pool with multiple accounts. Fallback chain: Gemini → Kiro → Ollama. Never block on AIClient. |
| **Service unavailability** — AIClient itself can fail | **LOW** | Health check before routing. Instant fallback to LiteLLM/Ollama. AIClient failure = transparent to user. |

### 6.3 Security

| Risk | Severity | Mitigation |
|---|---|---|
| **Credential exposure** — OAuth tokens stored on disk | **MEDIUM** | Tokens in Docker volume with restricted permissions. Internal network only (no external exposure). Rotate tokens monthly. |
| **Request logging** — AIClient logs all requests/responses | **LOW** | Disable AIClient logging in production. Or: useful for audit trail. Internal network only. |

### 6.4 Architectural

| Risk | Severity | Mitigation |
|---|---|---|
| **Dependency on third-party project** — AIClient-2-API is community-maintained | **MEDIUM** | Pin Docker image version. Fork if needed. It's a standalone service — easy to replace. |
| **Protocol drift** — Providers change APIs, AIClient may lag | **LOW** | Monitor AIClient releases. Gemini/Claude protocols are stable. Health checks catch breakage. |

---

## 7. Governance Rules

To ensure this remains a temporary, controlled capability:

1. **Kill switch:** `DARKLAB_BOOST_ENABLED=false` in `.env` instantly disables all AIClient routing. Default is **off**.

2. **CEO approval gate:** Boost activation requires Boss (CEO) approval in Paperclip before first use each month. Stored as monthly approval record.

3. **Daily caps:** Maximum 100 boost calls per agent per day. Enforced in `llm_client.py` alongside existing budget enforcement.

4. **Audit trail:** Every boost call logs to:
   - Local spend file (provider: "aiclient", cost_usd: 0.0)
   - DRVP event stream (`llm.call.boosted`)
   - Paperclip activity log

5. **No customer data:** Boost tier must never process external customer data or PII. Research and internal use only.

6. **Quarterly review:** Every 90 days, assess:
   - Total boost calls vs paid API calls (ratio should stay < 40%)
   - Any account warnings or suspensions
   - Whether direct API budget should be increased instead
   - Provider TOS changes

7. **Sunset plan:** If any provider explicitly prohibits server-side OAuth usage, disable that provider in AIClient within 24 hours. The system is designed for this — removing a provider from `provider_pools.json` is a one-line change.

---

## 8. Implementation Timeline

| Week | Deliverable | Owner |
|---|---|---|
| 1 | Deploy AIClient-2-API Docker container, authorize Gemini + Kiro | Ops |
| 1 | Add `call_aiclient()` and boost tier to model router | Dev |
| 2 | Paperclip boost toggle + DRVP events + daily cap enforcement | Dev |
| 2 | PicoClaw `/boost` command | Dev |
| 2 | Integration testing: research task via boost tier end-to-end | QA |
| 3 | CEO review, enable for Academic agent only (pilot) | Boss |
| 4 | Expand to Experiment agent if pilot successful | Boss |

**Total effort:** ~3 developer-days + 1 day ops setup

---

## 9. Recommendation

**Proceed with Phase 1-2 (deploy + router integration) immediately.** The technical risk is minimal — AIClient-2-API runs as an isolated Docker container, the boost tier is off by default, and the fallback chain ensures zero disruption if AIClient is unavailable.

**Defer Phase 3-4 (Paperclip governance + PicoClaw commands) until after a 2-week pilot** with the Academic agent using boost for research tasks only. This provides real usage data on quota consumption, quality improvement, and provider stability before investing in full governance tooling.

**Key principle:** AIClient-2-API is a **research accelerator, not an infrastructure dependency.** Design every integration point with the assumption that it will be disabled tomorrow. The system must work exactly as it does today with `DARKLAB_BOOST_ENABLED=false`.

---

## Appendix A: AIClient-2-API Configuration Reference

```json
// configs/aiclient/config.json
{
  "REQUIRED_API_KEY": "darklab-internal",
  "SERVER_PORT": 3000,
  "HOST": "0.0.0.0",
  "MODEL_PROVIDER": "gemini-cli-oauth",
  "PROVIDER_POOLS_FILE_PATH": "configs/provider_pools.json",
  "MAX_ERROR_COUNT": 3,
  "TLS_SIDECAR_ENABLED": false,
  "CRON_REFRESH_TOKEN": true,
  "providerFallbackChain": {
    "gemini-cli-oauth": ["claude-kiro-oauth"],
    "claude-kiro-oauth": ["gemini-cli-oauth"]
  }
}
```

## Appendix B: Environment Variables

```bash
# Add to ~/.darklab/.env
AICLIENT_BASE_URL=http://aiclient-api:3000/v1
AICLIENT_API_KEY=darklab-internal
DARKLAB_BOOST_ENABLED=false    # Off by default
DARKLAB_BOOST_DAILY_LIMIT=100  # Max boost calls per agent per day
```
