# darklab-deepresearch

Iterative deep research with academic source search and convergence evaluation.
Searches arXiv, Semantic Scholar, and bioRxiv for relevant papers, synthesizes
findings, and refines through multiple iterations until quality meets the
convergence threshold (default 0.75).

## Usage

```
/deepresearch solid-state battery commercialization timeline
/deepresearch CRISPR off-target effects in clinical trials
/deepresearch quantum sensor applications for environmental monitoring
```

## How It Works

1. **Search** — Queries arXiv, Semantic Scholar, and bioRxiv in parallel
2. **Synthesize** — Generates a structured research draft from found papers
3. **Evaluate** — Scores the draft on 5 quality metrics (completeness, source quality, structure, novelty, accuracy)
4. **Iterate** — If score < threshold, feeds gap analysis back for refinement
5. **Deliver** — Returns the final report with citations when quality converges

## Quality Metrics

| Metric | Weight | Description |
|--------|--------|-------------|
| Completeness | 25% | Coverage of sub-topics, section presence |
| Source Quality | 25% | Peer-reviewed ratio, citation counts |
| Structure | 20% | Heading hierarchy, logical flow |
| Novelty | 15% | Specific data points, non-trivial insights |
| Accuracy | 15% | Source attribution, appropriate hedging |

## Configuration

- Max iterations: 5 (safety cap)
- Quality threshold: 0.75 (configurable)
- Sources: arXiv (10), Semantic Scholar (10), bioRxiv (recent 30 days)

## Output

Returns structured research report with:
- Introduction, methodology, findings, discussion, conclusion
- Numbered citations with paper metadata
- Gap analysis from failed iterations
- Quality score breakdown

## Estimated Duration

15-50 minutes depending on topic complexity and convergence speed.
