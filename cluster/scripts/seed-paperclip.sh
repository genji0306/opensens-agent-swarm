#!/bin/bash
# Seed Paperclip AI with DarkLab org chart
# Run on Leader AFTER Paperclip is running (port 3100)
# Creates: Boss, Leader, Academic, Experiment agents with budgets

set -uo pipefail

DARKLAB_HOME="${DARKLAB_HOME:-${HOME}/.darklab}"
if [[ -f "${DARKLAB_HOME}/.env" ]]; then
    source "${DARKLAB_HOME}/.env"
fi

PAPERCLIP_URL="${PAPERCLIP_URL:-http://localhost:3100}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== DarkLab Paperclip Org Chart Seeder ==="
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Paperclip: ${PAPERCLIP_URL}"
echo ""

# Check Paperclip is running
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${PAPERCLIP_URL}" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" != "200" ]] && [[ "$HTTP_CODE" != "302" ]]; then
    echo "ERROR: Paperclip not reachable at ${PAPERCLIP_URL} (HTTP ${HTTP_CODE})"
    echo "Start Paperclip first:"
    echo "  launchctl load ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist"
    echo "  # or: cd ${DARKLAB_HOME}/paperclip && pnpm dev"
    exit 1
fi
echo "Paperclip is running."
echo ""

CREATED=0
SKIPPED=0
FAILED=0

# Helper: POST to Paperclip API with response validation
paperclip_create_agent() {
    local agent_name="$1"
    local data="$2"

    # Check if agent already exists (GET first for idempotency)
    local encoded_name
    encoded_name=$(printf '%s' "$agent_name" | sed 's/ /%20/g')
    local existing
    existing=$(curl -s -o /dev/null -w "%{http_code}" \
        "${PAPERCLIP_URL}/api/agents?name=${encoded_name}" 2>/dev/null || echo "000")

    if [[ "$existing" == "200" ]]; then
        local body
        body=$(curl -s "${PAPERCLIP_URL}/api/agents?name=${encoded_name}" 2>/dev/null)
        # Check if the response contains the agent (non-empty array or object with the name)
        if echo "$body" | grep -q "\"name\"" 2>/dev/null; then
            echo "  SKIP: ${agent_name} (already exists)"
            SKIPPED=$((SKIPPED + 1))
            return 0
        fi
    fi

    # Create the agent
    local response http_code body
    response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d "$data" \
        "${PAPERCLIP_URL}/api/agents" 2>/dev/null)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    case "$http_code" in
        200|201)
            echo "  OK: ${agent_name} created"
            CREATED=$((CREATED + 1))
            ;;
        409)
            echo "  SKIP: ${agent_name} (already exists)"
            SKIPPED=$((SKIPPED + 1))
            ;;
        *)
            echo "  FAIL: ${agent_name} (HTTP ${http_code})"
            if [[ -n "$body" ]]; then
                echo "        Response: ${body}"
            fi
            FAILED=$((FAILED + 1))
            ;;
    esac
}

# Step 1: Create org chart agents
echo "--- Creating Org Chart ---"
echo ""

# Boss (CEO — human adapter, no AI budget)
echo "Creating: Boss (CEO)..."
paperclip_create_agent "Boss" '{
  "name": "Boss",
  "role": "CEO",
  "type": "human",
  "description": "Human operator — command & control via Telegram and dashboard",
  "adapter": {
    "type": "human",
    "channels": ["telegram", "dashboard"]
  },
  "budget": {
    "daily_limit_usd": 0,
    "note": "Human operator — no AI budget needed"
  }
}'
echo ""

# DarkLab Leader (CTO — OpenClaw gateway adapter)
echo "Creating: DarkLab Leader (CTO)..."
paperclip_create_agent "DarkLab Leader" '{
  "name": "DarkLab Leader",
  "role": "CTO",
  "type": "ai",
  "description": "Gateway orchestrator — routes commands, plans research campaigns, coordinates agents",
  "adapter": {
    "type": "openclaw_gateway",
    "url": "ws://localhost:18789",
    "clientId": "paperclip-leader",
    "displayName": "darklab-leader"
  },
  "budget": {
    "daily_limit_usd": 50,
    "models": ["claude-opus-4-6", "gemini-2.0-flash"]
  },
  "reports_to": "Boss"
}'
echo ""

