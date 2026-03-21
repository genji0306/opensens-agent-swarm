# Boss Agent — Antigravity IDE Operational Guide

Step-by-step guide for setting up, running, and testing the DarkLab Boss agent
using the Antigravity IDE (AI Remote Control) dashboard.

---

## 1. Overview

The **Boss** is the lightweight command-and-control role running on a MacBook.
It has no Python agents, no OpenClaw gateway, and no AI services — it operates
entirely through shell scripts, the Paperclip web dashboard, and Telegram.

**What Boss provides:**
- 8 cluster management scripts (status, verify, connect, pair, test, update, backup, seed)
- Shell aliases for quick access (`darklab-status`, `darklab-verify`, etc.)
- SSH access to all cluster devices (Leader, Academic, Experiment)
- Paperclip dashboard access at `http://<leader>:3100`
- Telegram bot integration via Antigravity Deck

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| macOS (any version) | Intel or Apple Silicon |
| Network access | Same LAN as Leader, Academic, Experiment Mac minis |
| Git | For cloning the installer repo |
| Terminal or Antigravity IDE | For running commands |

The installer automatically installs: Homebrew, Node.js >=22.16, pnpm, and optionally Tailscale.

---

## 3. Installation

### 3.1 Clone and Run

```bash
git clone <repo-url> ~/darklab-installer
cd ~/darklab-installer
chmod +x install.sh
./install.sh
```

Select **option 5** (Boss) when prompted:
```
Select device role:
  1) Leader      (Mac mini M4 16GB  -- gateway + orchestrator)
  2) Academic    (Mac mini M4 24GB  -- research agent)
  3) Experiment  (Mac mini M4 24GB  -- simulation agent)
  4) Lab Agent   (Mac mini M4 24GB+ -- instrument control [future])
  5) Boss        (MacBook           -- command & control dashboard)
>>> 5
```

### 3.2 What the Installer Does

1. Creates `~/.darklab/` directory structure (logs, keys, data, scripts)
2. Installs Homebrew (if missing), Node.js >=22.16, pnpm
3. Optionally installs Tailscale for mesh networking
4. Discovers the Leader device via Bonjour/mDNS (or prompts for manual IP)
5. Writes `~/.darklab/.env` with Boss configuration
6. Generates SSH Ed25519 key at `~/.ssh/id_ed25519` (if not present)
7. Copies all 8 management scripts to `~/.darklab/scripts/`
8. Creates shell aliases in `~/.zshrc` or `~/.bashrc`

### 3.3 Post-Install Checklist

```bash
# Verify .env was created
cat ~/.darklab/.env
# Expected output includes:
#   DARKLAB_ROLE=boss
#   DARKLAB_LEADER=leader.local (or IP)
#   PAPERCLIP_URL=http://leader.local:3100

# Verify aliases are loaded
source ~/.zshrc  # or ~/.bashrc
darklab-status   # Should attempt cluster status check

# Copy SSH key to cluster devices (one-time)
ssh-copy-id darklab@leader.local
ssh-copy-id darklab@academic.local
ssh-copy-id darklab@experiment.local
```

---

## 4. Running with Antigravity IDE

The Antigravity Deck (AI Remote Control) provides a web dashboard + Telegram bot
for remote cluster management.

### 4.1 Antigravity Deck Setup

Location: `Opensens AI Remote control/Antigravity-Deck-main/`

```bash
cd "Opensens AI Remote control/Antigravity-Deck-main"

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env:
#   PORT=3500
#   TELEGRAM_BOT_TOKEN=<your-bot-token>
#   TELEGRAM_CHAT_ID=<your-chat-id>

# Start the server
node server.js
# Backend: http://localhost:3500
# Frontend: http://localhost:3000 (Next.js)
```

### 4.2 Creating a DarkLab Workspace

