#!/usr/bin/env python3
"""
Benchmark script — verify model fits in 16MB and estimate BPB.
Runs on MPS (Mac mini) or CPU. No GPU required.

Usage:
  python benchmark.py                    # Build model, check size, run dummy forward
  python benchmark.py --profile          # Profile memory + speed
  python benchmark.py --compare-activations  # Compare LeakyReLU² vs GELU vs SiLU
"""
import argparse
import math
import os
import sys
import time

import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(__file__))
from train_gpt import Config, ParameterGolfLM, EMA, quantize_int6, save_quantized, LeakyReLUSquared


def check_budget(cfg: Config):
    """Verify model fits in the 16MB artifact budget."""
    model = ParameterGolfLM(cfg)
    n_params = model.count_parameters()

    sizes = {}
    for bits in [4, 6, 8, 16]:
        sizes[f"Int{bits}"] = n_params * bits // 8

    code_size = 15_000  # train_gpt.py estimate
    tokenizer_size = 20_000

    print("=" * 50)
    print("PARAMETER GOLF BUDGET CHECK")
    print("=" * 50)
    print(f"Parameters:      {n_params:>12,}")
    print(f"Virtual layers:  {cfg.n_virtual_layers:>12} ({cfg.n_unique_layers} unique × {cfg.n_recurrence} recurrence)")
    print(f"d_model:         {cfg.d_model:>12}")
    print(f"n_heads:         {cfg.n_heads:>12}")
    print(f"MLP dim:         {cfg.mlp_dim:>12}")
    print(f"Vocab:           {cfg.vocab_size:>12}")
    print()
    print("Estimated artifact sizes:")
    for name, size in sizes.items():
        total = size + code_size + tokenizer_size
        status = "OK" if total <= 16_000_000 else "OVER"
        headroom = 16_000_000 - total
        print(f"  {name:>6}: {total:>12,} bytes  ({total/1e6:>5.1f} MB)  "
              f"[{status}]  headroom: {headroom:>10,} bytes")

    print()
    target_bits = cfg.quantize_bits
    target_size = sizes[f"Int{target_bits}"] + code_size + tokenizer_size
    print(f"Target (Int{target_bits}): {target_size:,} bytes — "
          f"{'FITS' if target_size <= 16_000_000 else 'DOES NOT FIT'}")

    return model


def profile_forward(model, cfg: Config, device: str = "cpu", n_runs: int = 10):
    """Profile forward pass speed and memory."""
    model = model.to(device)
    model.eval()

    input_ids = torch.randint(0, cfg.vocab_size, (1, cfg.max_seq_len), device=device)

    # Warmup
    with torch.no_grad():
        for _ in range(3):
            model(input_ids)

    # Time forward passes
    if device == "cuda":
        torch.cuda.synchronize()
    t0 = time.time()
    with torch.no_grad():
        for _ in range(n_runs):
            logits, _ = model(input_ids)
    if device == "cuda":
        torch.cuda.synchronize()
    elapsed = (time.time() - t0) / n_runs

    tokens_per_sec = cfg.max_seq_len / elapsed

    print(f"\nForward pass ({device}):")
    print(f"  Latency:     {elapsed*1000:.1f} ms")
    print(f"  Throughput:  {tokens_per_sec:.0f} tokens/s")
    print(f"  Seq length:  {cfg.max_seq_len}")

    if device == "cuda":
        mem = torch.cuda.max_memory_allocated() / 1e6
        print(f"  Peak GPU:    {mem:.0f} MB")
    elif device == "mps":
        # MPS doesn't have max_memory_allocated
        print(f"  MPS device:  Apple Silicon")

    return elapsed


def compare_activations(cfg: Config, device: str = "cpu"):
    """Compare LeakyReLU² vs GELU vs SiLU on forward speed."""
    activations = {
        "LeakyReLU2": LeakyReLUSquared(),
        "GELU": nn.GELU(),
        "SiLU": nn.SiLU(),
        "ReLU": nn.ReLU(),
    }

    x = torch.randn(cfg.batch_size, cfg.max_seq_len, cfg.mlp_dim, device=device)
    n_runs = 100

    print("\nActivation comparison (forward pass):")
    print(f"  Input: ({cfg.batch_size}, {cfg.max_seq_len}, {cfg.mlp_dim})")
    print(f"  Device: {device}")
    print()

    for name, act in activations.items():
        act = act.to(device)
        # Warmup
        for _ in range(5):
            act(x)

        t0 = time.time()
        for _ in range(n_runs):
            act(x)
        elapsed = (time.time() - t0) / n_runs

        print(f"  {name:>12}: {elapsed*1000:.3f} ms")


