"""Random-entry null: is the signal better than entering at random with every OTHER rule identical?

A threshold you set before knowing the null's spread will call noise a difference (or the reverse).
So the gate is a percentile against the null, not an absolute number.
Same symbol, same number of entries, same stop/hold/cost -- only the entry days are random. This keeps
trend drift and holding-period effects in the null, so beating it means the *selection* adds value.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from . import spec
from .backtest import symbol_trades


def mean_trade_return(trades, cost_rt: float) -> float:
    return float(np.mean([t.ret - cost_rt for t in trades])) if trades else np.nan


def random_null(data: Dict[str, pd.DataFrame], n_draws: int = 2000, seed: int = 0, cost_rt: float = spec.COST_RT,
                **strategy_overrides) -> dict:
    p = {**spec.STRATEGY, **strategy_overrides}
    rng = np.random.default_rng(seed)
    real = {s: symbol_trades(s, df, **p) for s, df in data.items()}
    actual = mean_trade_return([t for v in real.values() for t in v], cost_rt)
    warm = p["entry_lookback"] + p["atr_len"]
    draws = np.empty(n_draws)
    for k in range(n_draws):
        pool = []
        for s, df in data.items():
            n = len(real[s])
            if n == 0:
                continue
            days = rng.choice(np.arange(warm, len(df) - 1), size=n * 2, replace=False)
            pool += symbol_trades(s, df, entry_days=np.sort(days), **p)[:n]
        draws[k] = mean_trade_return(pool, cost_rt)
    return dict(actual=actual, null_mean=float(np.nanmean(draws)), null_sd=float(np.nanstd(draws)),
                percentile=float((draws < actual).mean() * 100), draws=draws)