In the Antigravity dashboard (http://localhost:3000):

1. Open the sidebar → **Workspaces**
2. Create a new workspace pointing to `~/darklab-installer/`
3. The workspace provides:
   - Terminal access for running cluster scripts
   - Claude Code integration for AI-assisted cluster management
   - Real-time WebSocket updates

### 4.3 Claude Code Integration

From the Antigravity dashboard or Telegram:

```
/claude Run darklab-status to check cluster health
/claude Verify all cluster components with darklab-verify
/claude SSH into leader.local and check openclaw gateway status
```

Claude Code runs in streaming mode with real-time tool visibility.

### 4.4 Telegram Remote Control

Configure the Telegram bridge in Antigravity:

| Command | Action |
|---------|--------|
| `/start` | Initialize bot |
| `/help` | Show available commands |
| `/listws` | List workspaces (inline keyboard) |
| `/setws <name>` | Set active workspace |
| `/claude <prompt>` | Run Claude Code task |
| `/status` | System resource status |
| `/screenshot` | Capture workspace screenshot |
| `/abort` | Abort running Claude Code task |

**Example Telegram workflow:**
```
You: /setws darklab
Bot: Workspace set to 'darklab'

You: /claude Run cluster-status.sh and summarize the results
Bot: [Streaming output with tool calls...]
Bot: Summary: Leader online, Academic online, Experiment offline...
```

---

## 5. Testing Each Management Script

All scripts are accessible via aliases or directly from `~/.darklab/scripts/`.

### 5.1 cluster-status.sh (`darklab-status`)

**Purpose:** Health overview of all cluster devices and services.

```bash
darklab-status
```

**What it checks:**
1. Gateway HTTP health at `http://<leader>:18789/health`
2. `openclaw gateway health` (if openclaw installed locally)
3. `openclaw devices` connected device list
4. SSH reachability of each device (Leader, Academic, Experiment)
5. Per-device service status, version, and role
6. Paperclip dashboard at `http://<leader>:3100`

**Expected output (healthy cluster):**
```
=== DarkLab Cluster Status ===
Gateway: http://leader.local:18789 ... OK (200)
Connected devices: 3

Device           SSH    Service    Version   Role
leader.local     OK     running    2.0.0     leader
academic.local   OK     running    2.0.0     academic
experiment.local OK     running    2.0.0     experiment

Paperclip: http://leader.local:3100 ... OK
```

### 5.2 verify-cluster.sh (`darklab-verify`)

**Purpose:** Comprehensive PASS/FAIL/WARN verification of all components.

```bash
darklab-verify
```

**Sections verified (14 total):**
1. Core Infrastructure (Homebrew, Node.js, Python, uv, pnpm)
2. DarkLab Home (`~/.darklab/` directory structure)
3. Python Environment (venv, packages)
4. Agent Code (shared modules, role-specific agents)
5. Ed25519 Keys (signing.key, signing.pub)
6. OpenClaw Skills (all 14 skills)
7. Claude Scientific Skills
8. AutoResearch (experiment only)
9. Paperclip (leader only)
10. Browser Profiles
11. OpenClaw Service (gateway or node status)
12. Exec Approvals (allowlisted commands)
13. Node Config (node.json for agent devices)
14. Network Connectivity + API Keys

**Expected output:**
```
=== DarkLab Verification ===
... [PASS] / [FAIL] / [WARN] for each check ...

Summary: 42 PASS, 0 FAIL, 3 WARN
```

### 5.3 test-connectivity.sh (`darklab-test`)

**Purpose:** 6-test network diagnostics.

```bash
darklab-test
```

**Tests:**
1. **DNS Resolution** — Can resolve `leader.local` hostname
2. **TCP Port** — Can connect to port 18789 on Leader
3. **HTTP Health** — GET `http://<leader>:18789/health` returns 200
4. **OpenClaw Service** — `openclaw gateway status` or `openclaw node status` is running
5. **Exec Approvals** — `~/.openclaw/exec-approvals.json` exists
6. **Paperclip Dashboard** — GET `http://<leader>:3100` returns 200/302

**Expected (all passing):**
```
Test 1: DNS Resolution .............. PASS
Test 2: TCP Port 18789 .............. PASS
Test 3: HTTP /health ................ PASS
Test 4: OpenClaw Service ............ PASS
Test 5: Exec Approvals .............. PASS
Test 6: Paperclip Dashboard ......... PASS

Results: 6/6 PASS
```

### 5.4 connect-cluster.sh (`darklab-connect`)

**Purpose:** Connect all devices to the Leader gateway. **Run on Leader.**

```bash
# SSH into Leader first, or run via Telegram
ssh darklab@leader.local
~/.darklab/scripts/connect-cluster.sh
```

**Process:**
1. Checks gateway status
2. Verifies HTTP health endpoint
3. Runs Bonjour discovery for nearby devices
4. Lists connected devices
5. Enters pairing wait loop (5-minute timeout)
6. Final verification of all connected nodes

### 5.5 pair-devices.sh

**Purpose:** Interactive pairing of Academic/Experiment nodes. **Run on Leader.**

```bash
ssh darklab@leader.local
~/.darklab/scripts/pair-devices.sh
```

Prompts for pairing codes from each device, then calls:
```bash
openclaw pairing approve darklab-academic <CODE>
openclaw pairing approve darklab-experiment <CODE>
```

### 5.6 update-cluster.sh (`darklab-update`)

**Purpose:** Rolling update across all devices via SSH.

```bash
darklab-update
```

**Warning:** Prompts for confirmation before executing. Updates:
- `git pull` on each device
- `uv sync` for Python dependencies
- `npm update openclaw` for OpenClaw
- Paperclip rebuild (leader only)
- AutoResearch pull (experiment only)
- Service restart via launchctl

### 5.7 backup-cluster.sh

**Purpose:** SCP backup of configs and keys from all devices.

```bash
~/.darklab/scripts/backup-cluster.sh
```

**Backs up to** `~/darklab-backups/<timestamp>/`:
- `.env` from each device
- `config.yaml` from `~/.openclaw/`
- `signing.pub` (public keys only)
- LaunchAgent plists

### 5.8 seed-paperclip.sh (`darklab-seed`)

**Purpose:** Create the org chart in Paperclip. **Run on Leader.**

```bash
ssh darklab@leader.local
~/.darklab/scripts/seed-paperclip.sh
```

**Creates 4 agents:**
| Agent | Role | Budget |
|-------|------|--------|
| Boss | CEO (human) | $0 |
| DarkLab Leader | CTO | $50/day |
| DarkLab Academic | Research Director | $30/day |
| DarkLab Experiment | Lab Director | $20/day |

---

## 6. Paperclip Dashboard

Access: `http://<leader-host>:3100` (or use `darklab-dashboard` alias)

```bash
darklab-dashboard   # Opens browser to Paperclip URL
```

**Dashboard features:**
- Real-time agent status and health
- Budget tracking per agent (daily spend vs. limits)
- Task queue monitoring
- Approval gates for high-cost operations
- Org chart visualization

---

## 7. Troubleshooting

### DNS / Bonjour Issues

```bash
# If leader.local doesn't resolve, use IP address:
ping leader.local
# If it fails, find Leader IP and set manually:
echo "DARKLAB_LEADER=192.168.1.100" >> ~/.darklab/.env
```

### SSH Connection Failures

```bash
# Test SSH manually:
ssh -o BatchMode=yes -o ConnectTimeout=5 darklab@leader.local echo ok

# If it fails:
# 1. Check SSH key was copied: ssh-copy-id darklab@leader.local
# 2. Check remote SSH is enabled: System Preferences → Sharing → Remote Login
# 3. Check firewall: sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
```

### Ports Blocked

Required ports:
| Port | Service | Direction |
|------|---------|-----------|
| 18789 | OpenClaw Gateway | Boss → Leader |
| 3100 | Paperclip Dashboard | Boss → Leader |
| 22 | SSH | Boss → All devices |

```bash
# Check if port is reachable:
nc -z -w5 leader.local 18789 && echo "Open" || echo "Blocked"
```

### Tailscale Overlay

If using Tailscale, devices may have different hostnames:
```bash
# Check Tailscale IPs:
tailscale status

# Use Tailscale MagicDNS names:
# leader.tail12345.ts.net instead of leader.local
```

### OpenClaw Not Running

```bash
# On Leader:
openclaw gateway status
# If not running:
openclaw gateway start

# On Agent devices:
openclaw node status
# If not running:
openclaw node start
```

### Paperclip Not Reachable

```bash
# On Leader, check LaunchAgent:
launchctl list | grep darklab-paperclip

# If not loaded:
launchctl load ~/Library/LaunchAgents/com.opensens.darklab-paperclip.plist

# Manual start:
cd ~/.darklab/paperclip && pnpm dev
```

---

## 8. Quick Reference — All Aliases

| Alias | Script | Description |
|-------|--------|-------------|
| `darklab-status` | cluster-status.sh | Cluster health overview |
| `darklab-verify` | verify-cluster.sh | Comprehensive PASS/FAIL check |
| `darklab-test` | test-connectivity.sh | 6-test network diagnostics |
| `darklab-connect` | connect-cluster.sh | Connect devices (run on Leader) |
| `darklab-update` | update-cluster.sh | Rolling update all devices |
| `darklab-seed` | seed-paperclip.sh | Create Paperclip org chart |
| `darklab-dashboard` | — | Open Paperclip in browser |
| `darklab-webchat` | — | Open OpenClaw web chat |
