---
name: darklab-leader
description: DarkLab Leader Agent -- routes commands, plans research campaigns, coordinates Academic and Experiment agents across the cluster.
metadata:
  {"openclaw": {"emoji": "boss", "requires": {"env": ["ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN"]}}}
---

# DarkLab Leader

Central coordinator for the DarkLab research cluster. Routes incoming commands to the correct agent and device.

## Routing

| Command | Target Device | Target Skill |
|---------|--------------|--------------|
| `/research <topic>` | Academic | darklab-research |
| `/literature <query>` | Academic | darklab-literature |
| `/doe <spec>` | Academic | darklab-doe |
| `/paper <topic>` | Academic | darklab-paper |
| `/perplexity <query>` | Academic | darklab-perplexity |
| `/simulate <params>` | Experiment | darklab-simulation |
| `/analyze <data>` | Experiment | darklab-analysis |
| `/synthetic <spec>` | Experiment | darklab-synthetic |
| `/report-data <scope>` | Experiment | darklab-report-data |
| `/autoresearch <program>` | Experiment | darklab-autoresearch |
| `/synthesize <topic>` | Leader (local) | darklab-synthesis |
| `/report <scope>` | Leader (local) | darklab-media-gen |
| `/notebooklm <sources>` | Leader (local) | darklab-notebooklm |
| `/status` | All devices | health check |

## Paperclip Coordination Layer

When Paperclip AI is running (`localhost:3100`), the Leader uses it for:

- **Budget enforcement**: Per-agent daily API spend limits ($50 Leader, $30 Academic, $20 Experiment)
- **Approval gates**: High-cost or irreversible actions require Boss approval via Telegram
- **Task tracking**: Atomic task checkout with heartbeat monitoring
- **Dashboard**: Boss can monitor cluster status, budgets, and task progress at `leader.local:3100`

Paperclip sits above OpenClaw — it does not replace the gateway but adds governance.

## Multi-Step Campaigns

For complex research requests, the Leader decomposes the task:

1. Plan the campaign using Claude OPUS
2. Dispatch literature research to Academic
3. Wait for research plan + experimental proposal
4. Forward proposal to Boss for approval (Paperclip approval gate)
5. Dispatch approved experiment to Experiment Agent
6. Experiment Agent runs AutoResearch loop (if ML task)
7. Collect results and synthesize
8. Generate final multimedia report
9. Send to Boss

## Node Invocation

Use `node.invoke` to dispatch to remote agents:

```json
{
  "node": "darklab-academic",
  "command": "darklab-research",
  "payload": {"topic": "MnO2 nanoparticles", "scope": "literature_review"}
}
```
