# DarkLab Installer — Development Context

**Version:** 2.1.0
**Date:** 2026-03-16
**Branch:** feature/lab-sequence-rehab

---

## Architecture Summary

4-device Mac mini cluster for autonomous AI-driven scientific research:

```
Boss (MacBook) → Leader (M4 16GB) → Academic (M4 24GB)
                                   → Experiment (M4 24GB)
```

- **OpenClaw** — Node.js gateway on Leader, node-hosts on Academic/Experiment
- **Paperclip AI** — Governance layer (budgets, approvals, org chart) on Leader :3100
- **Skills** — 14 OpenClaw skills invoked via `system.run` → Python agent modules
- **Agent pattern** — `async def handle(Task) -> TaskResult` + `run_agent()` entry point

---

## Component Status

| Component | Files | Status |
|-----------|-------|--------|
| install.sh | 1 | Done |
| roles/ | 5 (boss, leader, academic, experiment, lab-agent) | Done (lab-agent is stub) |
| common/ | 6 scripts | Done |
| configs/ | 6 files | Done |
| agents/shared/ | 7 modules | Done |
| agents/academic/ | 6 modules | Done |
| agents/experiment/ | 5 modules | Done |
| agents/leader/ | 4 modules | Done (dispatch + synthesis + media_gen + notebooklm) |
| skills/ | 14 skills | Done |
| scripts/ | 9 scripts | Done |
| tests/ | 7 files (conftest + 6 test files) | Done (56 tests passing) |
| pyproject.toml | 1 | Done (pytest + project config) |

**Overall: ~99% complete** (remaining: hardware bring-up only)

---

## Changes Made (2026-03-16)

### Priority 1 — Bug Fixes

1. **verify-cluster.sh line 188**: Fixed `keys/verify.key` → `keys/signing.pub`
   - `keys-setup.sh`, `crypto.py`, and `config.py` all create/reference `signing.pub`
   - The old check always failed even with correctly generated keys

2. **`__init__.py` files**: Confirmed already present in all 4 agent subdirectories — no action needed

### Priority 2 — New Leader Agent Modules

3. **agents/leader/synthesis.py** (new, ~110 lines)
   - Merges multi-source research findings into structured narratives
   - Uses Claude OPUS for high-quality synthesis
   - Input: research_results, simulation_data, analysis_results, original_plan
   - Output: executive_summary, key_findings, methodology_validation, data_consistency, recommendations, full_narrative

4. **agents/leader/media_gen.py** (new, ~160 lines)
   - Generates Word documents (.docx) and PowerPoint presentations (.pptx)
   - Uses python-docx for reports, python-pptx for slides
   - Input: synthesis data + output_types list
   - Output: deliverables with file paths

5. **agents/leader/notebooklm.py** (new, ~140 lines)
   - Browser automation for Google NotebookLM
   - Uses browser-use + langchain-anthropic (same pattern as academic/browser_agent.py)
   - Requires pre-authenticated Chrome profile at ~/.darklab/browser-profiles/notebooklm-research
   - Input: sources list, generate types, notebook_name
   - Output: notebook_url, assets list

### Supporting Changes

6. **agents/shared/models.py**: Added `NOTEBOOKLM = "notebooklm"` to TaskType enum

7. **agents/leader/dispatch.py**: Added notebooklm route to ROUTING_TABLE + planner prompt

8. **3 run.sh stubs updated** (skills/darklab-synthesis, darklab-media-gen, darklab-notebooklm):
   - Replaced error-echo stubs with real `uv run python3 -m leader.<module>` runners

9. **common/python-env.sh**: Added to leader extras:
   - `python-pptx>=1.0` (PPTX generation)
   - `browser-use>=0.2` (NotebookLM automation)
   - `langchain-anthropic>=0.3` (browser-use LLM backend)
   - `playwright>=1.40` (browser engine)
   - Playwright browser install now triggers for leader role too

### Documentation

10. **BOSS-AGENT-GUIDE.md** (new, ~300 lines)
    - Antigravity IDE operational runbook for Boss agent
    - Installation, post-install verification, all 8 scripts, Telegram integration, troubleshooting

---

## Key File Paths

```
agents/shared/
  config.py          — Settings from ~/.darklab/.env (Pydantic)
  models.py          — Task, TaskResult, TaskType, AgentInfo
  llm_client.py      — Anthropic/OpenAI/Gemini/Perplexity + budget enforcement
  node_bridge.py     — OpenClaw system.run ↔ Python bridge
  audit.py           — JSONL audit logger
  crypto.py          — Ed25519 sign/verify (PyNaCl)
  schemas.py         — EIP + RunRecord Pydantic models

agents/leader/
  dispatch.py        — Command routing + campaign planning
  synthesis.py       — Multi-source narrative synthesis (NEW)
  media_gen.py       — Word doc + PPTX generation (NEW)
  notebooklm.py      — NotebookLM browser automation (NEW)

configs/
  leader.config.yaml — OpenClaw gateway config (agents, discovery, Telegram)
  exec-approvals.json — system.run command allowlist
```

---

## Changes Made (2026-03-16 — v2.1.0)

