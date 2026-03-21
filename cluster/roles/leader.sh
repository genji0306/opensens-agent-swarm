#!/bin/bash
set -euo pipefail
# Leader role installer
# Installs: OpenClaw gateway, Claude OPUS, Gemini CLI, NotebookLM browser profile

echo "[leader] Starting Leader installation..."
echo ""

# Step 1: Prerequisites
source "${SCRIPT_DIR}/common/prerequisites.sh"

# Step 2: OpenClaw
source "${SCRIPT_DIR}/common/openclaw-setup.sh"

# Step 3: Gemini CLI
echo "[leader] Setting up Gemini CLI..."
if ! command -v gemini &>/dev/null; then
    echo "[leader] Installing Gemini CLI..."
    brew install gemini-cli
    echo "[leader] Run 'gemini' once to complete OAuth login."
else
    echo "[leader] Gemini CLI: OK"
fi

# Step 4: Tailscale
source "${SCRIPT_DIR}/common/tailscale-setup.sh"

# Step 5: API Keys
echo ""
echo "[leader] Configuring API keys..."
ENV_FILE="${DARKLAB_HOME}/.env"

if [[ -f "$ENV_FILE" ]]; then
    echo "[leader] Existing .env found. Loading..."
    source "$ENV_FILE"
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    read -p "Anthropic API key (Claude OPUS): " ANTHROPIC_API_KEY
fi
if [[ -z "${GOOGLE_AI_API_KEY:-}" ]]; then
    read -p "Google AI API key (Gemini): " GOOGLE_AI_API_KEY
fi
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    read -p "Telegram Bot Token (from @BotFather): " TELEGRAM_BOT_TOKEN
fi

cat > "$ENV_FILE" << EOF
# DarkLab Leader Configuration
DARKLAB_ROLE=leader
DARKLAB_VERSION=${DARKLAB_VERSION}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
GOOGLE_AI_API_KEY=${GOOGLE_AI_API_KEY}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
GATEWAY_PORT=18789
EOF
chmod 600 "$ENV_FILE"
echo "[leader] API keys saved to ${ENV_FILE}"

# Step 6: Ed25519 keys
source "${SCRIPT_DIR}/common/python-env.sh" leader
source "${SCRIPT_DIR}/common/keys-setup.sh"

# Step 7: Install agent code
echo "[leader] Installing agent code..."
AGENTS_TARGET="${DARKLAB_HOME}/agents"
mkdir -p "${AGENTS_TARGET}"
cp -r "${SCRIPT_DIR}/agents/shared" "${AGENTS_TARGET}/"
cp -r "${SCRIPT_DIR}/agents/leader" "${AGENTS_TARGET}/"
echo "[leader] Agent code installed to ${AGENTS_TARGET}"

# Step 8: Install DarkLab skills
echo "[leader] Installing DarkLab skills..."
SKILLS_TARGET="${HOME}/.openclaw/skills"
mkdir -p "$SKILLS_TARGET"
for skill_dir in "${SCRIPT_DIR}/skills/darklab-leader" \
                 "${SCRIPT_DIR}/skills/darklab-synthesis" \
                 "${SCRIPT_DIR}/skills/darklab-media-gen" \
                 "${SCRIPT_DIR}/skills/darklab-notebooklm"; do
    if [[ -d "$skill_dir" ]]; then
        skill_name=$(basename "$skill_dir")
        cp -r "$skill_dir" "${SKILLS_TARGET}/${skill_name}"
        echo "[leader] Installed skill: ${skill_name}"
    fi
done

# Step 9: OpenClaw config
echo "[leader] Creating OpenClaw configuration..."
if [[ -f "${SCRIPT_DIR}/configs/leader.config.yaml" ]]; then
    mkdir -p "${HOME}/.openclaw"
    cp "${SCRIPT_DIR}/configs/leader.config.yaml" "${HOME}/.openclaw/config.yaml"
    echo "[leader] Config written to ~/.openclaw/config.yaml"
fi

# Step 10: Browser profile for NotebookLM
source "${SCRIPT_DIR}/common/browser-setup.sh" leader

