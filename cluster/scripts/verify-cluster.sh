#!/bin/bash
# DarkLab Cluster Verification Script
# Checks all components installed by the DarkLab installer are functional.
# Run on each device after installation, or from Boss to verify the full cluster.

set -uo pipefail

DARKLAB_HOME="${DARKLAB_HOME:-${HOME}/.darklab}"
PASS=0
FAIL=0
WARN=0

pass()  { echo "  [PASS] $1"; ((PASS++)); }
fail()  { echo "  [FAIL] $1"; ((FAIL++)); }
warn()  { echo "  [WARN] $1"; ((WARN++)); }
header(){ echo ""; echo "=== $1 ==="; }

# Detect role
if [[ -f "${DARKLAB_HOME}/.env" ]]; then
    ROLE=$(grep "^DARKLAB_ROLE=" "${DARKLAB_HOME}/.env" 2>/dev/null | cut -d= -f2)
else
    ROLE="${1:-unknown}"
fi

echo "DarkLab Cluster Verification"
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Device:    $(hostname)"
echo "Role:      ${ROLE}"

# ── Core Infrastructure ──────────────────────────────────────────

header "Core Infrastructure"

# Homebrew
if command -v brew &>/dev/null; then
    pass "Homebrew installed"
else
    fail "Homebrew not found"
fi

# uv
if command -v uv &>/dev/null; then
    pass "uv installed ($(uv --version 2>/dev/null | head -1))"
else
    fail "uv not found"
fi

# pnpm
if command -v pnpm &>/dev/null; then
    pass "pnpm installed"
else
    warn "pnpm not found (needed for Paperclip)"
fi

# OpenClaw
if command -v openclaw &>/dev/null; then
    pass "OpenClaw installed ($(openclaw --version 2>/dev/null || echo 'version unknown'))"
else
    fail "OpenClaw not found"
fi

# Tailscale
if command -v tailscale &>/dev/null; then
    TS_STATUS=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('BackendState','unknown'))" 2>/dev/null || echo "unknown")
    if [[ "$TS_STATUS" == "Running" ]]; then
        pass "Tailscale running"
    else
        warn "Tailscale installed but status: ${TS_STATUS}"
    fi
else
    warn "Tailscale not found (optional for LAN-only setup)"
fi

# ── DarkLab Home ─────────────────────────────────────────────────

header "DarkLab Home (${DARKLAB_HOME})"

if [[ -d "$DARKLAB_HOME" ]]; then
    pass "DarkLab home directory exists"
else
    fail "DarkLab home directory missing"
fi

if [[ -f "${DARKLAB_HOME}/.env" ]]; then
    pass ".env configuration file exists"
    PERMS=$(stat -f "%Lp" "${DARKLAB_HOME}/.env" 2>/dev/null || stat -c "%a" "${DARKLAB_HOME}/.env" 2>/dev/null || echo "unknown")
    if [[ "$PERMS" == "600" ]]; then
        pass ".env permissions are 600 (secure)"
    else
        warn ".env permissions are ${PERMS} (should be 600)"
    fi
else
    fail ".env configuration missing"
fi

if [[ -d "${DARKLAB_HOME}/logs" ]]; then
    pass "Logs directory exists"
else
    warn "Logs directory missing (will be created on first run)"
fi

# ── Python Environment ───────────────────────────────────────────

header "Python Environment"

VENV_DIR="${DARKLAB_HOME}/.venv"
if [[ -d "$VENV_DIR" ]]; then
    pass "Python venv exists at ${VENV_DIR}"

    PYTHON="${VENV_DIR}/bin/python3"
    if [[ -x "$PYTHON" ]]; then
        pass "Python executable: $($PYTHON --version 2>&1)"

        # Check key packages
        for pkg in pydantic httpx pynacl structlog; do
            if "$PYTHON" -c "import $pkg" 2>/dev/null; then
                pass "Python package: ${pkg}"
            else
                fail "Python package missing: ${pkg}"
            fi
        done
    else
        fail "Python executable not found in venv"
    fi
else
    fail "Python venv not found"
fi

# ── Agent Code ───────────────────────────────────────────────────

header "Agent Code"

