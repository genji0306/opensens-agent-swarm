---
name: darklab-parameter-golf
version: 1.0.0
description: Train a compressed language model under 16MB with maximum quality (bits-per-byte) — implements the DarkLab research debate solution for OpenAI's Parameter Golf challenge
execution_mode: PLAYBOOK
allowed_tools:
  - bash
  - python
  - file_write
  - file_read
tags:
  - ml
  - compression
  - language-model
  - quantization
  - training
---

# Parameter Golf Skill

Train the best language model that fits in a 16MB artifact, optimized for bits-per-byte on FineWeb validation data.

## Strategy: Deep-Narrow Recurrent Transformer

Based on DarkLab research debate (61 papers + leaderboard analysis):

### Architecture

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| d_model | 384 | Narrow saves params; depth > width for small models |
| n_heads | 6 | 64 dim/head is the sweet spot |
| n_unique_layers | 4 | Physical transformer blocks |
| n_virtual_layers | 12 | 3x depth recurrence (free parameters) |
| MLP ratio | 3x | Int6 quantized, LeakyReLU² activation |
| Position encoding | Partial RoPE | Half dimensions only |
| Attention | XSA4 | Extended sparse, 4-group |
| Vocab size | 4096 | Tiny BPE tokenizer = more weight budget |
| Quantization | Int6 (GPTQ-lite) | 0.75 bytes/param |

### Parameter Budget

```
Total: 16,000,000 bytes
Code:        ~15,000 bytes
Tokenizer:   ~20,000 bytes
Weights:  ~5,600,000 bytes (7.5M params @ Int6)
EMA copy: ~5,600,000 bytes
Headroom: ~4,765,000 bytes
```

### Training Schedule (10 min on 8xH100)

```
Phase 1 (0-3 min):  Warmup — lr 0→6e-4, Parallel Muon, 262M tokens
Phase 2 (3-8 min):  Main — lr 6e-4→1e-4 cosine, EMA α=0.999, 419M tokens
Phase 3 (8-10 min): Warmdown — lr→0, switch to EMA, GPTQ-lite Int6
```

### Test-Time Training (Score-First TTT)

During evaluation:
1. Forward pass on 1024-token chunk → score all tokens
2. Gradient step on first 512 tokens (already evaluated)
3. Predict remaining 512 tokens with updated weights
4. Repeat with sliding window

Expected improvement: -0.02 to -0.04 BPB.

## Usage

```bash
# Train locally (1xH100 or MPS fallback)
python scripts/train_gpt.py --config scripts/config.yaml

# Train on 8xH100
torchrun --standalone --nproc_per_node=8 scripts/train_gpt.py

# Evaluate
python scripts/train_gpt.py --eval-only --checkpoint model.pt

# Package submission
python scripts/package.py --output submission/
```

## Key Techniques

1. **Depth Recurrence**: 4 physical layers reused 3x = 12 effective layers. Weight sharing means 3x fewer parameters for the same depth.

2. **LeakyReLU²**: `max(0.01*x, x)²` — cheaper than GELU, better gradients for small models. The squaring adds expressiveness without extra parameters.

3. **Parallel Muon Optimizer**: Converges 2x faster than AdamW for sub-10M parameter models. Uses momentum=0.95, weight_decay=0.1.

4. **GPTQ-lite Quantization**: Post-training quantization to Int6 with layer-wise calibration. Saves 25% over Int8 with <0.5% quality loss.

5. **Partial RoPE**: Apply rotary embeddings to only half the head dimensions. The other half uses absolute position — saves compute, negligible quality impact.

6. **XSA4 (Extended Sparse Attention)**: Groups heads into 4 sets with different attention patterns (local, strided, global, random). Reduces O(n²) to O(n·√n).

7. **EMA Weight Averaging**: Exponential moving average with α=0.999 acts as implicit regularization. Switch to EMA weights during warmdown.

## Novel Ideas (Untested)

- **Mixture of Depth**: Skip layers for easy tokens — adaptive compute
- **Byte-Level Fallback**: BPE for common tokens, byte-level for rare — better tail BPB
- **Spectral Reparameterization**: SVD-based weight matrices for smoother quantization
- **Progressive Quantization**: Gradually reduce precision during warmdown

## Expected Performance

```
Baseline (naive 9L, 512d):    1.2244 BPB
Current SOTA:                 1.1194 BPB
Without TTT:                  1.1150 BPB (estimated)
With Score-First TTT:         1.1080 BPB (estimated)
```

## References

- Fan et al. (2020) — Training with Quantization Noise for Extreme Model Compression
- PB-LLM — Partially Binarized Large Language Models
- Parameter Golf leaderboard: abaybektursun (1.1194), signalrush (1.1228), jfprincz (1.1248)
- DarkLab Deep Research: 61 papers from arXiv, PubMed, OpenAlex, CrossRef, DOAJ, EuropePMC