# Step 11: Paperclip AI coordination layer
echo "[leader] Installing Paperclip AI coordination layer..."
PLIST_DIR="${HOME}/Library/LaunchAgents"
mkdir -p "$PLIST_DIR"
USERNAME=$(whoami)
PAPERCLIP_DIR="${DARKLAB_HOME}/paperclip"

if [[ ! -d "$PAPERCLIP_DIR" ]]; then
    git clone --depth 1 https://github.com/paperclipai/paperclip.git "$PAPERCLIP_DIR" 2>/dev/null || \
        echo "[leader] Warning: Could not clone Paperclip (check network)"
fi
if [[ -d "$PAPERCLIP_DIR" ]]; then
    echo "[leader] Building Paperclip..."
    cd "$PAPERCLIP_DIR" && pnpm install 2>/dev/null && pnpm build 2>/dev/null || \
        echo "[leader] Warning: Paperclip build failed (can be built manually later)"

    # Run onboarding
    npx paperclipai onboard --yes 2>/dev/null || \
        echo "[leader] Warning: Paperclip onboard skipped (run manually: cd ${PAPERCLIP_DIR} && npx paperclipai onboard --yes)"

    cd "${DARKLAB_HOME}"
    echo "[leader] Paperclip installed at ${PAPERCLIP_DIR}"

    # Determine node binary path
    NODE_BIN=$(which node 2>/dev/null || echo "/opt/homebrew/bin/node")

    # Create Paperclip LaunchAgent (port 3100, LAN-accessible)
    cat > "${PLIST_DIR}/com.opensens.darklab-paperclip.plist" << PPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.opensens.darklab-paperclip</string>
    <key>WorkingDirectory</key>
    <string>${PAPERCLIP_DIR}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${NODE_BIN}</string>
        <string>${PAPERCLIP_DIR}/server/dist/index.js</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOST</key>
        <string>0.0.0.0</string>
        <key>PORT</key>
        <string>3100</string>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/${USERNAME}</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${DARKLAB_HOME}/logs/paperclip.log</string>
    <key>StandardErrorPath</key>
    <string>${DARKLAB_HOME}/logs/paperclip.err</string>
</dict>
</plist>
PPLIST
    echo "[leader] Paperclip LaunchAgent created (start manually when ready)"
fi

# Add Paperclip URL to .env
echo "PAPERCLIP_URL=http://localhost:3100" >> "$ENV_FILE"

# Step 12: Install exec approvals for system.run commands
echo "[leader] Installing exec approvals..."
mkdir -p "${HOME}/.openclaw"
cp "${SCRIPT_DIR}/configs/exec-approvals.json" "${HOME}/.openclaw/exec-approvals.json"
echo "[leader] Exec approvals installed to ~/.openclaw/exec-approvals.json"

# Step 13: Install OpenClaw gateway service via built-in command
echo "[leader] Installing OpenClaw gateway service..."
openclaw gateway install --port 18789 --force 2>/dev/null || \
    echo "[leader] Warning: openclaw gateway install failed (install manually: openclaw gateway install --port 18789)"
openclaw config set gateway.bind lan 2>/dev/null || true
echo "[leader] OpenClaw gateway service installed."

# Step 14: Summary
echo ""
echo "============================================"
echo "  LEADER INSTALLATION COMPLETE"
echo "============================================"
echo ""
echo "  Gateway URL:  http://$(hostname).local:18789"
echo "  WebChat:      http://$(hostname).local:18789"
echo "  Dashboard:    http://$(hostname).local:3100"
echo "  Config:       ~/.openclaw/config.yaml"
echo "  API Keys:     ${DARKLAB_HOME}/.env"
echo "  Logs:         ${DARKLAB_HOME}/logs/"
echo ""
echo "  Next steps:"
echo "  1. Start gateway:  openclaw gateway start"
echo "  2. Start Paperclip: launchctl load ${PLIST_DIR}/com.opensens.darklab-paperclip.plist"
echo "  3. Run Academic and Experiment installers on other Macs"
echo "  4. Connect cluster: scripts/connect-cluster.sh"
echo ""
