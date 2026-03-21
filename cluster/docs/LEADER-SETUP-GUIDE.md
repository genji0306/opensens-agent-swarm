# DarkLab Leader Mac Mini — Setup Guide

> Mac mini 16 GB (192.168.23.25) — Leader role
> Covers: Paperclip dashboard, OpenClaw Office virtual office, Claude Code remote control, and full deployment

---

## Table of Contents

1. [Current State](#1-current-state)
2. [Part A — Paperclip Dashboard](#2-part-a--paperclip-dashboard)
3. [Part B — OpenClaw Office (Virtual Office)](#3-part-b--openclaw-office-virtual-office)
4. [Part C — Connecting Everything](#4-part-c--connecting-everything)
5. [Part D — Claude Code Remote Control](#5-part-d--claude-code-remote-control)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Current State

**What's already running on Mac mini 16:**

| Service | Status | Port | Type |
|---------|--------|------|------|
| OpenClaw Gateway | Running | 18789 | Native (launchd) |
| Docker stack (PicoClaw + LiteLLM + DarkLab Leader + Caddy + Liaison Broker + Redis + Cloudflared) | Running | various | Docker Compose |
| DarkLab Leader Agent | Running (healthy) | 8100 | Docker container |
| Dozzle (log viewer) | Running | 8081 | Docker container |

**What's NOT installed yet:**

| Service | Port | Status |
|---------|------|--------|
| Paperclip AI | 3100 | Not installed |
| OpenClaw Office | 5180 | Not installed |

**System info:**
- Node.js v25.8.0 (Homebrew)
- npm 11.11.0
- pnpm: NOT installed (required)
- Homebrew: installed at /opt/homebrew
- Disk: 102 GB free
- RAM: 16 GB

---

## 2. Part A — Paperclip Dashboard

### What is Paperclip?

Paperclip AI is an open-source orchestration governance platform. For DarkLab, it provides:
- **Org chart** — hierarchy of agents (Boss → Leader → Academic/Experiment)
- **Budget enforcement** — daily spending limits per agent ($50/$30/$20)
- **Task coordination** — heartbeat-driven task dispatch and results tracking
- **Dashboard UI** — real-time agent status and budget overview at port 3100

Paperclip runs natively on macOS (not Docker) using PGlite (embedded PostgreSQL).

### Step 1: Install pnpm

SSH into the Mac mini and install pnpm:

```bash
ssh "cyber 02@192.168.23.25"
# Password: Opensens26

# Install pnpm globally
npm install -g pnpm
```

Verify:
```bash
pnpm --version
```

### Step 2: Clone and build Paperclip

```bash
export DARKLAB_HOME="${HOME}/.darklab"

# Clone Paperclip into the darklab home directory
git clone --depth 1 https://github.com/paperclipai/paperclip.git "${DARKLAB_HOME}/paperclip"

# Build
cd "${DARKLAB_HOME}/paperclip"
pnpm install
pnpm build

# Run onboarding (initializes PGlite database)
npx paperclipai onboard --yes
```

### Step 3: Create the LaunchAgent (auto-start daemon)

This creates a macOS service that keeps Paperclip running on port 3100:

```bash
NODE_BIN=$(which node)
PAPERCLIP_DIR="${HOME}/.darklab/paperclip"
PLIST_DIR="${HOME}/Library/LaunchAgents"
USERNAME=$(whoami)

cat > "${PLIST_DIR}/com.opensens.darklab-paperclip.plist" << PLIST
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
    <string>${HOME}/.darklab/logs/paperclip.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/.darklab/logs/paperclip.err</string>
</dict>
</plist>
PLIST
```

### Step 4: Start Paperclip

```bash
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist
```

Verify it's running:
```bash
curl -s http://localhost:3100
# Should return HTML or a redirect (HTTP 200/302)
```

### Step 5: Seed the org chart

The seed script creates the 4 DarkLab agents with their budgets:

```bash
cd ~/darklab/darklab-installer
bash scripts/seed-paperclip.sh
```

This creates:

| Agent | Role | Budget |
|-------|------|--------|
| Boss | CEO (human) | $0/day |
| DarkLab Leader | CTO | $50/day |
| DarkLab Academic | Research Director | $30/day |
| DarkLab Experiment | Lab Director | $20/day |

### Step 6: Install the OpenClaw adapter config

```bash
cp configs/paperclip-openclaw-adapter.json ~/.darklab/paperclip/openclaw-adapter.json
```

This connects Paperclip to the OpenClaw Gateway via WebSocket for agent coordination.

### Step 7: Access the Paperclip dashboard

From any device on the same LAN:

```
http://192.168.23.25:3100
```

Or from the Mac mini itself:
```
http://localhost:3100
```

### Checking Paperclip status

```bash
# Check if the service is loaded
launchctl list | grep paperclip

# Check if port 3100 is listening
lsof -i :3100

# Check logs
tail -50 ~/.darklab/logs/paperclip.log
tail -50 ~/.darklab/logs/paperclip.err

# Restart if needed
launchctl unload ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist
```

### Quick check script (run anytime)

```bash
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3100 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]] || [[ "$HTTP_CODE" == "302" ]]; then
    echo "Paperclip: RUNNING (HTTP ${HTTP_CODE})"
    echo "Dashboard: http://$(hostname).local:3100"
else
    echo "Paperclip: NOT RUNNING (HTTP ${HTTP_CODE})"
    echo "Start it: launchctl load ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist"
fi
```

---

## 3. Part B — OpenClaw Office (Virtual Office)

### What is OpenClaw Office?

OpenClaw Office is a visual monitoring and management frontend for OpenClaw. It renders agent work status, collaboration links, tool calls, and resource consumption through an isometric virtual office scene, plus a full system management console.

**Features:**
- 2D SVG floor plan with agent avatars, desks, furniture, status animations
- 3D React Three Fiber scene with character models and hologram effects
- Real-time agent status: idle, working, speaking, tool calling, error
- Collaboration lines showing inter-agent messaging
- Chat bar for real-time conversations with agents
- Console pages: Dashboard, Agents, Channels, Skills, Cron, Settings

**Connection:** WebSocket to OpenClaw Gateway (already running on port 18789)

### Option 1: Quick install (NPM global — recommended for production)

```bash
ssh "cyber 02@192.168.23.25"
# Password: Opensens26

export PATH=/opt/homebrew/bin:$PATH

# Install globally
npm install -g @ww-ai-lab/openclaw-office

# Run it (auto-detects Gateway token from ~/.openclaw/openclaw.json)
openclaw-office --port 5180 --host 0.0.0.0
```

Output should look like:
```
🏢 OpenClaw Office
➡️  Local:   http://localhost:5180
➡️  Network: http://192.168.23.25:5180
➡️  Gateway: ws://localhost:18789 (from ~/.openclaw/openclaw.json)
✓  Token:   loaded
```

### Option 2: Install from source (for development)

```bash
ssh "cyber 02@192.168.23.25"
export PATH=/opt/homebrew/bin:$PATH

# Install pnpm if not done yet
npm install -g pnpm

# Clone or copy the project
cd ~/darklab
cp -r darklab-installer/"Agent office" openclaw-office
cd openclaw-office

# Install dependencies
pnpm install

# Configure Gateway connection
cat > .env.local << 'EOF'
VITE_GATEWAY_TOKEN=$(openclaw config get gateway.auth.token 2>/dev/null)
EOF
```

For development with hot reload:
```bash
pnpm dev
```

For production build:
```bash
pnpm build
node bin/openclaw-office.js --port 5180 --host 0.0.0.0
```

### Step: Enable device auth bypass

OpenClaw Office is a web app that cannot provide Ed25519 device identity signatures. The Gateway requires a bypass:

```bash
openclaw config set gateway.controlUi.dangerouslyDisableDeviceAuth true
```

**Restart the Gateway after this:**
```bash
openclaw gateway stop
openclaw gateway start
```

### Step: Create a LaunchAgent for OpenClaw Office

To keep it running as a background service:

```bash
NODE_BIN=$(which node)
OFFICE_BIN=$(which openclaw-office 2>/dev/null || echo "${HOME}/.npm-global/bin/openclaw-office")
# If installed globally via npm, find the actual path:
OFFICE_BIN=$(npm root -g)/@ww-ai-lab/openclaw-office/bin/openclaw-office.js

cat > ~/Library/LaunchAgents/com.opensens.darklab-office.plist << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.opensens.darklab-office</string>
    <key>ProgramArguments</key>
    <array>
        <string>${NODE_BIN}</string>
        <string>${OFFICE_BIN}</string>
        <string>--port</string>
        <string>5180</string>
        <string>--host</string>
        <string>0.0.0.0</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/$(whoami)</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${HOME}/.darklab/logs/office.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/.darklab/logs/office.err</string>
</dict>
</plist>
PLIST

# Start the service
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-office.plist
```

### Accessing the Virtual Office

From any device on the LAN:

```
http://192.168.23.25:5180
```

**First launch flow:**
1. OpenClaw Office shows a Connection Setup Dialog
2. Choose "Local Gateway" (default — connects to ws://localhost:18789)
3. Token is auto-detected from `~/.openclaw/openclaw.json`
4. The office scene loads showing all registered agents

**Navigation:**
| Route | View |
|-------|------|
| `/` | Virtual office (2D floor plan / 3D scene) |
| `/dashboard` | System overview with stats and alerts |
| `/agents` | Agent list, create/delete, detail tabs |
| `/channels` | Channel configuration (Telegram, WhatsApp) |
| `/skills` | Skill marketplace |
| `/cron` | Scheduled task management |
| `/settings` | Provider management, appearance, Gateway config |

### Mock mode (for testing without Gateway)

If you want to test the UI without a running Gateway:

```bash
VITE_MOCK=true pnpm dev
```

This uses simulated agent data.

### Development workflow

```bash
cd ~/darklab/openclaw-office

pnpm dev              # Start dev server with HMR (port 5180)
pnpm build            # Production build (outputs to dist/)
pnpm test             # Run Vitest test suite
pnpm typecheck        # TypeScript strict mode check
pnpm lint             # Oxlint code quality check
```

**Architecture (data flow):**
```
OpenClaw Gateway ──WebSocket──> ws-client.ts ──> event-parser.ts ──> Zustand Store ──> React Components
     │                                                                     │
     └── RPC (agents.list, chat.send, ...) ──> rpc-client.ts ───────────>──┘
```

---

## 4. Part C — Connecting Everything

### Final architecture on Mac mini 16

```
Mac mini 16 (Leader, 192.168.23.25)
│
├── Docker Compose Stack
│   ├── redis (7-alpine)
│   ├── litellm (:4000) — LLM proxy with model routing
│   ├── picoclaw — general Telegram AI tasks
│   ├── picoclaw-exec — sandboxed task runner
│   ├── darklab-leader (:8100) — scientific commands
│   ├── liaison-broker (:8000) — Telegram webhook routing
│   ├── caddy (:80) — static file server
│   ├── cloudflared — Cloudflare tunnel
│   └── dozzle (:8081) — log viewer
│
├── Native Services (macOS LaunchAgents)
│   ├── OpenClaw Gateway (:18789) — agent orchestration
│   ├── Paperclip AI (:3100) — governance dashboard
│   ├── OpenClaw Office (:5180) — virtual office UI
│   └── Claude Code Remote (:—) — CLI + remote control via Anthropic relay
│
└── Data
    └── ~/.darklab/
        ├── .env (API keys)
        ├── logs/ (audit, budget, paperclip)
        ├── artifacts/ (synthesis, .docx, .pptx)
        ├── keys/ (Ed25519 signing keys)
        └── paperclip/ (Paperclip installation)
```

### Access URLs from Boss MacBook

| Service | URL | Purpose |
|---------|-----|---------|
| OpenClaw Office | http://192.168.23.25:5180 | Virtual office + console |
| Paperclip Dashboard | http://192.168.23.25:3100 | Budget & org chart |
| DarkLab Leader API | http://192.168.23.25:8100/health | Leader health check |
| Dozzle Logs | http://192.168.23.25:8081 | Docker container logs |
| OpenClaw Gateway | ws://192.168.23.25:18789 | WebSocket (internal) |
| Claude Code Remote | via Claude iOS app | Remote CLI control |

### Verify everything is running

Run this check from the Mac mini:

```bash
echo "=== Service Health Check ==="
echo ""

# OpenClaw Gateway
GW=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18789/health 2>/dev/null)
echo "OpenClaw Gateway (:18789): $([ "$GW" = "200" ] && echo 'OK' || echo 'DOWN')"

# Paperclip
PC=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3100 2>/dev/null)
echo "Paperclip AI (:3100):     $([ "$PC" = "200" ] || [ "$PC" = "302" ] && echo 'OK' || echo 'DOWN')"

# OpenClaw Office
OO=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5180 2>/dev/null)
echo "OpenClaw Office (:5180):  $([ "$OO" = "200" ] && echo 'OK' || echo 'DOWN')"

# DarkLab Leader
DL=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8100/health 2>/dev/null)
echo "DarkLab Leader (:8100):   $([ "$DL" = "200" ] && echo 'OK' || echo 'DOWN')"

# Docker containers
export PATH=/Applications/Docker.app/Contents/Resources/bin:$PATH
echo ""
echo "=== Docker Containers ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### Complete install sequence (fresh setup)

If starting from scratch on the Mac mini:

```bash
export PATH=/opt/homebrew/bin:$PATH

# 1. Install pnpm
npm install -g pnpm

# 2. Install Paperclip
git clone --depth 1 https://github.com/paperclipai/paperclip.git ~/.darklab/paperclip
cd ~/.darklab/paperclip && pnpm install && pnpm build
npx paperclipai onboard --yes
# (Create LaunchAgent as shown in Part A Step 3)
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist

# 3. Seed org chart (wait ~5s for Paperclip to start)
sleep 5
cd ~/darklab/darklab-installer && bash scripts/seed-paperclip.sh

# 4. Enable device auth bypass for web clients
openclaw config set gateway.controlUi.dangerouslyDisableDeviceAuth true
openclaw gateway stop && openclaw gateway start

# 5. Install OpenClaw Office
npm install -g @ww-ai-lab/openclaw-office
# (Create LaunchAgent as shown in Part B)
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-office.plist

# 6. Verify
curl -s http://localhost:3100 && echo "Paperclip: OK"
curl -s http://localhost:5180 && echo "Office: OK"
curl -s http://localhost:8100/health | python3 -m json.tool
```

---

## 5. Part D — Claude Code Remote Control

### What is Claude Code Remote Control?

Claude Code is Anthropic's official CLI tool that gives Claude full access to the local filesystem, shell, and Docker stack. **Remote Control** lets you drive a Claude Code session running on the Mac mini from the **Claude iOS app** on your iPhone — no VPN, no port forwarding, no SSH tunnel.

This creates a second independent AI control channel:

```
Channel 1: iPhone (Telegram)  →  Liaison Broker  →  PicoClaw (general tasks)
                                                 →  DarkLab Leader :8100 (scientific commands)

Channel 2: iPhone (Claude iOS) →  Anthropic Relay  →  Claude Code CLI on Mac mini
                                                        └── ~/darklab/ workspace
                                                        └── Docker stack control
                                                        └── Full filesystem access
```

Both channels run independently. No conflicts.

### How Remote Control works

- Claude Code runs on the Mac mini and polls Anthropic's API over HTTPS (outbound only)
- No inbound ports are opened — everything goes through Anthropic's relay
- The Claude iOS app connects to the same Anthropic account
- All traffic is TLS-encrypted with short-lived, scoped credentials
- Survives network interruptions (auto-reconnects when WiFi drops)

### Prerequisites

- **Claude Code CLI v2.1.51+** — installed at `~/.local/bin/claude` (v2.1.77 on this machine)
- **claude.ai subscription** — Pro, Max, Team, or Enterprise (API key alone is NOT enough)
- **Claude iOS app** — download from the App Store
- **Internet** — the Mac mini must have outbound HTTPS access

### Step 1: Ensure PATH and API key are set

These should already be in `~/.zshrc`:

```bash
# Verify on Mac mini
ssh "cyber 02@192.168.23.25"
# Password: Opensens26

claude --version
# Expected: 2.1.77 (or later)

echo $ANTHROPIC_API_KEY
# Expected: sk-ant-api03-... (non-empty)
```

If missing, add to `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
export ANTHROPIC_API_KEY="<your-key-from-~/darklab/.env>"
```

### Step 2: Log in with your claude.ai account

Remote Control requires a claude.ai subscription login (not just API key).

```bash
# Start Claude Code interactively
cd ~/darklab
claude
```

Inside the Claude Code session:
```
/login
```

This opens a browser-based OAuth flow. Follow the prompts to sign in with your claude.ai account (the one with a Pro/Max subscription).

After login, verify:
```
/remote-control
```

If it shows a session URL and QR code, you're authenticated for remote control.

> **Note:** If the Mac mini has no display/browser, use the device code shown in the terminal to authenticate from another device at the URL provided.

### Step 3: Start Remote Control

There are three ways to enable remote control:

#### Option A: Dedicated server mode (recommended for always-on)

```bash
cd ~/darklab
claude remote-control --name "DarkLab Leader"
```

This starts Claude Code in server mode — it only accepts remote connections (no local interactive terminal). Supports multiple concurrent sessions.

Flags:
- `--name "DarkLab Leader"` — session label visible in the Claude iOS app
- `--capacity 4` — max concurrent remote sessions (default: 32)
- `--verbose` — show detailed connection logs

#### Option B: Interactive session with remote access

```bash
cd ~/darklab
claude --rc
```

This starts a normal interactive Claude Code session AND enables remote access. You can use it locally while also accepting remote connections from iOS.

#### Option C: Enable remote from an existing session

If Claude Code is already running interactively:
```
/rc
```

Or with a custom name:
```
/remote-control DarkLab Leader
```

### Step 4: Connect from Claude iOS app

1. **On the Mac mini terminal**, after starting remote control, you'll see:
   - A session URL (e.g., `https://claude.ai/code/session/...`)
   - Press **spacebar** to display a **QR code**

2. **On your iPhone**:
   - Open the Claude iOS app
   - Scan the QR code, OR
   - Navigate to the session URL, OR
   - Find the session by name in the remote sessions list (green dot = online)

3. Start typing prompts in the Claude iOS app — they execute on the Mac mini with full access to `~/darklab/`, Docker, and all local tools.

### Step 5: Keep it running (persistent session)

Since the Mac mini has `screen` available (tmux is NOT installed):

```bash
# Create a detachable screen session
screen -S claude-leader

# Inside the screen session:
cd ~/darklab
claude remote-control --name "DarkLab Leader"

# Detach: press Ctrl+A, then D
# The session continues running in background
```

Reattach later:
```bash
screen -r claude-leader
```

#### Option: LaunchAgent for auto-start on boot

Create `~/Library/LaunchAgents/com.opensens.darklab-claude-code.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.opensens.darklab-claude-code</string>
    <key>WorkingDirectory</key>
    <string>/Users/cyber02/darklab</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/cyber02/.local/bin/claude</string>
        <string>remote-control</string>
        <string>--name</string>
        <string>DarkLab Leader</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Users/cyber02/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/cyber02</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/Users/cyber02/.darklab/logs/claude-code.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/cyber02/.darklab/logs/claude-code.err</string>
</dict>
</plist>
```

Load it:
```bash
mkdir -p ~/.darklab/logs
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-claude-code.plist
```

### Step 6: CLAUDE.md workspace context

A `CLAUDE.md` file at `~/darklab/CLAUDE.md` provides Claude Code with full context about the DarkLab stack (already deployed). It includes:

- Architecture overview (all Docker services, ports, native services)
- Docker commands (with PATH note for `/Applications/Docker.app/Contents/Resources/bin`)
- DarkLab Leader API at :8100 (dispatch, synthesize endpoints)
- LiteLLM model aliases (search, plan, synthesis, dispatch, media)
- Key file paths (`~/darklab/`, `~/.darklab/`, `~/.openclaw/`)
- Environment variables in `.env`
- SSH username note (`cyber 02` — has a space)
- Safety warnings (don't run `docker compose down`, don't modify `.env`)

### Verification

```bash
# 1. Claude Code works
claude --version
# → 2.1.77

# 2. Remote control starts
claude remote-control --name "Test" &
# → Should show session URL (kill with: fg, then Ctrl+C)

# 3. Claude iOS app sees the session
# Open Claude app → look for "DarkLab Leader" session with green dot

# 4. Send a test prompt from iOS
# Type: "Run docker ps and show me what containers are running"
# → Should return container list from the Mac mini

# 5. PicoClaw still works (unchanged)
# Send a Telegram message to the bot → still responds

# 6. DarkLab Leader still healthy
curl http://localhost:8100/health
# → {"status": "healthy", ...}
```

### Switching between channels

| Task | Use |
|------|-----|
| Quick question, general task | Telegram → PicoClaw |
| Scientific synthesis, literature review, DOE | Telegram → DarkLab Leader (`/synthesize`, `/research`, etc.) |
| File editing, Docker ops, debugging, code changes | Claude iOS → Claude Code Remote |
| Complex multi-step local tasks on Mac mini | Claude iOS → Claude Code Remote |

Claude Code Remote is the power-user channel — use it when you need Claude to directly interact with the Mac mini's filesystem, edit configs, restart containers, or run scripts.

### Troubleshooting (Remote Control)

**"You must be logged in to use Remote Control"**
```bash
claude
# Inside session:
/login
# Follow OAuth flow to sign in with claude.ai subscription account
```

**Session not visible on iOS app**
- Ensure Mac mini has internet (outbound HTTPS)
- Ensure Claude Code and iOS app use the same Anthropic account
- Check `claude remote-control --verbose` for connection errors
- Try restarting: `Ctrl+C` then `claude remote-control --name "DarkLab Leader"`

**Session disconnects frequently**
- Claude Code auto-reconnects after brief network drops
- Extended outage (10+ min) causes timeout — restart the session
- If using `screen`, verify the screen session is still alive: `screen -ls`

**Claude Code can't find Docker**
- Docker CLI needs explicit PATH. The `~/darklab/CLAUDE.md` instructs Claude about this
- If running in LaunchAgent, ensure PATH includes `/Applications/Docker.app/Contents/Resources/bin`

---

## 6. Troubleshooting

### Paperclip won't start

```bash
# Check logs
tail -100 ~/.darklab/logs/paperclip.err

# Common issues:
# - Port 3100 already in use: lsof -i :3100
# - Node not found in PATH: ensure LaunchAgent has /opt/homebrew/bin in PATH
# - Database not initialized: cd ~/.darklab/paperclip && npx paperclipai onboard --yes
```

### OpenClaw Office shows "Connection Failed"

```bash
# 1. Verify Gateway is running
curl http://localhost:18789/health

# 2. Check device auth bypass is enabled
openclaw config get gateway.controlUi.dangerouslyDisableDeviceAuth
# Should be: true

# 3. Check token is accessible
openclaw config get gateway.auth.token
# Should return a non-empty string

# 4. Restart Gateway after config changes
openclaw gateway stop && openclaw gateway start
```

### OpenClaw Office 3D scene doesn't load

- 3D requires WebGL support in the browser
- On mobile or low-end devices, Office auto-falls back to 2D mode
- You can toggle 2D/3D manually in the office view

### DarkLab Leader container unhealthy

```bash
export PATH=/Applications/Docker.app/Contents/Resources/bin:$PATH

# Check container logs
docker logs darklab-darklab-leader-1 --tail 50

# Restart just the leader
cd ~/darklab && docker compose restart darklab-leader

# Rebuild if code changed
cd ~/darklab && docker compose up --build -d darklab-leader
```

### Memory considerations (16 GB Mac mini)

Running everything simultaneously uses approximately:
- Docker Desktop: ~2-3 GB
- OpenClaw Gateway: ~200 MB
- Paperclip + PGlite: ~150 MB
- OpenClaw Office: ~100 MB
- Total overhead: ~3-4 GB, leaving 12+ GB for containers and tasks

This is well within the 16 GB limit for the Leader role.
