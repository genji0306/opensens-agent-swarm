# darklab-debate

Multi-agent debate simulation powered by MiroShark. Generates structured
scientific debates with AI agents holding diverse viewpoints, producing
transcripts that serve as synthetic training data for OpenClaw-RL.

## Usage

```
/debate "CRISPR off-target effects are under-reported in clinical trials"
/debate --scenario peer-review "Your research paper title or abstract"
/debate --scenario methodology --rounds 15 "Experimental design description"
```

## Scenarios

| Scenario | Description |
|----------|-------------|
| `hypothesis` | Agents argue for and against a research hypothesis (default) |
| `peer-review` | Simulate hostile peer reviewers evaluating a paper |
| `methodology` | Challenge statistical validity and experimental design |
| `literature-dispute` | Debate conflicting findings from different papers |
| `cross-domain` | Challenge applicability of findings across domains |
| `budget` | Debate resource allocation for a research proposal |

## Options

- `--scenario <name>` — Debate scenario type (default: hypothesis)
- `--rounds <n>` — Number of debate rounds (default: 10)
- `--agents <n>` — Number of debate agents (default: 15)

## Output

Returns a structured debate summary including:
- Key arguments from each side
- Belief state changes over rounds
- Consensus points and unresolved disputes
- Quality scores for each agent's contributions

Debate transcripts are automatically converted to OpenClaw-RL rollout
format and stored for future training cycles.

## Requirements

- MiroShark backend running (DARKLAB_MIROSHARK_ENABLED=true)
- Neo4j database for knowledge graph
- Ollama or cloud LLM for simulation rounds
