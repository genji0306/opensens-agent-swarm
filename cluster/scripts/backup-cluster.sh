#!/bin/bash
# Backup DarkLab cluster configuration
# Run from Boss MacBook

set -euo pipefail

LEADER="${DARKLAB_LEADER:-leader.local}"
ACADEMIC="${DARKLAB_ACADEMIC:-academic.local}"
EXPERIMENT="${DARKLAB_EXPERIMENT:-experiment.local}"

BACKUP_DIR="${HOME}/darklab-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "=== DarkLab Cluster Backup ==="
echo "Backup directory: $BACKUP_DIR"
echo ""

backup_device() {
    local name="$1"
    local host="$2"
    local device_dir="${BACKUP_DIR}/${name}"
    mkdir -p "$device_dir"

    echo "Backing up $name ($host)..."

    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$host" "echo ok" &>/dev/null; then
        echo "  WARN: Cannot reach $host. Skipping."
        return
    fi

    # Backup .env (contains API keys - handle with care)
    scp "$host:~/.darklab/.env" "$device_dir/env.backup" 2>/dev/null || echo "  No .env found"

    # Backup OpenClaw config
    scp "$host:~/.openclaw/config.yaml" "$device_dir/openclaw-config.yaml" 2>/dev/null || echo "  No config.yaml found"

    # Backup signing keys
    scp "$host:~/.darklab/keys/signing.pub" "$device_dir/signing.pub" 2>/dev/null || echo "  No public key found"
    # Note: Private keys are NOT backed up remotely for security

    # Backup LaunchAgent plist
    scp "$host:~/Library/LaunchAgents/com.opensens.darklab-*.plist" "$device_dir/" 2>/dev/null || echo "  No plist found"

    echo "  $name backed up to $device_dir"
}

backup_device "leader" "$LEADER"
backup_device "academic" "$ACADEMIC"
backup_device "experiment" "$EXPERIMENT"

echo ""
echo "=== Backup complete ==="
echo "Location: $BACKUP_DIR"
echo ""
echo "WARNING: The backup contains API keys. Store securely."
echo "Consider encrypting: tar czf - ${BACKUP_DIR} | age -r <your-age-key> > backup.tar.gz.age"
