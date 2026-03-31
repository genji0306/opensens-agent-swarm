#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "TELEGRAM_BOT_TOKEN is not set."
  echo "Usage:"
  echo "  TELEGRAM_BOT_TOKEN=<token> bash cluster/scripts/register-telegram-commands.sh"
  exit 1
fi

api_url="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setMyCommands"

payload=$(cat <<'JSON'
{
  "commands": [
    {"command": "start", "description": "Show the DarkLab quick-start help"},
    {"command": "help", "description": "Show all DarkLab swarm commands"},
    {"command": "status", "description": "Check cluster health"},
    {"command": "research", "description": "Literature search and gap analysis"},
    {"command": "literature", "description": "Deep literature review"},
    {"command": "doe", "description": "Design experiments"},
    {"command": "paper", "description": "Draft a research paper"},
    {"command": "perplexity", "description": "Web research via Perplexity"},
    {"command": "simulate", "description": "Run simulations"},
    {"command": "analyze", "description": "Analyze data"},
    {"command": "synthetic", "description": "Generate synthetic datasets"},
    {"command": "report_data", "description": "Create publication-quality figures"},
    {"command": "autoresearch", "description": "Run the autonomous ML loop"},
    {"command": "parametergolf", "description": "Parameter optimization"},
    {"command": "synthesize", "description": "Synthesize findings"},
    {"command": "report", "description": "Generate the final report"},
    {"command": "notebooklm", "description": "Generate audio or study guides"},
    {"command": "deerflow", "description": "Deep multi-step research"},
    {"command": "deepresearch", "description": "Iterative deep research"},
    {"command": "swarmresearch", "description": "5-angle parallel research"},
    {"command": "debate", "description": "Run a multi-agent debate"},
    {"command": "fullswarm", "description": "Run the full swarm pipeline"},
    {"command": "results", "description": "List recent research results"},
    {"command": "schedule", "description": "Manage recurring research schedules"},
    {"command": "boost", "description": "Toggle or inspect boost mode"},
    {"command": "rl_train", "description": "Start RL training"},
    {"command": "rl_status", "description": "Check RL training status"},
    {"command": "rl_rollback", "description": "Roll back RL checkpoints"},
    {"command": "rl_freeze", "description": "Freeze the RL baseline"},
    {"command": "turboq_status", "description": "Show TurboQuant cache status"}
  ]
}
JSON
)

curl -fsS -X POST "${api_url}" \
  -H "Content-Type: application/json" \
  -d "${payload}"

echo
echo "Telegram commands registered successfully."