AGENTS_DIR="${DARKLAB_HOME}/agents"
if [[ -d "${AGENTS_DIR}/shared" ]]; then
    pass "Shared agent module installed"

    for mod in models config audit crypto llm_client node_bridge schemas; do
        if [[ -f "${AGENTS_DIR}/shared/${mod}.py" ]]; then
            pass "  shared/${mod}.py"
        else
            fail "  shared/${mod}.py missing"
        fi
    done
else
    fail "Shared agent module not found"
fi

if [[ "$ROLE" == "academic" ]]; then
    if [[ -d "${AGENTS_DIR}/academic" ]]; then
        pass "Academic agent module installed"
        for mod in research literature doe paper perplexity browser_agent; do
            if [[ -f "${AGENTS_DIR}/academic/${mod}.py" ]]; then
                pass "  academic/${mod}.py"
            else
                fail "  academic/${mod}.py missing"
            fi
        done
    else
        fail "Academic agent module not found"
    fi
fi

if [[ "$ROLE" == "experiment" ]]; then
    if [[ -d "${AGENTS_DIR}/experiment" ]]; then
        pass "Experiment agent module installed"
        for mod in simulation analysis synthetic report_data autoresearch; do
            if [[ -f "${AGENTS_DIR}/experiment/${mod}.py" ]]; then
                pass "  experiment/${mod}.py"
            else
                fail "  experiment/${mod}.py missing"
            fi
        done
    else
        fail "Experiment agent module not found"
    fi
fi

# ── Ed25519 Keys ─────────────────────────────────────────────────

header "Ed25519 Keys"

if [[ -f "${DARKLAB_HOME}/keys/signing.key" ]]; then
    pass "Signing key exists"
else
    fail "Signing key missing"
fi

if [[ -f "${DARKLAB_HOME}/keys/signing.pub" ]]; then
    pass "Public key (signing.pub) exists"
else
    fail "Public key (signing.pub) missing"
fi

# ── Skills ───────────────────────────────────────────────────────

header "OpenClaw Skills"

SKILLS_DIR="${HOME}/.openclaw/skills"
if [[ -d "$SKILLS_DIR" ]]; then
    SKILL_COUNT=$(find "$SKILLS_DIR" -name "SKILL.md" 2>/dev/null | wc -l | tr -d ' ')
    pass "Skills directory exists (${SKILL_COUNT} skills found)"

    # Check role-specific skills
    if [[ "$ROLE" == "leader" ]]; then
        for s in darklab-leader darklab-synthesis darklab-media-gen darklab-notebooklm; do
            [[ -d "${SKILLS_DIR}/${s}" ]] && pass "  ${s}" || fail "  ${s} missing"
        done
    elif [[ "$ROLE" == "academic" ]]; then
        for s in darklab-research darklab-literature darklab-doe darklab-paper darklab-perplexity; do
            [[ -d "${SKILLS_DIR}/${s}" ]] && pass "  ${s}" || fail "  ${s} missing"
        done
    elif [[ "$ROLE" == "experiment" ]]; then
        for s in darklab-simulation darklab-analysis darklab-synthetic darklab-report-data darklab-autoresearch; do
            [[ -d "${SKILLS_DIR}/${s}" ]] && pass "  ${s}" || fail "  ${s} missing"
        done
    fi
else
    fail "Skills directory not found"
fi

# Claude Scientific Skills
header "Claude Scientific Skills"

