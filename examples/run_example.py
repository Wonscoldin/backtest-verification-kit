"""End-to-end: public data -> canonical run -> random null -> EV by window.

    python -m examples.run_example
"""
from verify import spec
from verify.backtest import run
from verify.data import load_daily
from verify.ev import ev_report
from verify.null import random_null

data = {s: load_daily(s, start=spec.START) for s in spec.UNIVERSE}
r = run(data)
print(f"Example Donchian (long only), {r['curve'].index[0]:%Y-%m-%d} ~ {r['curve'].index[-1]:%Y-%m-%d}")
print(f"  CAGR {r['cagr']:.1f}% | MDD {r['mdd']:.1f}% | trades {len(r['trades'])} (candidates {len(r['candidates'])})")
print("  known optimism:", *r["known_optimism"], sep="\n    - ")

n = random_null(data, n_draws=500)
print(f"\nRandom-entry null (same symbols, count, stop, hold, cost): actual {n['actual']*100:+.2f}%/trade "
      f"vs null {n['null_mean']*100:+.2f} +/- {n['null_sd']*100:.2f} -> {n['percentile']:.1f} percentile")

print("\n3-year EV (wealth multiple, 20-day block bootstrap):")
print(ev_report(r["curve"], n=1000).to_string(index=False))
