#!/bin/bash
# Connect DarkLab cluster devices
# Run on Leader after all devices have been installed
# Starts gateway, discovers nodes, approves pairing requests

set -uo pipefail

echo "=== DarkLab Cluster Connection ==="
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

# Step 1: Check if gateway is running
echo "--- Step 1: Gateway Status ---"
GW_STATUS=$(openclaw gateway status 2>/dev/null) || true
if echo "$GW_STATUS" | grep -qi "running"; then
    echo "Gateway: RUNNING"
else
    echo "Gateway not running. Starting..."
    openclaw gateway start 2>/dev/null || {
        echo "ERROR: Could not start gateway."
        echo "Try manually: openclaw gateway start"
        exit 1
    }
    sleep 2
    echo "Gateway started."
fi

# Step 2: Health check
echo ""
echo "--- Step 2: Gateway Health ---"
HEALTH=$(openclaw gateway health 2>/dev/null) || true
if [[ -n "$HEALTH" ]]; then
    echo "$HEALTH"
else
    # Fallback to HTTP check
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:18789/health" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "200" ]]; then
        echo "Gateway health: OK (HTTP 200)"
    else
        echo "WARNING: Gateway health check failed (HTTP ${HTTP_CODE})"
        echo "The gateway may still be starting up. Continuing..."
    fi
fi

# Step 3: Bonjour discovery
echo ""
echo "--- Step 3: Bonjour Discovery ---"
DISCOVERED=$(openclaw gateway discover 2>/dev/null) || true
if [[ -n "$DISCOVERED" ]]; then
    echo "$DISCOVERED"
else
    echo "No devices discovered via Bonjour yet."
    echo "Make sure Academic and Experiment agents are running: openclaw node start"
fi

# Step 4: Check connected devices
echo ""
echo "--- Step 4: Connected Devices ---"
DEVICES=$(openclaw devices 2>/dev/null) || true
if [[ -n "$DEVICES" ]]; then
    echo "$DEVICES"
else
    echo "No devices connected yet."
fi

# Step 5: Wait for pairing requests
echo ""
echo "--- Step 5: Pairing ---"
echo "Waiting for pairing requests from node-hosts..."
echo "Nodes should display a pairing code when they connect."
echo ""
echo "To approve a node, run in another terminal:"
echo "  openclaw pairing approve <display-name> <code>"
echo ""
echo "Example:"
echo "  openclaw pairing approve darklab-academic ABC123"
echo "  openclaw pairing approve darklab-experiment XYZ789"
echo ""

# Interactive polling loop (5 minute timeout)
TIMEOUT=300
ELAPSED=0
INTERVAL=10

echo "Polling for pairing requests (${TIMEOUT}s timeout)..."
echo "Press Ctrl+C to stop polling."
echo ""

while [[ $ELAPSED -lt $TIMEOUT ]]; do
    # Check if devices are now connected
    DEVICE_COUNT=$(openclaw devices 2>/dev/null | grep -c "darklab-" 2>/dev/null || echo "0")
    if [[ "$DEVICE_COUNT" -ge 2 ]]; then
        echo ""
        echo "Both nodes connected!"
        break
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    echo "  [${ELAPSED}s] Waiting... (${DEVICE_COUNT}/2 nodes connected)"
done

# Step 6: Final verification
echo ""
echo "--- Step 6: Final Verification ---"
FINAL_DEVICES=$(openclaw devices 2>/dev/null) || true
echo "$FINAL_DEVICES"

echo ""
echo "=== Cluster Connection Complete ==="
echo ""
echo "Dashboard URLs:"
echo "  Gateway:    http://$(hostname).local:18789"
echo "  Paperclip:  http://$(hostname).local:3100"
echo "  OpenClaw:   openclaw dashboard"
echo ""
echo "Run 'scripts/test-connectivity.sh' to verify full connectivity."
