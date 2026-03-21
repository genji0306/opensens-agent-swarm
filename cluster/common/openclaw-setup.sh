#!/bin/bash
# Install and configure OpenClaw

echo "[openclaw] Setting up OpenClaw..."

# Install OpenClaw globally
if ! command -v openclaw &>/dev/null; then
    echo "[openclaw] Installing OpenClaw..."
    npm install -g openclaw@latest
else
    echo "[openclaw] OpenClaw already installed: $(openclaw --version 2>/dev/null || echo 'unknown')"
fi

# Create OpenClaw config directory
mkdir -p ~/.openclaw/skills

echo "[openclaw] OpenClaw setup complete."
