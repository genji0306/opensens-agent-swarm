#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export DARKLAB_HOME="${HOME}/.darklab"
export DARKLAB_VERSION="2.1.0"
export SCRIPT_DIR

echo "============================================"
echo "  DARKLAB Cluster Installer v${DARKLAB_VERSION}"
echo "  Distributed Autonomous Research Lab"
echo "============================================"
echo ""

# Detect system
ARCH=$(uname -m)
OS=$(uname -s)
if [[ "$OS" != "Darwin" ]]; then
    echo "ERROR: DarkLab requires macOS. Detected: $OS"
    exit 1
fi
echo "System: macOS ($ARCH)"

# Check RAM
RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
echo "RAM: ${RAM_GB}GB"
echo ""

# Role selection
echo "Select this device's role:"
echo ""
echo "  1) Leader      (Mac mini M4 16GB  -- gateway + orchestrator)"
echo "  2) Academic     (Mac mini M4 24GB  -- research agent)"
echo "  3) Experiment   (Mac mini M4 24GB  -- simulation agent)"
echo "  4) Lab Agent    (Mac mini M4 24GB+ -- instrument control [future])"
echo "  5) Boss         (MacBook           -- command & control dashboard)"
echo ""
read -p "Role [1-5]: " role

# Create DarkLab home directory
mkdir -p "${DARKLAB_HOME}/logs" "${DARKLAB_HOME}/keys" "${DARKLAB_HOME}/data"

case $role in
    1)
        echo ""
        echo "=== Installing LEADER role ==="
        source "${SCRIPT_DIR}/roles/leader.sh"
        ;;
    2)
        echo ""
        echo "=== Installing ACADEMIC AGENT role ==="
        source "${SCRIPT_DIR}/roles/academic.sh"
        ;;
    3)
        echo ""
        echo "=== Installing EXPERIMENT AGENT role ==="
        source "${SCRIPT_DIR}/roles/experiment.sh"
        ;;
    4)
        echo ""
        echo "=== Installing LAB AGENT role ==="
        source "${SCRIPT_DIR}/roles/lab-agent.sh"
        ;;
    5)
        echo ""
        echo "=== Installing BOSS role ==="
        source "${SCRIPT_DIR}/roles/boss.sh"
        ;;
    *)
        echo "Invalid selection. Exiting."
        exit 1
        ;;
esac

echo ""
echo "============================================"
echo "  Installation complete!"
echo "  Role: $(echo $role | sed 's/1/Leader/;s/2/Academic/;s/3/Experiment/;s/4/Lab Agent/;s/5/Boss/')"
echo "  DarkLab home: ${DARKLAB_HOME}"
echo "  Logs: ${DARKLAB_HOME}/logs/"
echo "============================================"
