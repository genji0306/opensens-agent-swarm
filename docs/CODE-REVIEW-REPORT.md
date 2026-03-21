# Opensens Agent Swarm — Code Review Report

> **Date:** 2026-03-21
> **Scope:** Full codebase (1,018 files, 5,033 nodes, 39,235 edges)
> **Method:** Code-review-graph analysis + targeted module review (30 files)
> **Reviewer:** Claude Opus 4.6

---

## Executive Summary

The codebase is **well-structured** with clean separation of concerns, consistent async/await patterns, and thoughtful defensive programming. The middleware pipeline pattern is elegant, DRVP event emission is consistent, and optional dependencies are properly guarded. **430 tests pass** across all packages.

However, the review identified **6 critical/high-severity issues** that should be addressed before production deployment, primarily around **authentication** (no auth on FastAPI server), **budget enforcement logic** (comparing agent budget against company-wide spend), and **memory leaks** in long-running processes.

### Findings Summary

| Severity | Core Python | Cluster Agents | Office + Paperclip | Total |
|----------|:-----------:|:--------------:|:-------------------:|:-----:|
| **CRITICAL** | 0 | 1 | 1 | **2** |
| **HIGH** | 4 | 4 | 4 | **12** |
| **MEDIUM** | 9 | 9 | 7 | **25** |
| **LOW** | 10 | 10 | 4 | **24** |
| **Total** | **23** | **24** | **16** | **63** |

### Code Graph Statistics

```
Files parsed:      1,018
Total nodes:       5,033  (189 classes, 3,373 functions, 409 tests)
Total edges:      39,235  (28,822 calls, 4,552 imports, 1,177 test links)
Languages:         Python, TypeScript, TSX, JavaScript
Oversized functions: 30 (>80 lines), largest: heartbeatService at 2,097 lines
```

---

## CRITICAL Findings (2)

### CRIT-1: No authentication on FastAPI server

**File:** `cluster/agents/leader/serve.py`

The FastAPI server exposes `/dispatch`, `/synthesize`, `/media`, `/task`, `/config/boost`, and `/config/browser` endpoints with **zero authentication**. Any client on the `192.168.23.0/24` network can invoke agent dispatch, toggle boost mode, or exhaust the budget. The server binds to `0.0.0.0:8100`. CORS restricts browser origins but does not protect against direct HTTP calls.

**Fix:** Add API key authentication middleware validating `Authorization: Bearer <DARKLAB_API_KEY>`.

---

### CRIT-2: RPC response handler memory leak during reconnection

**File:** `office/src/gateway/rpc-client.ts` (lines 41-52)

When a WebSocket disconnects during a pending RPC request, the response handler registered in the `responseHandlers` Map is never deleted. The timeout will fire (rejecting the promise), but the handler entry leaks. Under reconnection churn with frequent RPC calls, this grows unboundedly.

**Fix:** Have `GatewayRpcClient` listen for status changes and reject+cleanup all pending requests on disconnect.

---

## HIGH Findings (12)

### Core Python (4)

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-1 | **Budget check compares agent budget vs. company-wide spend.** `get_cost_summary()` returns total company costs, not per-agent. Budget enforcement is fundamentally broken for multi-agent setups. | `core/oas_core/middleware/budget.py` | 62-67 |
| H-2 | **Approval gate fails open on Paperclip error.** When `create_approval()` raises, the middleware returns `approved: True`. A Paperclip outage (or deliberate DoS) bypasses all approval gates. | `core/oas_core/middleware/governance.py` | 231-232 |
| H-3 | **JSON injection via f-string in error handling.** Exception messages with quotes/backslashes produce malformed JSON. Attacker-controlled error messages could inject arbitrary JSON fields. | `core/oas_core/swarm.py` | 120 |
| H-4 | **Governance tests likely not running.** Test classes missing `@pytest.mark.asyncio` — async test methods may be silently skipped, meaning governance middleware has zero effective test coverage. | `core/tests/test_governance.py` | — |

### Cluster Agents (4)

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-5 | **SSRF via `reply_url`.** User-controlled URL receives full task results. Could target internal services or cloud metadata endpoints. | `cluster/agents/leader/serve.py` | 369-377 |
| H-6 | **Unauthenticated DRVP SSE endpoint.** `/drvp/events/{company_id}` accepts any company_id with no auth. Exposes research content, cost data, and approval decisions. | `cluster/agents/leader/serve.py` | 164 |
| H-7 | **Infinite recursion in credit-exhaustion retry.** `call_litellm` retries itself recursively with no depth guard. If the fallback model also triggers a credit error pattern, stack overflow occurs. | `cluster/agents/shared/llm_client.py` | 216 |
| H-8 | **Global `asyncio.Lock` cross-event-loop risk.** Lock created lazily but no protection against usage from different event loops during testing. | `cluster/agents/leader/dispatch.py` | 57, 66 |