### Budget Enforcement Concurrency Fix

11. **agents/shared/llm_client.py**: Added `_check_and_record_spend()` — atomic budget check + spend record
    - Previous approach had TOCTOU race: separate `_check_budget()` and `_record_spend()` allowed
      two concurrent calls to both pass the check then both record, exceeding the budget
    - New function holds `LOCK_EX` for the entire check-and-record operation
    - All 4 LLM call functions now use `_check_and_record_spend()` for recording

12. **tests/test_budget_concurrency.py** (new, ~130 lines)
    - Multiprocessing stress tests for budget enforcement
    - Tests: no data loss under concurrent writes, correct call count preservation,
      budget not exceeded under concurrent check-and-record, file integrity after 30 concurrent writes

### Model Upgrades

13. **Claude 4.6 model IDs** — Updated across all files:
    - `claude-opus-4-5-20250929` → `claude-opus-4-6-20260301`
    - `claude-sonnet-4-5-20250929` → `claude-sonnet-4-6-20260301`
    - Files updated: llm_client.py, synthesis.py, notebooklm.py, browser_agent.py,
      leader.config.yaml, seed-paperclip.sh, test_budget.py

### Paperclip API Validation

14. **scripts/seed-paperclip.sh**: Rewrote agent creation with proper validation
    - Added `paperclip_create_agent()` with HTTP response code checking
    - Idempotency: checks if agent exists before creating (skips on 409 or GET match)
    - Tracks created/skipped/failed counts with summary
    - Exits with error code if any agent creation fails

### NotebookLM Profile Setup

15. **scripts/setup-notebooklm-profile.sh** (new, ~120 lines)
    - Interactive helper for Leader device Chrome profile setup
    - Verifies Chrome + Playwright installation
    - Launches Chrome with correct `--user-data-dir` pointing to NotebookLM profile
    - Validates profile after user signs in: cookies, login data, profile size
    - Detects existing profiles and offers re-authentication

### Test Infrastructure

16. **pyproject.toml** (new) — Root project configuration
    - `pythonpath = ["agents"]` so pytest resolves `from shared.xxx` imports
    - `testpaths = ["tests"]`, `asyncio_mode = "auto"`
    - Project metadata and dependency manifest

17. **tests/conftest.py** (new) — Shared pytest fixtures
    - `darklab_home` fixture: temp directory with standard subdirs
    - `mock_settings` fixture: patched config for test-safe execution

### Dispatch Completeness Fix

18. **agents/leader/dispatch.py**: Added 3 missing skill routes
    - `perplexity` → Academic → darklab-perplexity
    - `synthetic` → Experiment → darklab-synthetic
    - `report-data` → Experiment → darklab-report-data
    - Routing table now covers all 13 skills (was 10)
    - Updated PLANNER_PROMPT with all 13 commands

19. **configs/leader.config.yaml**: Updated systemPrompt
    - Added all 13 slash commands to Leader agent prompt (was 7)

### New Tests

20. **tests/test_node_bridge.py** (new, ~100 lines)
    - Tests sync/async handler dispatch via argv and stdin
    - Error handling: invalid JSON, empty input, handler exceptions

21. **tests/test_dispatch_integration.py** (new, ~120 lines)
    - Routing table completeness: all 13 skills routable, correct nodes
    - Async dispatch handler: status, known commands, campaign planning
    - Campaign plan fallback when LLM returns invalid JSON

**Test suite: 56 tests, all passing**

---

## Changes Made (2026-03-16 — v2.1.0 Round 4)

### Bug Fixes

22. **agents/shared/llm_client.py**: Completed TOCTOU race fix
    - Removed 4 redundant `_check_budget()` calls (lines 159, 187, 211, 232) that ran
      before API calls without locking — these created a TOCTOU window
    - Removed now-unused `_check_budget()` and `_get_daily_spend()` functions
    - `_check_and_record_spend()` is now the sole budget enforcement path (atomic under LOCK_EX)

23. **install.sh**: Fixed version 2.0.0 → 2.1.0

24. **agents/academic/browser_agent.py** + **agents/leader/notebooklm.py**: Fixed hardcoded paths
    - `Path.home() / ".darklab"` → `settings.darklab_home` for testability and portability

### Robustness

25. **common/python-env.sh**: Added `command -v uv` pre-check before `uv sync`

26. **roles/{leader,academic,experiment,boss}.sh**: Added `set -euo pipefail` for standalone safety

### Documentation & Sync

27. **skills/darklab-leader/SKILL.md**: Updated routing table from 10 → 14 commands
    - Added: perplexity, synthetic, report-data, notebooklm

28. **CLAUDE.md** (new): Project guide for Claude Code sessions
    - Architecture, directory structure, agent pattern, routing table, conventions, test commands

---

## Remaining Work

| Item | Priority | Notes |
|------|----------|-------|
| End-to-end hardware bring-up | High | Test install.sh on actual Mac minis |
| OpenClaw pairing flow | High | Verify pairing works across real devices |
| lab-agent.sh implementation | Low | Blocked on instrument control hardware |
| Data comparison between sessions | Low | iOS app feature gap |