def test_quantization(model, cfg: Config):
    """Test GPTQ-lite quantization and verify compressed size."""
    print("\nQuantization test:")
    quantized = quantize_int6(model)

    # Save to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        size = save_quantized(quantized, f.name)
        print(f"  Quantized file: {size:,} bytes ({size/1e6:.1f} MB)")
        print(f"  Code estimate:  ~15,000 bytes")
        print(f"  Total artifact: {size + 15000:,} bytes")
        print(f"  Budget:         16,000,000 bytes")
        print(f"  Headroom:       {16_000_000 - size - 15000:,} bytes")
        os.unlink(f.name)

    # Verify reconstruction quality
    model.eval()
    input_ids = torch.randint(0, cfg.vocab_size, (1, 64))
    with torch.no_grad():
        logits_fp, _ = model(input_ids)

    # Rough reconstruction error estimate
    total_error = 0
    n_params = 0
    for name, param in model.named_parameters():
        if name in quantized:
            q = quantized[name]
            reconstructed = (q["data"].float() * q["scale"].float() +
                           q["scale"].float() * (-q["zero_point"].float()))
            error = (param.data.float() - reconstructed).abs().mean().item()
            total_error += error
            n_params += 1

    if n_params:
        print(f"  Avg quantization error: {total_error/n_params:.6f}")


def test_depth_recurrence(cfg: Config):
    """Verify depth recurrence produces different outputs per pass."""
    model = ParameterGolfLM(cfg)
    model.eval()

    input_ids = torch.randint(0, cfg.vocab_size, (1, 32))

    # Hook to capture intermediate activations
    activations = []

    def hook_fn(module, input, output):
        activations.append(output.detach().clone())

    # Register hook on first layer
    model.layers[0].register_forward_hook(hook_fn)

    with torch.no_grad():
        model(input_ids)

    print(f"\nDepth recurrence test:")
    print(f"  Physical layers: {cfg.n_unique_layers}")
    print(f"  Recurrence: {cfg.n_recurrence}x")
    print(f"  Virtual layers: {cfg.n_virtual_layers}")
    print(f"  Layer 0 activations captured: {len(activations)} passes")

    if len(activations) >= 2:
        diff = (activations[0] - activations[1]).abs().mean().item()
        print(f"  Pass 1 vs Pass 2 diff: {diff:.6f} (should be > 0)")
        diff2 = (activations[1] - activations[2]).abs().mean().item() if len(activations) > 2 else 0
        print(f"  Pass 2 vs Pass 3 diff: {diff2:.6f}")


def test_ema(cfg: Config):
    """Verify EMA smooths weights correctly."""
    model = ParameterGolfLM(cfg)
    ema = EMA(model, decay=0.999)

    # Simulate training steps
    for _ in range(100):
        for p in model.parameters():
            p.data.add_(torch.randn_like(p) * 0.01)
        ema.update(model)

    # Check EMA is different from current weights
    diff = 0
    for (name, p), (_, s) in zip(model.named_parameters(), ema.shadow.items()):
        diff += (p.data - s).abs().mean().item()

    print(f"\nEMA test (100 steps, decay=0.999):")
    print(f"  Avg weight diff (model vs EMA): {diff/len(list(model.parameters())):.6f}")
    print(f"  EMA should be smoother (lower variance)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--compare-activations", action="store_true")
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    cfg = Config()

    # Auto-detect device
    if args.device:
        device = args.device
    elif torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    # Always run budget check
    model = check_budget(cfg)

    if args.compare_activations:
        compare_activations(cfg, device)
    elif args.profile:
        profile_forward(model, cfg, device)
        test_quantization(model, cfg)
    else:
        # Full benchmark suite
        test_depth_recurrence(cfg)
        test_ema(cfg)
        test_quantization(model, cfg)
        profile_forward(model, cfg, device)

    print("\nDone.")
