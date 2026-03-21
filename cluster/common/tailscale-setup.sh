#!/bin/bash
# Set up Tailscale mesh networking

echo "[tailscale] Checking Tailscale..."

if ! command -v tailscale &>/dev/null; then
    echo "[tailscale] Tailscale not installed."
    read -p "Install Tailscale for secure mesh networking? [y/N]: " install_ts
    if [[ "$install_ts" =~ ^[Yy]$ ]]; then
        echo "[tailscale] Installing Tailscale..."
        brew install --cask tailscale
        echo "[tailscale] Installed. Please open Tailscale.app and sign in."
        echo "[tailscale] After signing in, all cluster devices on the same Tailscale"
        echo "[tailscale] account will be able to communicate securely."
    else
        echo "[tailscale] Skipping Tailscale. Devices must be on the same LAN."
    fi
else
    TS_STATUS=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('BackendState','Unknown'))" 2>/dev/null || echo "Unknown")
    echo "[tailscale] Tailscale installed. Status: $TS_STATUS"
    if [[ "$TS_STATUS" != "Running" ]]; then
        echo "[tailscale] Please open Tailscale.app and sign in."
    fi
fi
