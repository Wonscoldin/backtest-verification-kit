"""Decide with the objective, not a proxy: expected wealth multiple over a horizon (block bootstrap).

Also report it with the single best day removed -- an average can pass every gate while half of the
gain is one day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def block_bootstrap_ev(daily_returns: pd.Series, years: float = 3.0, block: int = 20, n: int = 4000, seed: int = 0) -> float:
    v = np.asarray(daily_returns, float)
    rng = np.random.default_rng(seed)
    T, N = int(365.25 * years), len(v)
    out = np.empty(n)
    for k in range(n):
        idx = []
        while len(idx) < T:
            s = rng.integers(0, N - block + 1)
            idx.extend(range(s, s + block))
        out[k] = np.prod(1.0 + v[idx[:T]])
    return float(out.mean())


def ev_report(curve: pd.Series, windows=(None, "2024-01-01", "2025-01-01"), **kw) -> pd.DataFrame:
    r = curve.pct_change().dropna()
    rows = []
    for w in windows:
        x = r if w is None else r.loc[w:]
        rows.append(dict(window=w or "all", days=len(x), ev=block_bootstrap_ev(x, **kw),
                         ev_ex_best_day=block_bootstrap_ev(x.drop(x.idxmax()), **kw)))
    return pd.DataFrame(rows)
