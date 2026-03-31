"""
Parameter Golf configurations — from conservative to budget-maxing.

Each config targets a different artifact size / quality tradeoff.
Run: python benchmark.py --config <name>
"""
from train_gpt import Config


# Original: 5.6 MB artifact (lots of headroom)
CONSERVATIVE = Config(
    d_model=384,
    n_heads=6,
    n_unique_layers=4,
    n_recurrence=3,
    mlp_ratio=3.0,
    vocab_size=4096,
)

# Medium: ~10 MB artifact (balanced)
BALANCED = Config(
    d_model=512,
    n_heads=8,
    n_unique_layers=4,
    n_recurrence=3,
    mlp_ratio=3.0,
    vocab_size=4096,
)

# Aggressive: ~14 MB artifact (near budget limit)
AGGRESSIVE = Config(
    d_model=576,
    n_heads=9,
    n_unique_layers=5,
    n_recurrence=3,
    mlp_ratio=3.5,
    vocab_size=4096,
)

# Max budget: ~15.5 MB (pushing the limit)
MAX_BUDGET = Config(
    d_model=640,
    n_heads=10,
    n_unique_layers=5,
    n_recurrence=3,
    mlp_ratio=3.5,
    vocab_size=4096,
)

# Deep and narrow: many virtual layers, small width
DEEP_NARROW = Config(
    d_model=384,
    n_heads=6,
    n_unique_layers=3,
    n_recurrence=5,  # 15 virtual layers!
    mlp_ratio=3.0,
    vocab_size=4096,
)

# Wide and shallow: fewer layers, more width
WIDE_SHALLOW = Config(
    d_model=768,
    n_heads=12,
    n_unique_layers=3,
    n_recurrence=2,  # 6 virtual layers
    mlp_ratio=2.5,
    vocab_size=4096,
)

# Int4 extreme: larger model quantized harder
INT4_EXTREME = Config(
    d_model=768,
    n_heads=12,
    n_unique_layers=5,
    n_recurrence=3,
    mlp_ratio=3.0,
    vocab_size=4096,
    quantize_bits=4,
)

CONFIGS = {
    "conservative": CONSERVATIVE,
    "balanced": BALANCED,
    "aggressive": AGGRESSIVE,
    "max_budget": MAX_BUDGET,
    "deep_narrow": DEEP_NARROW,
    "wide_shallow": WIDE_SHALLOW,
    "int4_extreme": INT4_EXTREME,
}


def print_comparison():
    """Print a comparison table of all configs."""
    print(f"{'Config':<16} {'d_model':>7} {'heads':>5} {'layers':>7} "
          f"{'virtual':>7} {'params':>12} {'Int6 MB':>8} {'Int4 MB':>8} {'status':>8}")
    print("-" * 90)

    for name, cfg in CONFIGS.items():
        from train_gpt import ParameterGolfLM
        model = ParameterGolfLM(cfg)
        n = model.count_parameters()
        int6 = n * 6 // 8 + 35000
        int4 = n * 4 // 8 + 35000
        bits = cfg.quantize_bits
        target = n * bits // 8 + 35000
        status = "OK" if target <= 16_000_000 else "OVER"

        print(f"{name:<16} {cfg.d_model:>7} {cfg.n_heads:>5} "
              f"{cfg.n_unique_layers:>3}×{cfg.n_recurrence:<3} "
              f"{cfg.n_virtual_layers:>7} {n:>12,} {int6/1e6:>7.1f} {int4/1e6:>7.1f} "
              f"{'[' + status + ']':>8}")
        del model


if __name__ == "__main__":
    print_comparison()
