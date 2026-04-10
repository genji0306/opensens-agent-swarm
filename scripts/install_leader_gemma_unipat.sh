#!/bin/bash
# Install Ollama + Gemma models + UniScientist on the Leader Mac mini (16GB).
#
# Usage (run ON the Leader):
#   bash scripts/install_leader_gemma_unipat.sh
#
# Or remotely from the Boss machine when on the same LAN / Tailscale:
#   scp scripts/install_leader_gemma_unipat.sh "cyber 02@192.168.23.25:/tmp/"
#   ssh "cyber 02@192.168.23.25" "bash /tmp/install_leader_gemma_unipat.sh"
#
# Idempotent: safe to re-run. Skips anything already installed.
set -euo pipefail

DARKLAB_HOME="${DARKLAB_HOME:-$HOME/.darklab}"
UNIPAT_DIR="$DARKLAB_HOME/unipat"
ENV_FILE="$DARKLAB_HOME/.env"

GEMMA_LIGHT="gemma3:4b"     # ~3.0 GB — default worker
GEMMA_HEAVY="gemma3:12b"    # ~7.2 GB — UniPat default model
# Pull these only if you have headroom (single-slot quality mode)
GEMMA_XL="gemma3:27b"       # ~16 GB — only with nothing else running

log() { printf '\033[36m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[warn]\033[0m %s\n' "$*"; }
err()  { printf '\033[31m[error]\033[0m %s\n' "$*"; exit 1; }

# ── Sanity ─────────────────────────────────────────────────────────
[[ "$(uname)" == "Darwin" ]] || err "This script is for macOS (Leader Mac mini)."
mkdir -p "$DARKLAB_HOME"

