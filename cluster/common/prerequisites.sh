#!/bin/bash
# Common prerequisites for all DarkLab roles
# Installs: Homebrew, Node.js 22, Python 3.11+, uv, pnpm

echo "[prereq] Checking prerequisites..."

# Homebrew
if ! command -v brew &>/dev/null; then
    echo "[prereq] Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add Homebrew to PATH for Apple Silicon
    if [[ $(uname -m) == "arm64" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
else
    echo "[prereq] Homebrew: OK"
fi

# Node.js >=22.16.0 (required by OpenClaw)
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
    echo "[prereq] Installing Node.js >=22.16.0 (current: ${NODE_RAW})..."
    brew install node@22
    brew link --overwrite node@22
else
    echo "[prereq] Node.js ${NODE_RAW}: OK"
fi

# Python 3.11+
PY_VERSION=$(python3 --version 2>/dev/null | sed 's/Python //' | cut -d. -f1-2 || echo "0.0")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
    echo "[prereq] Installing Python 3.11+..."
    brew install python@3.12
else
    echo "[prereq] Python ${PY_VERSION}: OK"
fi

# uv (Astral's Python package manager)
if ! command -v uv &>/dev/null; then
    echo "[prereq] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "[prereq] uv: OK"
fi

# pnpm
if ! command -v pnpm &>/dev/null; then
    echo "[prereq] Installing pnpm..."
    npm install -g pnpm
else
    echo "[prereq] pnpm: OK"
fi

echo "[prereq] All prerequisites installed."
