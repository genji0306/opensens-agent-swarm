#!/bin/bash
set -euo pipefail
source "${HOME}/.darklab/.env" 2>/dev/null || true
export PYTHONPATH="${HOME}/.darklab/agents:${PYTHONPATH:-}"
cd "${HOME}/.darklab"
exec uv run python3 -m leader.unipat_swarm_cmd "$@"