# ── 1. Install Homebrew if missing ─────────────────────────────────
if ! command -v brew >/dev/null 2>&1; then
    log "Installing Homebrew"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Apple Silicon brew lives in /opt/homebrew
    if [[ -d /opt/homebrew/bin ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
else
    log "Homebrew already installed: $(brew --version | head -1)"
fi

# ── 2. Install Ollama if missing ───────────────────────────────────
if ! command -v ollama >/dev/null 2>&1; then
    log "Installing Ollama via brew"
    brew install --cask ollama || brew install ollama
else
    log "Ollama already installed: $(ollama --version 2>&1 | head -1)"
fi

# ── 3. Start Ollama as a background service ────────────────────────
if ! pgrep -f "ollama serve" >/dev/null 2>&1; then
    log "Starting Ollama server (background)"
    # Prefer brew services for auto-start on login; fall back to nohup
    if brew services list 2>/dev/null | grep -q "^ollama"; then
        brew services start ollama || true
    else
        nohup ollama serve >"$DARKLAB_HOME/ollama.log" 2>&1 &
        disown
    fi
    sleep 3
else
    log "Ollama server already running (pid=$(pgrep -f 'ollama serve' | head -1))"
fi

# Quick health check
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    warn "Ollama not responding on :11434 yet — giving it 5 more seconds"
    sleep 5
fi
curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 || err "Ollama failed to start on :11434"
log "Ollama is healthy on http://localhost:11434"

# ── 4. Pull Gemma models (default: light + heavy) ──────────────────
pull_if_missing() {
    local model="$1"
    if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$model"; then
        log "Model already present: $model"
    else
        log "Pulling $model (this can take several minutes)"
        ollama pull "$model"
    fi
}

pull_if_missing "$GEMMA_LIGHT"
pull_if_missing "$GEMMA_HEAVY"

# Pull XL only if DARKLAB_PULL_XL=1 — it's 16GB and will compete with other services
if [[ "${DARKLAB_PULL_XL:-0}" == "1" ]]; then
    pull_if_missing "$GEMMA_XL"
fi

# Try Gemma 4 PLE edge models when available in Ollama
for candidate in "gemma4:e4b" "gemma4:e2b"; do
    if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$candidate"; then
        log "Gemma 4 PLE model already present: $candidate"
    else
        # Best-effort — don't fail the script if not yet published
        log "Attempting to pull $candidate (will skip if not yet published)"
        ollama pull "$candidate" 2>/dev/null || warn "$candidate not yet in Ollama registry — skipped"
    fi
done

# ── 5. Clone UniScientist (UniPat-AI) ──────────────────────────────
if [[ -d "$UNIPAT_DIR/.git" ]]; then
    log "UniScientist already cloned at $UNIPAT_DIR — fetching latest"
    git -C "$UNIPAT_DIR" fetch --quiet || warn "git fetch failed (offline?)"
else
    log "Cloning UniScientist into $UNIPAT_DIR"
    git clone https://github.com/UniPat-AI/UniScientist "$UNIPAT_DIR"
fi

# ── 6. Install UniScientist Python deps into a dedicated venv ──────
if [[ -f "$UNIPAT_DIR/requirements.txt" ]]; then
    if [[ ! -d "$UNIPAT_DIR/.venv" ]]; then
        log "Creating dedicated venv for UniScientist"
        python3 -m venv "$UNIPAT_DIR/.venv"
    fi
    log "Installing UniScientist requirements (quiet)"
    "$UNIPAT_DIR/.venv/bin/pip" install --upgrade pip --quiet
    "$UNIPAT_DIR/.venv/bin/pip" install -r "$UNIPAT_DIR/requirements.txt" --quiet || \
        warn "Some UniScientist deps failed — inspect $UNIPAT_DIR/.venv manually"
else
    warn "requirements.txt not found in $UNIPAT_DIR (repo layout may have changed)"
fi

# ── 7. Seed ~/.darklab/.env with UniPat vars (non-destructive) ─────
touch "$ENV_FILE"
ensure_env_var() {
    local key="$1"
    local default="$2"
    if ! grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        printf '%s=%s\n' "$key" "$default" >> "$ENV_FILE"
        log "Seeded $key in $ENV_FILE"
    fi
}
ensure_env_var "OLLAMA_BASE_URL" "http://localhost:11434"
ensure_env_var "GEMMA_DEFAULT_MODEL" "$GEMMA_LIGHT"
ensure_env_var "UNIPAT_MODEL" "$GEMMA_HEAVY"
ensure_env_var "SERPER_KEY_ID" "REPLACE_ME"
ensure_env_var "JINA_API_KEYS" "REPLACE_ME"
ensure_env_var "OPENROUTER_API_KEY" "REPLACE_ME"

# ── 8. Summary ─────────────────────────────────────────────────────
log "Installation complete."
echo
echo "─── Summary ──────────────────────────────────────────────"
echo "  Ollama endpoint : http://localhost:11434"
echo "  Models pulled   :"
ollama list 2>/dev/null | grep -E "^gemma" || echo "    (none yet)"
echo "  UniScientist    : $UNIPAT_DIR"
echo "  UniPat venv     : $UNIPAT_DIR/.venv"
echo "  Env file        : $ENV_FILE"
echo
echo "Next steps:"
echo "  1. Edit $ENV_FILE and set real values for SERPER_KEY_ID, JINA_API_KEYS, OPENROUTER_API_KEY"
echo "  2. Restart the DarkLab Leader service so it picks up the new env"
echo "  3. Smoke test from Boss:"
echo "       curl -sX POST http://192.168.23.25:8100/dispatch \\"
echo "         -H 'Content-Type: application/json' \\"
echo "         -d '{\"command\":\"gemma-swarm\",\"args\":\"status\"}'"
echo "       curl -sX POST http://192.168.23.25:8100/dispatch \\"
echo "         -H 'Content-Type: application/json' \\"
echo "         -d '{\"command\":\"unipat\",\"args\":\"status\"}'"
echo "──────────────────────────────────────────────────────────"