# DarkLab Academic (Research Director)
echo "Creating: DarkLab Academic (Research Director)..."
paperclip_create_agent "DarkLab Academic" '{
  "name": "DarkLab Academic",
  "role": "Research Director",
  "type": "ai",
  "description": "Literature search, cross-validation, experiment design, paper drafting",
  "adapter": {
    "type": "openclaw_node",
    "gateway_url": "ws://localhost:18789",
    "displayName": "darklab-academic"
  },
  "budget": {
    "daily_limit_usd": 30,
    "models": ["claude-sonnet-4-6", "gpt-4o", "gemini-2.0-flash", "perplexity-sonar"]
  },
  "reports_to": "DarkLab Leader"
}'
echo ""

# DarkLab Experiment (Lab Director)
echo "Creating: DarkLab Experiment (Lab Director)..."
paperclip_create_agent "DarkLab Experiment" '{
  "name": "DarkLab Experiment",
  "role": "Lab Director",
  "type": "ai",
  "description": "Simulation, data analysis, synthetic data generation, AutoResearch ML loop",
  "adapter": {
    "type": "openclaw_node",
    "gateway_url": "ws://localhost:18789",
    "displayName": "darklab-experiment"
  },
  "budget": {
    "daily_limit_usd": 20,
    "models": ["claude-sonnet-4-6", "pytorch-mps"]
  },
  "reports_to": "DarkLab Leader"
}'
echo ""

# Step 2: Copy adapter config
echo "--- Installing Adapter Config ---"
ADAPTER_CONFIG="${DARKLAB_HOME}/paperclip/openclaw-adapter.json"
INSTALLER_CONFIG="$(dirname "$SCRIPT_DIR")/configs/paperclip-openclaw-adapter.json"
if [[ -f "$INSTALLER_CONFIG" ]]; then
    cp "$INSTALLER_CONFIG" "$ADAPTER_CONFIG" 2>/dev/null || true
    echo "Adapter config copied to ${ADAPTER_CONFIG}"
elif [[ -f "${SCRIPT_DIR}/../configs/paperclip-openclaw-adapter.json" ]]; then
    cp "${SCRIPT_DIR}/../configs/paperclip-openclaw-adapter.json" "$ADAPTER_CONFIG" 2>/dev/null || true
    echo "Adapter config copied to ${ADAPTER_CONFIG}"
else
    echo "Warning: adapter config not found in installer, creating inline..."
    cat > "$ADAPTER_CONFIG" << 'ADAPTER'
{
  "type": "openclaw_gateway",
  "url": "ws://localhost:18789",
  "clientId": "paperclip-controller",
  "autoPairOnFirstConnect": true,
  "sessionKeyStrategy": "issue"
}
ADAPTER
    echo "Adapter config created at ${ADAPTER_CONFIG}"
fi

echo ""
echo "=== Paperclip Org Chart Seeder Complete ==="
echo ""
echo "  Results: ${CREATED} created, ${SKIPPED} skipped, ${FAILED} failed"
echo ""
echo "  Agents:"
echo "    Boss             (CEO, human)"
echo "    DarkLab Leader   (CTO, \$50/day)"
echo "    DarkLab Academic (Research Director, \$30/day)"
echo "    DarkLab Experiment (Lab Director, \$20/day)"
echo ""
echo "  Dashboard: ${PAPERCLIP_URL}"
echo "  Adapter config: ${ADAPTER_CONFIG}"

if [[ "$FAILED" -gt 0 ]]; then
    echo ""
    echo "  WARNING: ${FAILED} agent(s) failed to create."
    echo "  Verify Paperclip API is running and check the response errors above."
    exit 1
fi
