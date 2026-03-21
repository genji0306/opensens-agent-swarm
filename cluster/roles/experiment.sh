#!/bin/bash
set -euo pipefail
# Experiment Agent role installer
# Installs: OpenClaw node-host, compute stack (numpy, scipy, pandas, etc.)

echo "[experiment] Starting Experiment Agent installation..."
echo ""

# Step 1: Prerequisites
source "${SCRIPT_DIR}/common/prerequisites.sh"

# Step 2: OpenClaw
source "${SCRIPT_DIR}/common/openclaw-setup.sh"

# Step 3: Tailscale
source "${SCRIPT_DIR}/common/tailscale-setup.sh"

# Step 4: API Key
echo ""
echo "[experiment] Configuring API key..."
ENV_FILE="${DARKLAB_HOME}/.env"

if [[ -f "$ENV_FILE" ]]; then
    echo "[experiment] Existing .env found. Loading..."
    source "$ENV_FILE"
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    read -p "Anthropic API key (Claude): " ANTHROPIC_API_KEY
fi

# Discover Leader
echo ""
echo "[experiment] Discovering Leader gateway..."
LEADER_HOST=""

echo "[experiment] Searching for Leader via Bonjour..."
BONJOUR_RESULT=$(dns-sd -B _openclaw._tcp . 2>/dev/null & BGPID=$!; sleep 3; kill $BGPID 2>/dev/null; wait $BGPID 2>/dev/null) || true
if [[ -n "$BONJOUR_RESULT" ]]; then
    echo "[experiment] Found Leader via Bonjour!"
    LEADER_HOST="leader.local"
fi

if [[ -z "$LEADER_HOST" ]]; then
    read -p "Leader hostname or IP (e.g., leader.local or 192.168.1.100): " LEADER_HOST
fi

LEADER_PORT="${LEADER_PORT:-18789}"

cat > "$ENV_FILE" << EOF
# DarkLab Experiment Agent Configuration
DARKLAB_ROLE=experiment
DARKLAB_VERSION=${DARKLAB_VERSION}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
DARKLAB_LEADER_HOST=${LEADER_HOST}
DARKLAB_LEADER_PORT=${LEADER_PORT}
EOF
chmod 600 "$ENV_FILE"
echo "[experiment] Configuration saved to ${ENV_FILE}"

# Step 5: Python environment + keys
source "${SCRIPT_DIR}/common/python-env.sh" experiment
source "${SCRIPT_DIR}/common/keys-setup.sh"

# Step 6: Copy Python agent code
echo "[experiment] Installing Python agent code..."
AGENTS_TARGET="${DARKLAB_HOME}/agents"
mkdir -p "$AGENTS_TARGET"
cp -r "${SCRIPT_DIR}/agents/shared" "${AGENTS_TARGET}/"
cp -r "${SCRIPT_DIR}/agents/experiment" "${AGENTS_TARGET}/"
echo "[experiment] Agent code installed to ${AGENTS_TARGET}"

# Step 7: Install AutoResearch-macOS
echo "[experiment] Installing AutoResearch-macOS..."
AUTORESEARCH_DIR="${DARKLAB_HOME}/tools/autoresearch"
if [[ ! -d "$AUTORESEARCH_DIR" ]]; then
    mkdir -p "${DARKLAB_HOME}/tools"
    git clone --depth 1 https://github.com/miolini/autoresearch-macos.git "$AUTORESEARCH_DIR" 2>/dev/null || \
        echo "[experiment] Warning: Could not clone autoresearch-macos (check network)"
fi
if [[ -d "$AUTORESEARCH_DIR" ]]; then
    echo "[experiment] AutoResearch installed at ${AUTORESEARCH_DIR}"
else
    echo "[experiment] Skipping AutoResearch (clone failed)"
fi

# Create autoresearch workspace directory
mkdir -p "${DARKLAB_HOME}/autoresearch-workspaces"

