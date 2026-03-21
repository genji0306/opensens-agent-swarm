#!/bin/bash
set -euo pipefail
# Boss role installer (MacBook — command & control)
# Lightweight: no OpenClaw gateway, no Python agents, no AI services
# Installs management scripts and configures dashboard access

echo "[boss] Starting Boss (Command & Control) installation..."
echo ""

# Step 1: Minimal prerequisites (Homebrew + Node.js + pnpm)
echo "[boss] Checking prerequisites..."

# Homebrew
if ! command -v brew &>/dev/null; then
    echo "[boss] Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [[ $(uname -m) == "arm64" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
else
    echo "[boss] Homebrew: OK"
fi

# Node.js (for OpenClaw CLI tools)
NODE_RAW=$(node --version 2>/dev/null || echo "v0.0.0")
NODE_MAJOR=$(echo "$NODE_RAW" | sed 's/v//' | cut -d. -f1)
NODE_MINOR=$(echo "$NODE_RAW" | sed 's/v//' | cut -d. -f2)
NEED_NODE_INSTALL=false
if [[ "$NODE_MAJOR" -lt 22 ]]; then
    NEED_NODE_INSTALL=true
elif [[ "$NODE_MAJOR" -eq 22 && "$NODE_MINOR" -lt 16 ]]; then
    NEED_NODE_INSTALL=true
fi
if [[ "$NEED_NODE_INSTALL" == "true" ]]; then
    echo "[boss] Installing Node.js >=22.16.0 (current: ${NODE_RAW})..."
    brew install node@22
    brew link --overwrite node@22
else
    echo "[boss] Node.js ${NODE_RAW}: OK"
fi

# pnpm (for potential Paperclip local dev)
if ! command -v pnpm &>/dev/null; then
    echo "[boss] Installing pnpm..."
    npm install -g pnpm
else
    echo "[boss] pnpm: OK"
fi

# Step 2: Tailscale (optional)
echo ""
echo "[boss] Tailscale (optional for remote access)..."
if command -v tailscale &>/dev/null; then
    echo "[boss] Tailscale: OK"
else
    read -p "Install Tailscale for remote access? [y/N]: " ts_confirm
    if [[ "$ts_confirm" =~ ^[Yy]$ ]]; then
        brew install tailscale
        echo "[boss] Tailscale installed. Run 'tailscale up' to connect."
    else
        echo "[boss] Skipping Tailscale."
    fi
fi

# Step 3: Discover Leader
echo ""
echo "[boss] Discovering Leader gateway..."
LEADER_HOST=""

# Try Bonjour/mDNS
echo "[boss] Searching via Bonjour (3 seconds)..."
BONJOUR_RESULT=$(dns-sd -B _openclaw-gw._tcp . 2>/dev/null & BGPID=$!; sleep 3; kill $BGPID 2>/dev/null; wait $BGPID 2>/dev/null) || true
if [[ -n "$BONJOUR_RESULT" ]]; then
    echo "[boss] Found Leader via Bonjour!"
    LEADER_HOST="leader.local"
fi

if [[ -z "$LEADER_HOST" ]]; then
    read -p "Leader hostname or IP (e.g., leader.local or 192.168.1.100): " LEADER_HOST
fi

LEADER_PORT="${LEADER_PORT:-18789}"

# Step 4: Save configuration
echo ""
echo "[boss] Saving configuration..."
ENV_FILE="${DARKLAB_HOME}/.env"

cat > "$ENV_FILE" << EOF
# DarkLab Boss (Command & Control) Configuration
DARKLAB_ROLE=boss
DARKLAB_VERSION=${DARKLAB_VERSION}
DARKLAB_LEADER=${LEADER_HOST}
DARKLAB_LEADER_HOST=${LEADER_HOST}
DARKLAB_LEADER_PORT=${LEADER_PORT}
DARKLAB_ACADEMIC=academic.local
DARKLAB_EXPERIMENT=experiment.local
PAPERCLIP_URL=http://${LEADER_HOST}:3100
EOF
chmod 600 "$ENV_FILE"
echo "[boss] Configuration saved to ${ENV_FILE}"

