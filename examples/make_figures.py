"""Regenerate docs/img/*.png used in the README.

    python -m examples.make_figures
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from verify import spec  # noqa: E402
from verify.backtest import run  # noqa: E402
from verify.data import load_daily  # noqa: E402
from verify.null import random_null  # noqa: E402

INK, MUTED, ACCENT, NULLC = "#1f2933", "#7b8794", "#c2410c", "#9aa5b1"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "white", "axes.facecolor": "white"})
os.makedirs("docs/img", exist_ok=True)

data = {s: load_daily(s, start=spec.START) for s in spec.UNIVERSE}
r = run(data)
c = r["curve"]

fig, ax = plt.subplots(figsize=(8, 3.2))
ax.plot(c.index, c.values, color=INK, lw=1.4)
ax.set_yscale("log")
ax.set_yticks([1, 2, 3, 4, 6])
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}x"))
ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
ax.set_ylabel("equity multiple (log)")
ax.set_title("Example Donchian, 6 coins, daily, costs included (in-sample)", color=INK, loc="left", fontsize=10)
for y in ("2024-01-01", "2025-01-01"):
    ax.axvline(np.datetime64(y), color=MUTED, lw=0.8, ls="--")
    ax.text(np.datetime64(y), c.max(), f" {y[:4]}+", color=MUTED, va="top", fontsize=8)
fig.tight_layout()
fig.savefig("docs/img/equity.png", dpi=150)

n = random_null(data, n_draws=2000)
fig, ax = plt.subplots(figsize=(8, 3.2))
ax.hist(n["draws"] * 100, bins=50, color=NULLC)
ax.axvline(n["actual"] * 100, color=ACCENT, lw=2)
ax.text(n["actual"] * 100, ax.get_ylim()[1] * 0.92, f"  signal {n['actual']*100:+.2f}%\n  ({n['percentile']:.1f} pct)",
        color=ACCENT, va="top", fontsize=9)
ax.set_xlabel("mean return per trade after costs, %")
ax.set_ylabel("random draws")
ax.set_title("Same rules, random entry days (2,000 draws) vs the signal", color=INK, loc="left", fontsize=10)
fig.tight_layout()
fig.savefig("docs/img/null.png", dpi=150)
print("wrote docs/img/equity.png, docs/img/null.png")
