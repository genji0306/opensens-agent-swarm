#!/bin/bash
# Update all DarkLab cluster devices
# Run from Boss MacBook

set -euo pipefail

LEADER="${DARKLAB_LEADER:-leader.local}"
ACADEMIC="${DARKLAB_ACADEMIC:-academic.local}"
EXPERIMENT="${DARKLAB_EXPERIMENT:-experiment.local}"

DEVICES=("$LEADER" "$ACADEMIC" "$EXPERIMENT")

echo "=== DarkLab Cluster Update ==="
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""
echo "Devices to update:"
for host in "${DEVICES[@]}"; do
    echo "  - $host"
done
echo ""
read -p "Proceed with update? [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Update cancelled."
    exit 0
fi

FAILED=()

for host in "${DEVICES[@]}"; do
    echo ""
    echo "--- Updating $host ---"

    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$host" "echo ok" &>/dev/null; then
        echo "WARN: Cannot reach $host. Skipping."
        FAILED+=("$host")
        continue
    fi

    # Backup current config
    ssh "$host" "cp ~/.darklab/.env ~/.darklab/.env.bak.\$(date +%s) 2>/dev/null" || true

    # Pull latest code (if git repo exists)
    ssh "$host" "cd ~/darklab 2>/dev/null && git pull origin main 2>/dev/null" || echo "  No git repo at ~/darklab (OK for fresh install)"

    # Update Python dependencies
    ssh "$host" "cd ~/.darklab && uv sync 2>/dev/null" || echo "  Python deps: no changes"

    # Update OpenClaw
    ssh "$host" "npm update -g openclaw 2>/dev/null" || echo "  OpenClaw: update skipped"

    # Update Paperclip (Leader only)
    if [[ "$host" == "$LEADER" ]]; then
        ssh "$host" "cd ~/.darklab/paperclip 2>/dev/null && git pull 2>/dev/null && pnpm install 2>/dev/null && pnpm build 2>/dev/null" || echo "  Paperclip: update skipped"
    fi

    # Update AutoResearch (Experiment only)
    if [[ "$host" == "$EXPERIMENT" ]]; then
        ssh "$host" "cd ~/.darklab/tools/autoresearch 2>/dev/null && git pull 2>/dev/null" || echo "  AutoResearch: update skipped"
    fi

    # Restart services
    ssh "$host" "launchctl kickstart -k gui/\$(id -u)/com.opensens.darklab-leader 2>/dev/null || launchctl kickstart -k gui/\$(id -u)/com.opensens.darklab-node 2>/dev/null" || echo "  Service restart: manual restart needed"

    echo "--- $host updated ---"
done

echo ""
if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo "WARNING: Could not reach: ${FAILED[*]}"
fi
echo "=== Cluster update complete ==="
echo ""
echo "Run 'scripts/cluster-status.sh' to verify all nodes are healthy."
