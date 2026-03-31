# darklab-fullswarm

End-to-end research pipeline that orchestrates ALL DarkLab agents across 6 phases
on a single research topic. Supports fully autonomous, semi-manual, and manual modes.
Prioritizes local LLM (Ollama qwen3:8b) for $0 cost overnight research.

## Usage

```
/fullswarm auto quantum error correction codes
/fullswarm semi solid-state battery commercialization
/fullswarm manual room-temperature superconductors
/fullswarm status
/fullswarm resume swarm-a1b2c3d4
/fullswarm results
```

## Modes

### Auto (Overnight Research)
Fully autonomous — runs all 18 steps without human intervention.
Best for overnight batch research when you want results by morning.

```
/fullswarm auto <research topic>
```

### Semi (Guided Research)
Runs Phase 1 (Discovery) and Phase 2 (Deep Analysis) automatically,
then pauses with a summary of findings. Review the results, then
resume to proceed with experiments and deliverables.

```
/fullswarm semi <research topic>
# ... review /results ...
/fullswarm resume <run_id>
```

### Manual (Approval Required)
Shows the full 18-step campaign plan with phase breakdown and
dependency graph. No execution until explicitly approved.

```
/fullswarm manual <research topic>
# ... review plan ...
/fullswarm resume <run_id>
```

## Phases & Steps

| Phase | Steps | Commands | Duration |
|-------|-------|----------|----------|
| 1. Discovery | 1-4 | /research /literature /perplexity /deerflow | 20-40m |
| 2. Deep Analysis | 5-7 | /deepresearch /swarmresearch /debate | 30-90m |
| 3. Experimentation | 8-11 | /doe /synthetic /simulate /analyze | 20-40m |
| 4. Optimization | 12-13 | /parametergolf /autoresearch | 15-30m |
| 5. Deliverables | 14-17 | /synthesize /report-data /report /paper | 20-40m |
| 6. Extras | 18 | /notebooklm | 5-10m |

Total: 18 steps, ~2-4 hours (auto mode).

## Dependency Graph

```
Step  1 /research ─────┐
Step  2 /literature ───┤
Step  3 /perplexity ───┼──→ Step 5 /deepresearch ──→ Step 8 /doe ──→ Step 9 /synthetic ──┐
Step  4 /deerflow ─────┤    Step 6 /swarmresearch ─────────────────→ Step 10 /simulate ──┤
                       │    Step 7 /debate ────────────────────────────────────────────────┤
                       │                                                                   │
                       │                                              Step 11 /analyze ←──┘
                       │                                                   │
                       │                              Step 12 /parametergolf ←── Step 11
                       │                              Step 13 /autoresearch ←── Step 11
                       │                                   │
                       └──→ Step 14 /synthesize ←──────────┘
                                  │
                         Step 15 /report-data
                         Step 16 /report
                         Step 17 /paper
                         Step 18 /notebooklm
```

## Management Commands

| Command | Description |
|---------|-------------|
| `/fullswarm status` | List all runs (active, paused, completed) |
| `/fullswarm results` | List completed runs with summaries |
| `/fullswarm resume <id>` | Resume a paused or planned run |

## Cost

- Local LLM (default): $0 — all steps use Ollama qwen3:8b
- With boost: $5-15 depending on topic complexity
- Planning only uses Claude when decomposing free-form requests

## Output

Results stored in:
- Knowledge base: `~/.darklab/deep-research/knowledge.jsonl`
- Run state: `~/.darklab/fullswarm/<run_id>.json`
- Individual step outputs: via each command's own storage

## Configuration

- LLM: Ollama qwen3:8b (local, $0) — override with /boost on
- Step timeout: 600s per step
- Phase 2 pause (semi mode): after deepresearch + swarmresearch + debate