### Office + Paperclip (4)

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-9 | **`requestIssueMap` grows unboundedly.** Entries only removed on terminal events. Crashed/abandoned requests leak entries forever. | `paperclip/server/src/services/drvp-issue-linker.ts` | 44 |
| H-10 | **Browser-blocked timer race.** `setTimeout` reverts agent status to "thinking" after 3s, but is never cancelled. Subsequent events get overwritten by the stale timer. | `office/src/drvp/drvp-consumer.ts` | 184-191 |
| H-11 | **`heartbeatService` is 2,097 lines / `executeRun` is 600+ lines.** The most critical code path (running agent tasks) is extremely difficult to review, test, or modify safely. | `paperclip/server/src/services/heartbeat.ts` | 454-2550 |
| H-12 | **`enqueueWakeup` is 455 lines** with ~260 lines of deeply nested conditional logic for issue-execution-locking transactions. | `paperclip/server/src/services/heartbeat.ts` | 1837-2291 |

---

## MEDIUM Findings (25)

### Core Python (9)

| # | Finding | File |
|---|---------|------|
| M-1 | Campaign DAG infinite loop on circular dependencies — no cycle detection | `campaign.py` |
| M-2 | DRVP emit failure in error handler could swallow original exception | `middleware/__init__.py` |
| M-3 | Zero-cost calls (boost tier) recorded as 1 cent — inflates spend tracking | `budget.py` |
| M-4 | Encapsulation violation — governance calls `paperclip._request()` directly | `governance.py` |
| M-5 | WebSocket race condition — message loop and connect both read from same socket | `openclaw.py` |
| M-6 | Deprecated `asyncio.get_event_loop()` usage (Python 3.12+ warning) | `openclaw.py` |
| M-7 | Prompt visible in process table via `--prompt` CLI argument | `claude_code.py` |
| M-8 | Timeout does not kill Claude Code subprocess — process runs indefinitely | `claude_code.py` |
| M-9 | Response JSON parsing can raise unhandled `JSONDecodeError` | `paperclip.py` |

### Cluster Agents (9)

| # | Finding | File |
|---|---------|------|
| M-10 | Blocking file I/O (`fcntl.flock`) inside async context — blocks event loop | `llm_client.py` |
| M-11 | `fcntl` import is Unix-only — no portability guard | `llm_client.py` |
| M-12 | New HTTP client instantiated per LLM call — no connection pooling | `llm_client.py` |
| M-13 | No file locking on audit log writes — interleaved writes possible | `audit.py` |
| M-14 | No file permission check when loading Ed25519 private keys | `crypto.py` |
| M-15 | `_apply_boost_toggle` mutates frozen Pydantic settings directly | `dispatch.py` |
| M-16 | Single-step campaigns bypass approval gate entirely | `dispatch.py` |
| M-17 | `plan_campaign` silently converts malformed LLM JSON to single research step | `dispatch.py` |
| M-18 | Redis subscription leak — stalled SSE clients hold subscriptions indefinitely | `serve.py` |

### Office + Paperclip (7)

| # | Finding | File |
|---|---------|------|
| M-19 | SSE client has no authentication — EventSource doesn't support headers | `drvp-client.ts` |
| M-20 | Module-level timers not cleaned up on gateway reconnection | `office-store.ts` |
| M-21 | `send()` silently drops messages when WebSocket is not open | `ws-client.ts` |
| M-22 | `setAgentVisualStatusByName` uses O(n) scan on every DRVP event | `office-store.ts` |
| M-23 | `processAgentEvent` is 250 lines with 6 agent-ID resolution strategies | `office-store.ts` |
| M-24 | DRVP bridge relays Redis events to WebSocket clients without validation | `drvp-bridge.ts` |
| M-25 | Several helper functions use `any` type for DB transaction parameter | `issues.ts` |

---

## Test Coverage Gaps