CLAUDE_SKILLS="${HOME}/.claude/skills"
if [[ -d "$CLAUDE_SKILLS" ]]; then
    CS_COUNT=$(ls -d "${CLAUDE_SKILLS}"/*/ 2>/dev/null | wc -l | tr -d ' ')
    pass "Claude skills directory exists (${CS_COUNT} skills)"

    if [[ "$ROLE" == "academic" ]]; then
        for s in pubmed-database arxiv-database biorxiv-database scientific-writing citation-management; do
            [[ -d "${CLAUDE_SKILLS}/${s}" ]] && pass "  ${s}" || warn "  ${s} not installed"
        done
    fi
    if [[ "$ROLE" == "experiment" ]]; then
        for s in scikit-learn matplotlib plotly; do
            [[ -d "${CLAUDE_SKILLS}/${s}" ]] && pass "  ${s}" || warn "  ${s} not installed"
        done
    fi
else
    warn "Claude skills directory not found (optional)"
fi

# ── AutoResearch (Experiment only) ───────────────────────────────

if [[ "$ROLE" == "experiment" ]]; then
    header "AutoResearch-macOS"

    AR_DIR="${DARKLAB_HOME}/tools/autoresearch"
    if [[ -d "$AR_DIR" ]]; then
        pass "AutoResearch installed at ${AR_DIR}"
        if [[ -f "${AR_DIR}/autoresearch.py" ]] || [[ -f "${AR_DIR}/main.py" ]]; then
            pass "AutoResearch main script found"
        else
            warn "AutoResearch main script not found (check repo structure)"
        fi
    else
        warn "AutoResearch not installed (clone may have failed during install)"
    fi

    if [[ -d "${DARKLAB_HOME}/autoresearch-workspaces" ]]; then
        pass "AutoResearch workspaces directory exists"
    else
        warn "AutoResearch workspaces directory missing"
    fi
fi

# ── Paperclip (Leader only) ──────────────────────────────────────

if [[ "$ROLE" == "leader" ]]; then
    header "Paperclip AI"

    PAPERCLIP_DIR="${DARKLAB_HOME}/paperclip"
    if [[ -d "$PAPERCLIP_DIR" ]]; then
        pass "Paperclip installed at ${PAPERCLIP_DIR}"
        if [[ -f "${PAPERCLIP_DIR}/package.json" ]]; then
            pass "Paperclip package.json found"
        fi
        if [[ -d "${PAPERCLIP_DIR}/dist" ]] || [[ -d "${PAPERCLIP_DIR}/build" ]]; then
            pass "Paperclip build output exists"
        else
            warn "Paperclip not built yet (run: cd ${PAPERCLIP_DIR} && pnpm build)"
        fi
    else
        warn "Paperclip not installed"
    fi
fi

# ── Browser Profiles (Academic/Leader) ───────────────────────────

if [[ "$ROLE" == "academic" ]] || [[ "$ROLE" == "leader" ]]; then
    header "Browser Profiles"

    PROFILES_DIR="${DARKLAB_HOME}/browser-profiles"
    if [[ -d "$PROFILES_DIR" ]]; then
        PROFILE_COUNT=$(ls -d "${PROFILES_DIR}"/*/ 2>/dev/null | wc -l | tr -d ' ')
        pass "Browser profiles directory (${PROFILE_COUNT} profiles)"
    else
        warn "Browser profiles directory not found"
    fi
fi

# ── OpenClaw Service ─────────────────────────────────────────────

header "OpenClaw Service"

if [[ "$ROLE" == "leader" ]]; then
    GW_STATUS=$(openclaw gateway status 2>/dev/null) || GW_STATUS=""
    if echo "$GW_STATUS" | grep -qi "running"; then
        pass "OpenClaw gateway service running"
    elif [[ -n "$GW_STATUS" ]]; then
        warn "OpenClaw gateway installed but not running (start with: openclaw gateway start)"
    else
        warn "OpenClaw gateway status unknown (run: openclaw gateway install --port 18789)"
    fi

    # Paperclip LaunchAgent
    PLIST_DIR="${HOME}/Library/LaunchAgents"
    if [[ -f "${PLIST_DIR}/com.opensens.darklab-paperclip.plist" ]]; then
        pass "Paperclip LaunchAgent exists"
    else
        warn "Paperclip LaunchAgent not found"
    fi
elif [[ "$ROLE" == "academic" ]] || [[ "$ROLE" == "experiment" ]]; then
    NODE_STATUS=$(openclaw node status 2>/dev/null) || NODE_STATUS=""
    if echo "$NODE_STATUS" | grep -qi "running"; then
        pass "OpenClaw node service running"
    elif [[ -n "$NODE_STATUS" ]]; then
        warn "OpenClaw node installed but not running (start with: openclaw node start)"
    else
        warn "OpenClaw node status unknown (run: openclaw node install --host <leader> --port 18789)"
    fi
fi

# ── Exec Approvals ──────────────────────────────────────────────

header "Exec Approvals"

EXEC_FILE="${HOME}/.openclaw/exec-approvals.json"
if [[ -f "$EXEC_FILE" ]]; then
    pass "exec-approvals.json exists"
else
    if [[ "$ROLE" == "boss" ]]; then
        pass "exec-approvals.json not needed for Boss role"
    else
        fail "exec-approvals.json missing (system.run commands will be denied)"
    fi
fi

# ── Node Config (node-hosts only) ──────────────────────────────

