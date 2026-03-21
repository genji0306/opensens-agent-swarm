#!/bin/bash
# Check status of all DarkLab cluster devices
# Run from Boss MacBook or Leader
# Uses OpenClaw native commands with SSH fallback

set -uo pipefail

DARKLAB_HOME="${DARKLAB_HOME:-${HOME}/.darklab}"
if [[ -f "${DARKLAB_HOME}/.env" ]]; then
    source "${DARKLAB_HOME}/.env"
fi

LEADER="${DARKLAB_LEADER:-leader.local}"
ACADEMIC="${DARKLAB_ACADEMIC:-academic.local}"
EXPERIMENT="${DARKLAB_EXPERIMENT:-experiment.local}"
LEADER_PORT="${DARKLAB_LEADER_PORT:-18789}"

echo "=== DarkLab Cluster Status ==="
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

# --- Gateway Health (HTTP check) ---
echo "--- Gateway ---"
GATEWAY_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://${LEADER}:${LEADER_PORT}/health" 2>/dev/null || echo "000")
if [[ "$GATEWAY_HEALTH" == "200" ]]; then
    echo "  Gateway (${LEADER}:${LEADER_PORT}): HEALTHY"
else
    echo "  Gateway (${LEADER}:${LEADER_PORT}): UNREACHABLE (HTTP ${GATEWAY_HEALTH})"
fi

# Try OpenClaw gateway health if running locally
if command -v openclaw &>/dev/null; then
    GW_HEALTH=$(openclaw gateway health 2>/dev/null) || true
    if [[ -n "$GW_HEALTH" ]]; then
        echo "  $GW_HEALTH"
    fi
fi

# --- Connected Devices (via OpenClaw) ---
echo ""
echo "--- Connected Devices ---"
if command -v openclaw &>/dev/null; then
    DEVICES=$(openclaw devices 2>/dev/null) || true
    if [[ -n "$DEVICES" ]]; then
        echo "$DEVICES" | sed 's/^/  /'
    else
        echo "  (no devices listed — openclaw may not be running locally)"
    fi
else
    echo "  (openclaw CLI not installed on this device)"
fi

# --- Bonjour Discovery ---
echo ""
echo "--- Bonjour Discovery ---"
if command -v openclaw &>/dev/null; then
    DISCOVERED=$(openclaw gateway discover 2>/dev/null) || true
    if [[ -n "$DISCOVERED" ]]; then
        echo "$DISCOVERED" | sed 's/^/  /'
    else
        echo "  (no devices discovered via Bonjour)"
    fi
else
    echo "  (openclaw CLI not available)"
fi

# --- Individual Device Status (SSH fallback) ---
echo ""
echo "--- Device Status (SSH) ---"
echo ""
printf "  %-15s %-10s %-14s %-10s %s\n" "Device" "SSH" "Service" "Version" "Role"
printf "  %-15s %-10s %-14s %-10s %s\n" "------" "---" "-------" "-------" "----"

check_device() {
    local name="$1"
    local host="$2"

    printf "  %-15s " "$name"

    # Check SSH connectivity
    if ssh -o ConnectTimeout=3 -o BatchMode=yes "$host" "echo ok" &>/dev/null; then
        printf "%-10s " "OK"
    else
        printf "%-10s " "FAIL"
        printf "%-14s %-10s %s\n" "-" "-" "-"
        return
    fi

    # Check OpenClaw service via SSH
    local oc_status
    oc_status=$(ssh -o ConnectTimeout=3 "$host" "openclaw gateway status 2>/dev/null || openclaw node status 2>/dev/null || echo 'unknown'" 2>/dev/null || echo "unknown")
    if echo "$oc_status" | grep -qi "running"; then
        printf "%-14s " "RUNNING"
    elif [[ "$oc_status" == "unknown" ]]; then
        # Fallback: check launchctl
        local lc_status
        lc_status=$(ssh "$host" "launchctl list 2>/dev/null | grep darklab" 2>/dev/null || echo "")
        if [[ -n "$lc_status" ]]; then
            printf "%-14s " "LOADED"
        else
            printf "%-14s " "DOWN"
        fi
    else
        printf "%-14s " "STOPPED"
    fi

    # Version
    local version
    version=$(ssh "$host" "grep DARKLAB_VERSION ~/.darklab/.env 2>/dev/null | cut -d= -f2" 2>/dev/null || echo "?")
    printf "%-10s " "v${version}"

    # Role
    local role
    role=$(ssh "$host" "grep DARKLAB_ROLE ~/.darklab/.env 2>/dev/null | cut -d= -f2" 2>/dev/null || echo "?")
    printf "%s" "$role"

    echo ""
}

check_device "Leader" "$LEADER"
check_device "Academic" "$ACADEMIC"
check_device "Experiment" "$EXPERIMENT"

# --- Paperclip Dashboard ---
echo ""
echo "--- Paperclip Dashboard ---"
PAPERCLIP_PORT="${PAPERCLIP_PORT:-3100}"
PAPERCLIP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${LEADER}:${PAPERCLIP_PORT}" 2>/dev/null || echo "000")
if [[ "$PAPERCLIP_CODE" == "200" ]] || [[ "$PAPERCLIP_CODE" == "302" ]]; then
    echo "  Paperclip (${LEADER}:${PAPERCLIP_PORT}): RUNNING"
else
    echo "  Paperclip (${LEADER}:${PAPERCLIP_PORT}): UNREACHABLE (HTTP ${PAPERCLIP_CODE})"
fi

echo ""
echo "=== End Status ==="