| Module | Gap | Severity |
|--------|-----|----------|
| `cluster/agents/shared/crypto.py` | No test file exists — key gen, signing, verification untested | HIGH |
| `cluster/agents/shared/audit.py` | No test file exists — logging and concurrency untested | MEDIUM |
| `cluster/agents/leader/serve.py` | `/dispatch`, `/synthesize`, `/media`, `/task`, `/config/*` untested | MEDIUM |
| `core/tests/test_governance.py` | Async tests may be silently skipped (missing markers) | HIGH |
| `core/oas_core/adapters/openclaw.py` | RPC request/response cycle, connect handshake untested | MEDIUM |
| `cluster/agents/shared/llm_client.py` | Credit retry, `call_multi_ai`, `call_routed`, `call_aiclient` untested | MEDIUM |

---

## Oversized Functions (Top 15)

From the code-review-graph analysis (threshold: 80+ lines):

| Lines | Function | File |
|------:|----------|------|
| 2,097 | `heartbeatService` | `paperclip/server/src/services/heartbeat.ts` |
| 1,601 | `agentRoutes` | `paperclip/server/src/routes/agents.ts` |
| 1,240 | `OnboardingWizard` | `paperclip/ui/src/components/OnboardingWizard.tsx` |
| 1,165 | `accessRoutes` | `paperclip/server/src/routes/access.ts` |
| 1,163 | `issueRoutes` | `paperclip/server/src/routes/issues.ts` |
| 1,156 | `DesignGuide` | `paperclip/ui/src/pages/DesignGuide.tsx` |
| 1,131 | `issueService` | `paperclip/server/src/services/issues.ts` |
| 889 | `NewIssueDialog` | `paperclip/ui/src/components/NewIssueDialog.tsx` |
| 805 | `ProjectProperties` | `paperclip/ui/src/components/ProjectProperties.tsx` |
| 795 | `IssueDetail` | `paperclip/ui/src/pages/IssueDetail.tsx` |
| 714 | `AgentConfigForm` | `paperclip/ui/src/components/AgentConfigForm.tsx` |
| 637 | `startServer` | `paperclip/server/src/index.ts` |
| 632 | `Inbox` | `paperclip/ui/src/pages/Inbox.tsx` |
| 609 | `IssuesList` | `paperclip/ui/src/components/IssuesList.tsx` |
| 606 | `executeRun` | `paperclip/server/src/services/heartbeat.ts` |

---

## Recommended Priority Actions

### Immediate (before deployment)

1. **Add authentication to `serve.py`** — shared API key via `Authorization` header. Closes CRIT-1, H-5, H-6.
2. **Fix budget check** to compare agent-specific spend, not company total. Closes H-1.
3. **Fix JSON injection** in `swarm.py` — use `json.dumps()` instead of f-string. Closes H-3.
4. **Add recursion guard** to `call_litellm` — `if _retry_depth > 0: raise`. Closes H-7.

### Short-term (next sprint)

5. **Fix RPC response handler leak** — reject+cleanup all pending on disconnect. Closes CRIT-2.
6. **Make approval gate fail-closed** (or configurable). Closes H-2.
7. **Add TTL eviction** to `requestIssueMap` in drvp-issue-linker. Closes H-9.
8. **Track and cancel browser-blocked timers** per agent. Closes H-10.
9. **Verify governance tests run** — add `@pytest.mark.asyncio` markers. Closes H-4.
10. **Add `proc.kill()`** in Claude Code timeout handler. Closes M-8.

### Medium-term (refactoring sprint)

11. **Decompose `heartbeatService`** into `prepareRunContext()`, `invokeAdapter()`, `finalizeRun()`. Closes H-11, H-12.
12. **Add tests for `crypto.py` and `audit.py`** — security-critical modules with zero coverage.
13. **Wrap `_check_and_record_spend` in `asyncio.to_thread()`** — prevent event loop blocking.
14. **Add cycle detection** to campaign engine before DAG execution.
15. **Validate `reply_url`** against an allowlist of known broker URLs.

---

## Conclusion

The Opensens Agent Swarm is an ambitious and well-executed platform. The core architecture — middleware pipeline, DRVP protocol, campaign DAG engine, dual-mode dispatch — is sound. The primary risks are concentrated in two areas:

1. **Network security** — the FastAPI server and SSE endpoints lack authentication, making the cluster vulnerable to any device on the local network.
2. **Long-running process stability** — several unbounded data structures (`requestIssueMap`, `responseHandlers`, `agentIdCache`) will cause gradual memory growth on the Leader node.

Addressing the 4 immediate actions above would resolve the most impactful issues with minimal code changes.
