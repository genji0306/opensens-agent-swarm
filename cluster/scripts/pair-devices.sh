#!/bin/bash
# Multi-device pairing helper
# Run on the Leader device after Academic and Experiment nodes are started

set -euo pipefail

echo "=== DarkLab Device Pairing ==="
echo ""
echo "This script helps you approve pairing codes from Academic and Experiment nodes."
echo "Make sure the other devices have started their node-host and display pairing codes."
echo ""

# Academic pairing
read -p "Academic Agent pairing code (or Enter to skip): " academic_code
if [[ -n "$academic_code" ]]; then
    echo "Approving Academic Agent..."
    openclaw pairing approve academic "$academic_code"
    echo "Academic Agent paired successfully."
fi

echo ""

# Experiment pairing
read -p "Experiment Agent pairing code (or Enter to skip): " experiment_code
if [[ -n "$experiment_code" ]]; then
    echo "Approving Experiment Agent..."
    openclaw pairing approve experiment "$experiment_code"
    echo "Experiment Agent paired successfully."
fi

echo ""

# Lab Agent (optional)
read -p "Lab Agent pairing code (or Enter to skip): " lab_code
if [[ -n "$lab_code" ]]; then
    read -p "Lab Agent name (e.g., lab-potentiostat): " lab_name
    echo "Approving Lab Agent..."
    openclaw pairing approve "$lab_name" "$lab_code"
    echo "Lab Agent '${lab_name}' paired successfully."
fi

echo ""
echo "=== Pairing complete ==="
echo "Run '/status' in Telegram to verify all nodes are connected."
