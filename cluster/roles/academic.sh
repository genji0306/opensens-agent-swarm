#!/bin/bash
set -euo pipefail
# Academic Agent role installer
# Installs: OpenClaw node-host, research tools, browser profiles

echo "[academic] Starting Academic Agent installation..."
echo ""

# Step 1: Prerequisites
source "${SCRIPT_DIR}/common/prerequisites.sh"

# Step 2: OpenClaw
source "${SCRIPT_DIR}/common/openclaw-setup.sh"

# Step 3: Gemini CLI
echo "[academic] Setting up Gemini CLI..."
if ! command -v gemini &>/dev/null; then
    echo "[academic] Installing Gemini CLI..."
    brew install gemini-cli
    echo "[academic] Run 'gemini' once to complete OAuth login."
else
    echo "[academic] Gemini CLI: OK"
fi

# Step 4: Tailscale
source "${SCRIPT_DIR}/common/tailscale-setup.sh"

# Step 5: API Keys
echo ""
echo "[academic] Configuring API keys..."
ENV_FILE="${DARKLAB_HOME}/.env"

if [[ -f "$ENV_FILE" ]]; then
    echo "[academic] Existing .env found. Loading..."
    source "$ENV_FILE"
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    read -p "Anthropic API key (Claude): " ANTHROPIC_API_KEY
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    read -p "OpenAI API key (GPT-4o): " OPENAI_API_KEY
fi
if [[ -z "${GOOGLE_AI_API_KEY:-}" ]]; then
    read -p "Google AI API key (Gemini): " GOOGLE_AI_API_KEY
fi
read -p "Perplexity API key (optional, press Enter to skip): " PERPLEXITY_API_KEY

# Discover Leader
echo ""
echo "[academic] Discovering Leader gateway..."
LEADER_HOST=""

# Try Bonjour/mDNS first
echo "[academic] Searching for Leader via Bonjour..."
BONJOUR_RESULT=$(dns-sd -B _openclaw._tcp . 2>/dev/null & BGPID=$!; sleep 3; kill $BGPID 2>/dev/null; wait $BGPID 2>/dev/null) || true
if [[ -n "$BONJOUR_RESULT" ]]; then
    echo "[academic] Found Leader via Bonjour!"
    LEADER_HOST="leader.local"
fi

if [[ -z "$LEADER_HOST" ]]; then
    read -p "Leader hostname or IP (e.g., leader.local or 192.168.1.100): " LEADER_HOST
fi

LEADER_PORT="${LEADER_PORT:-18789}"

cat > "$ENV_FILE" << EOF
# DarkLab Academic Agent Configuration
DARKLAB_ROLE=academic
DARKLAB_VERSION=${DARKLAB_VERSION}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
OPENAI_API_KEY=${OPENAI_API_KEY}
GOOGLE_AI_API_KEY=${GOOGLE_AI_API_KEY}
PERPLEXITY_API_KEY=${PERPLEXITY_API_KEY:-}
DARKLAB_LEADER_HOST=${LEADER_HOST}
DARKLAB_LEADER_PORT=${LEADER_PORT}
EOF
chmod 600 "$ENV_FILE"
echo "[academic] Configuration saved to ${ENV_FILE}"

# Step 6: Python environment + keys
source "${SCRIPT_DIR}/common/python-env.sh" academic
source "${SCRIPT_DIR}/common/keys-setup.sh"

# Step 7: Copy Python agent code
echo "[academic] Installing Python agent code..."
AGENTS_TARGET="${DARKLAB_HOME}/agents"
mkdir -p "$AGENTS_TARGET"
cp -r "${SCRIPT_DIR}/agents/shared" "${AGENTS_TARGET}/"
cp -r "${SCRIPT_DIR}/agents/academic" "${AGENTS_TARGET}/"
echo "[academic] Agent code installed to ${AGENTS_TARGET}"

