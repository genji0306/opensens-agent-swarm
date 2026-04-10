#!/usr/bin/env bash
set -euo pipefail

# Run the KAIROS daemon handler via Python module
exec python3 -m leader.kairos "$@"