if [[ "$ROLE" == "academic" ]] || [[ "$ROLE" == "experiment" ]]; then
    header "Node Configuration"

    NODE_JSON="${HOME}/.openclaw/node.json"
    if [[ -f "$NODE_JSON" ]]; then
        pass "node.json exists at ${NODE_JSON}"
    else
        warn "node.json missing (openclaw node install should create this)"
    fi
fi

# ── Network Connectivity ────────────────────────────────────────

header "Network Connectivity"

if [[ "$ROLE" == "academic" ]] || [[ "$ROLE" == "experiment" ]]; then
    LEADER_HOST=$(grep "DARKLAB_LEADER_HOST" "${DARKLAB_HOME}/.env" 2>/dev/null | cut -d= -f2)
    LEADER_PORT=$(grep "DARKLAB_LEADER_PORT" "${DARKLAB_HOME}/.env" 2>/dev/null | cut -d= -f2)
    LEADER_PORT="${LEADER_PORT:-18789}"

    if [[ -n "$LEADER_HOST" ]]; then
        if curl -s -o /dev/null -w "%{http_code}" "http://${LEADER_HOST}:${LEADER_PORT}/health" 2>/dev/null | grep -q "200"; then
            pass "Leader gateway reachable at ${LEADER_HOST}:${LEADER_PORT}"
        else
            warn "Leader gateway not reachable at ${LEADER_HOST}:${LEADER_PORT} (may not be running yet)"
        fi
    else
        warn "DARKLAB_LEADER_HOST not set in .env"
    fi
fi

if [[ "$ROLE" == "leader" ]]; then
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:18789/health" 2>/dev/null | grep -q "200"; then
        pass "Local gateway running on port 18789"
    else
        warn "Local gateway not running (start with: openclaw gateway start)"
    fi

    PAPERCLIP_URL=$(grep "PAPERCLIP_URL" "${DARKLAB_HOME}/.env" 2>/dev/null | cut -d= -f2)
    if [[ -n "$PAPERCLIP_URL" ]]; then
        if curl -s -o /dev/null -w "%{http_code}" "${PAPERCLIP_URL}" 2>/dev/null | grep -qE "200|302"; then
            pass "Paperclip dashboard reachable at ${PAPERCLIP_URL}"
        else
            warn "Paperclip dashboard not reachable (start manually when ready)"
        fi
    fi
fi

# ── API Keys ─────────────────────────────────────────────────────

header "API Keys (presence check only)"

if [[ -f "${DARKLAB_HOME}/.env" ]]; then
    source "${DARKLAB_HOME}/.env"
    [[ -n "${ANTHROPIC_API_KEY:-}" ]] && pass "ANTHROPIC_API_KEY set" || fail "ANTHROPIC_API_KEY missing"

    if [[ "$ROLE" == "academic" ]]; then
        [[ -n "${OPENAI_API_KEY:-}" ]] && pass "OPENAI_API_KEY set" || warn "OPENAI_API_KEY not set"
        [[ -n "${GOOGLE_AI_API_KEY:-}" ]] && pass "GOOGLE_AI_API_KEY set" || warn "GOOGLE_AI_API_KEY not set"
        [[ -n "${PERPLEXITY_API_KEY:-}" ]] && pass "PERPLEXITY_API_KEY set" || warn "PERPLEXITY_API_KEY not set (browser-use fallback available)"
    fi

    if [[ "$ROLE" == "leader" ]]; then
        [[ -n "${GOOGLE_AI_API_KEY:-}" ]] && pass "GOOGLE_AI_API_KEY set" || warn "GOOGLE_AI_API_KEY not set"
        [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] && pass "TELEGRAM_BOT_TOKEN set" || warn "TELEGRAM_BOT_TOKEN not set"
    fi
fi

# ── Summary ──────────────────────────────────────────────────────

echo ""
echo "============================================"
echo "  VERIFICATION SUMMARY"
echo "============================================"
echo "  PASS: ${PASS}"
echo "  FAIL: ${FAIL}"
echo "  WARN: ${WARN}"
echo ""

if [[ $FAIL -eq 0 ]]; then
    echo "  Status: READY (${WARN} warnings)"
    exit 0
else
    echo "  Status: ISSUES FOUND (${FAIL} failures, ${WARN} warnings)"
    exit 1
fi