# Step 8: Install DarkLab skills
echo "[academic] Installing DarkLab skills..."
SKILLS_TARGET="${HOME}/.openclaw/skills"
mkdir -p "$SKILLS_TARGET"
for skill_dir in "${SCRIPT_DIR}/skills/darklab-research" \
                 "${SCRIPT_DIR}/skills/darklab-literature" \
                 "${SCRIPT_DIR}/skills/darklab-doe" \
                 "${SCRIPT_DIR}/skills/darklab-paper" \
                 "${SCRIPT_DIR}/skills/darklab-perplexity"; do
    if [[ -d "$skill_dir" ]]; then
        skill_name=$(basename "$skill_dir")
        cp -r "$skill_dir" "${SKILLS_TARGET}/${skill_name}"
        echo "[academic] Installed skill: ${skill_name}"
    fi
done

# Step 9: Install Claude Scientific Skills (K-Dense-AI)
echo "[academic] Installing Claude Scientific Skills..."
CLAUDE_SKILLS_DIR="${HOME}/.claude/skills"
mkdir -p "$CLAUDE_SKILLS_DIR"
if [[ ! -d "/tmp/claude-sci-skills" ]]; then
    git clone --depth 1 https://github.com/K-Dense-AI/claude-scientific-skills.git /tmp/claude-sci-skills 2>/dev/null || \
        echo "[academic] Warning: Could not clone claude-scientific-skills (check network)"
fi
if [[ -d "/tmp/claude-sci-skills/scientific-skills" ]]; then
    for skill in pubmed-database arxiv-database biorxiv-database perplexity-search \
                 scientific-writing citation-management matplotlib plotly \
                 pdf-gen xlsx-gen pptx-gen docx-gen; do
        if [[ -d "/tmp/claude-sci-skills/scientific-skills/$skill" ]]; then
            cp -r "/tmp/claude-sci-skills/scientific-skills/$skill" "$CLAUDE_SKILLS_DIR/"
            echo "[academic] Installed scientific skill: ${skill}"
        fi
    done
    rm -rf /tmp/claude-sci-skills
    echo "[academic] Claude Scientific Skills installed to ${CLAUDE_SKILLS_DIR}"
else
    echo "[academic] Skipping scientific skills (clone failed)"
fi

# Step 10: Browser profiles
source "${SCRIPT_DIR}/common/browser-setup.sh" academic

# Step 11: Install exec approvals for system.run commands
echo "[academic] Installing exec approvals..."
mkdir -p "${HOME}/.openclaw"
cp "${SCRIPT_DIR}/configs/exec-approvals.json" "${HOME}/.openclaw/exec-approvals.json"
echo "[academic] Exec approvals installed to ~/.openclaw/exec-approvals.json"

# Step 12: Install OpenClaw node service via built-in command
echo "[academic] Installing OpenClaw node service..."
openclaw node install --host "${LEADER_HOST}" --port "${LEADER_PORT}" --display-name "darklab-academic" --force 2>/dev/null || \
    echo "[academic] Warning: openclaw node install failed (install manually: openclaw node install --host ${LEADER_HOST} --port ${LEADER_PORT} --display-name darklab-academic)"

# Generate node.json fallback
OPENCLAW_DIR="${HOME}/.openclaw"
if [[ ! -f "${OPENCLAW_DIR}/node.json" ]]; then
    cat > "${OPENCLAW_DIR}/node.json" << NJSON
{
  "version": 1,
  "nodeId": "darklab-academic-$(hostname -s)",
  "displayName": "darklab-academic",
  "gateway": {
    "host": "${LEADER_HOST}",
    "port": ${LEADER_PORT},
    "tls": false
  }
}
NJSON
    echo "[academic] node.json written to ${OPENCLAW_DIR}/node.json"
fi
echo "[academic] OpenClaw node service installed."

# Step 13: Summary
echo ""
echo "============================================"
echo "  ACADEMIC AGENT INSTALLATION COMPLETE"
echo "============================================"
echo ""
echo "  Leader:       ${LEADER_HOST}:${LEADER_PORT}"
echo "  Config:       ${DARKLAB_HOME}/.env"
echo "  Logs:         ${DARKLAB_HOME}/logs/"
echo ""
echo "  Next steps:"
echo "  1. Start node:  openclaw node start"
echo "  2. Note the pairing code displayed"
echo "  3. On Leader, approve:  openclaw pairing approve darklab-academic <CODE>"
echo "  4. Set up browser profiles (see instructions above)"
echo ""
