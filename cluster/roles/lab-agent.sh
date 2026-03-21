#!/bin/bash
# Lab Agent role installer (future)
# Template for adding instrument control nodes

echo "[lab-agent] Starting Lab Agent installation..."
echo ""
echo "NOTE: Lab Agent support is planned for a future release."
echo "This installer creates the basic skeleton for instrument control nodes."
echo ""

# Step 1: Prerequisites
source "${SCRIPT_DIR}/common/prerequisites.sh"

# Step 2: OpenClaw
source "${SCRIPT_DIR}/common/openclaw-setup.sh"

# Step 3: Tailscale
source "${SCRIPT_DIR}/common/tailscale-setup.sh"

# Step 4: API Key
echo ""
ENV_FILE="${DARKLAB_HOME}/.env"
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    read -p "Anthropic API key (Claude): " ANTHROPIC_API_KEY
fi

# Discover Leader
echo "[lab-agent] Discovering Leader gateway..."
LEADER_HOST=""
BONJOUR_RESULT=$(dns-sd -B _openclaw._tcp . 2>/dev/null & BGPID=$!; sleep 3; kill $BGPID 2>/dev/null; wait $BGPID 2>/dev/null) || true
if [[ -n "$BONJOUR_RESULT" ]]; then
    LEADER_HOST="leader.local"
fi
if [[ -z "$LEADER_HOST" ]]; then
    read -p "Leader hostname or IP: " LEADER_HOST
fi
LEADER_PORT="${LEADER_PORT:-18789}"

cat > "$ENV_FILE" << EOF
# DarkLab Lab Agent Configuration
DARKLAB_ROLE=lab-agent
DARKLAB_VERSION=${DARKLAB_VERSION}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
DARKLAB_LEADER_HOST=${LEADER_HOST}
DARKLAB_LEADER_PORT=${LEADER_PORT}
EOF
chmod 600 "$ENV_FILE"

# Step 5: Python environment + keys
source "${SCRIPT_DIR}/common/python-env.sh" experiment
source "${SCRIPT_DIR}/common/keys-setup.sh"

# Step 6: Summary
echo ""
echo "============================================"
echo "  LAB AGENT INSTALLATION COMPLETE (Skeleton)"
echo "============================================"
echo ""
echo "  This is a template installation."
echo "  To add instrument support:"
echo "  1. Install SiLA2 device drivers"
echo "  2. Create instrument-specific OpenClaw skills"
echo "  3. Register device capabilities in node-host config"
echo ""
echo "  See: darklab_4device_architecture.md Section 2.2.5"
echo ""
