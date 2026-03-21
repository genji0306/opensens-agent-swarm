#!/bin/bash
# DarkLab Leader Dispatch runner — invoked by OpenClaw system.run
# Routes commands to Academic/Experiment agents or plans campaigns.
set -euo pipefail
source "${HOME}/.darklab/.env" 2>/dev/null || true
export PYTHONPATH="${HOME}/.darklab/agents:${PYTHONPATH:-}"
cd "${HOME}/.darklab"
exec uv run python3 -m leader.dispatch "$@"