# Step 5: SSH key setup
echo ""
echo "[boss] Checking SSH keys..."
if [[ ! -f "${HOME}/.ssh/id_ed25519" ]]; then
    echo "[boss] No Ed25519 SSH key found. Generating..."
    ssh-keygen -t ed25519 -f "${HOME}/.ssh/id_ed25519" -N "" -C "darklab-boss@$(hostname -s)"
    echo "[boss] SSH key generated."
    echo ""
    echo "  Copy this key to each Mac mini:"
    echo "    ssh-copy-id ${LEADER_HOST}"
    echo "    ssh-copy-id academic.local"
    echo "    ssh-copy-id experiment.local"
else
    echo "[boss] SSH key exists: ~/.ssh/id_ed25519"
fi

# Step 6: Copy management scripts
echo ""
echo "[boss] Installing management scripts..."
SCRIPTS_DIR="${DARKLAB_HOME}/scripts"
mkdir -p "$SCRIPTS_DIR"

for script in cluster-status.sh update-cluster.sh connect-cluster.sh test-connectivity.sh \
              verify-cluster.sh backup-cluster.sh seed-paperclip.sh; do
    if [[ -f "${SCRIPT_DIR}/scripts/${script}" ]]; then
        cp "${SCRIPT_DIR}/scripts/${script}" "${SCRIPTS_DIR}/${script}"
        chmod +x "${SCRIPTS_DIR}/${script}"
        echo "[boss] Installed: ${script}"
    fi
done

# Step 7: Create shell aliases
echo ""
echo "[boss] Creating shell aliases..."
ALIAS_FILE="${DARKLAB_HOME}/aliases.sh"
cat > "$ALIAS_FILE" << 'ALIASES'
# DarkLab Boss aliases — source from ~/.zshrc or ~/.bashrc
alias darklab-status='~/.darklab/scripts/cluster-status.sh'
alias darklab-update='~/.darklab/scripts/update-cluster.sh'
alias darklab-connect='~/.darklab/scripts/connect-cluster.sh'
alias darklab-test='~/.darklab/scripts/test-connectivity.sh'
alias darklab-verify='~/.darklab/scripts/verify-cluster.sh'
alias darklab-seed='~/.darklab/scripts/seed-paperclip.sh'
ALIASES

# Add Paperclip dashboard alias using the actual leader host
cat >> "$ALIAS_FILE" << EOF
alias darklab-dashboard='open http://${LEADER_HOST}:3100'
alias darklab-webchat='open http://${LEADER_HOST}:18789'
EOF

# Source aliases in shell profile
SHELL_RC="${HOME}/.zshrc"
[[ ! -f "$SHELL_RC" ]] && SHELL_RC="${HOME}/.bashrc"
if ! grep -q "darklab/aliases.sh" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# DarkLab Boss aliases" >> "$SHELL_RC"
    echo "[ -f ~/.darklab/aliases.sh ] && source ~/.darklab/aliases.sh" >> "$SHELL_RC"
    echo "[boss] Aliases added to ${SHELL_RC}"
else
    echo "[boss] Aliases already in ${SHELL_RC}"
fi

# Step 8: Summary
echo ""
echo "============================================"
echo "  BOSS INSTALLATION COMPLETE"
echo "============================================"
echo ""
echo "  Leader:      ${LEADER_HOST}:${LEADER_PORT}"
echo "  Dashboard:   http://${LEADER_HOST}:3100"
echo "  WebChat:     http://${LEADER_HOST}:18789"
echo "  Config:      ${DARKLAB_HOME}/.env"
echo "  Scripts:     ${DARKLAB_HOME}/scripts/"
echo ""
echo "  Quick commands (after restarting shell):"
echo "    darklab-status      Check cluster health"
echo "    darklab-dashboard   Open Paperclip dashboard"
echo "    darklab-webchat     Open OpenClaw webchat"
echo "    darklab-connect     Connect cluster devices"
echo "    darklab-test        Test connectivity"
echo ""
echo "  Next steps:"
echo "  1. Copy SSH key to Mac minis:  ssh-copy-id ${LEADER_HOST}"
echo "  2. Verify cluster:  source ~/.darklab/aliases.sh && darklab-status"
echo "  3. Open dashboard:  open http://${LEADER_HOST}:3100"
echo ""