# Step 8: Install DarkLab skills
echo "[experiment] Installing DarkLab skills..."
SKILLS_TARGET="${HOME}/.openclaw/skills"
mkdir -p "$SKILLS_TARGET"
for skill_dir in "${SCRIPT_DIR}/skills/darklab-simulation" \
                 "${SCRIPT_DIR}/skills/darklab-analysis" \
                 "${SCRIPT_DIR}/skills/darklab-synthetic" \
                 "${SCRIPT_DIR}/skills/darklab-report-data" \
                 "${SCRIPT_DIR}/skills/darklab-autoresearch"; do
    if [[ -d "$skill_dir" ]]; then
        skill_name=$(basename "$skill_dir")
        cp -r "$skill_dir" "${SKILLS_TARGET}/${skill_name}"
        echo "[experiment] Installed skill: ${skill_name}"
    fi
done

# Install Claude Scientific Skills (experiment subset)
echo "[experiment] Installing Claude Scientific Skills (compute subset)..."
CLAUDE_SKILLS_DIR="${HOME}/.claude/skills"
mkdir -p "$CLAUDE_SKILLS_DIR"
if [[ ! -d "/tmp/claude-sci-skills" ]]; then
    git clone --depth 1 https://github.com/K-Dense-AI/claude-scientific-skills.git /tmp/claude-sci-skills 2>/dev/null || true
fi
if [[ -d "/tmp/claude-sci-skills/scientific-skills" ]]; then
    for skill in pytorch-lightning scikit-learn matplotlib plotly pdf-gen xlsx-gen; do
        if [[ -d "/tmp/claude-sci-skills/scientific-skills/$skill" ]]; then
            cp -r "/tmp/claude-sci-skills/scientific-skills/$skill" "$CLAUDE_SKILLS_DIR/"
            echo "[experiment] Installed scientific skill: ${skill}"
        fi
    done
    rm -rf /tmp/claude-sci-skills
fi

# Step 9: Install exec approvals for system.run commands
echo "[experiment] Installing exec approvals..."
mkdir -p "${HOME}/.openclaw"
cp "${SCRIPT_DIR}/configs/exec-approvals.json" "${HOME}/.openclaw/exec-approvals.json"
echo "[experiment] Exec approvals installed to ~/.openclaw/exec-approvals.json"

# Step 10: Install OpenClaw node service via built-in command
echo "[experiment] Installing OpenClaw node service..."
openclaw node install --host "${LEADER_HOST}" --port "${LEADER_PORT}" --display-name "darklab-experiment" --force 2>/dev/null || \
    echo "[experiment] Warning: openclaw node install failed (install manually: openclaw node install --host ${LEADER_HOST} --port ${LEADER_PORT} --display-name darklab-experiment)"

# Generate node.json fallback
OPENCLAW_DIR="${HOME}/.openclaw"
if [[ ! -f "${OPENCLAW_DIR}/node.json" ]]; then
    cat > "${OPENCLAW_DIR}/node.json" << NJSON
{
  "version": 1,
  "nodeId": "darklab-experiment-$(hostname -s)",
  "displayName": "darklab-experiment",
  "gateway": {
    "host": "${LEADER_HOST}",
    "port": ${LEADER_PORT},
    "tls": false
  }
}
NJSON
    echo "[experiment] node.json written to ${OPENCLAW_DIR}/node.json"
fi
echo "[experiment] OpenClaw node service installed."

# Step 11: Summary
echo ""
echo "============================================"
echo "  EXPERIMENT AGENT INSTALLATION COMPLETE"
echo "============================================"
echo ""
echo "  Leader:       ${LEADER_HOST}:${LEADER_PORT}"
echo "  Config:       ${DARKLAB_HOME}/.env"
echo "  Python deps:  numpy, scipy, pandas, matplotlib, plotly, scikit-learn"
echo "  Logs:         ${DARKLAB_HOME}/logs/"
echo ""
echo "  Next steps:"
echo "  1. Start node:  openclaw node start"
echo "  2. Note the pairing code displayed"
echo "  3. On Leader, approve:  openclaw pairing approve darklab-experiment <CODE>"
echo ""
