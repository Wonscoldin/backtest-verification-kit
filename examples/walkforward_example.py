"""Anchored walk-forward on the example strategy.

    python -m examples.walkforward_example
"""
from verify import spec
from verify.data import load_daily
from verify.walkforward import anchored

GRID = {"entry_lookback": (10, 20, 40, 55), "stop_atr": (1.5, 2.0, 3.0)}     # 12 cells, all counted

data = {s: load_daily(s, start=spec.START) for s in spec.UNIVERSE}
w = anchored(data, GRID, test_years=(2022, 2023, 2024, 2025, 2026))
print(w["folds"].to_string(index=False))
print(f"\nOut-of-sample CAGR (chained test years): {w['oos_cagr']:.1f}%")
print(f"In-sample best cell over the same years {w['in_sample_best']}: {w['in_sample_cagr']:.1f}%")
print(f"Walk-forward ratio: {w['ratio']:.2f}  -> plan with backtest x {w['ratio']:.2f}, not the backtest")
if w["folds"]["on_grid_edge"].map(bool).any():
    print("Note: some folds chose a grid edge, so the ratio is a bound rather than an estimate.")
