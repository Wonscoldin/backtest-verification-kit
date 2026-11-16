"""Anchored walk-forward: how much of the in-sample result survives when parameters are chosen
only with data that existed at the time?

For each test year Y: pick the grid cell with the best EV on [start, Y), then record that cell's returns
in year Y. Chaining the test years gives an out-of-sample curve. The headline is the ratio
    out-of-sample CAGR / in-sample CAGR of the cell that is best over the whole period
-- the haircut to apply before planning with a backtest number.

Selection is by the objective (EV), not by a proxy. If the chosen cell sits on the edge of the grid,
the grid was too small and the ratio is a bound, not an estimate -- the report says so.
The simulator is causal, so one full-period run per cell can be sliced by date (a test locks this).
"""
from __future__ import annotations

import itertools
from typing import Dict, Iterable

import numpy as np
import pandas as pd

from .backtest import run
from .ev import block_bootstrap_ev


def _cagr(r: pd.Series) -> float:
    return ((1 + r).prod() ** (365.25 / len(r)) - 1) * 100 if len(r) else np.nan


def grid_curves(data: Dict[str, pd.DataFrame], grid: Dict[str, Iterable]) -> Dict[tuple, pd.Series]:
    keys = list(grid)
    out = {}
    for vals in itertools.product(*(grid[k] for k in keys)):
        out[vals] = run(data, **dict(zip(keys, vals)))["curve"].pct_change().dropna()
    return out


def anchored(data: Dict[str, pd.DataFrame], grid: Dict[str, Iterable], test_years: Iterable[int],
             ev_draws: int = 500, seed: int = 0) -> dict:
    keys = list(grid)
    curves = grid_curves(data, grid)
    folds, oos = [], []
    for y in test_years:
        fit_end, t0, t1 = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
        scores = {k: block_bootstrap_ev(r.loc[:fit_end - pd.Timedelta(days=1)], n=ev_draws, seed=seed)
                  for k, r in curves.items()}
        best = max(scores, key=scores.get)
        test = curves[best].loc[t0:t1 - pd.Timedelta(days=1)]
        edge = [k for k, v in zip(keys, best) if v in (min(grid[k]), max(grid[k]))]
        folds.append(dict(test_year=y, chosen=dict(zip(keys, best)), fit_ev=scores[best],
                          test_cagr=_cagr(test), test_days=len(test), on_grid_edge=edge))
        oos.append(test)
    oos_r = pd.concat(oos)
    first = oos_r.index[0]
    is_best = max(curves, key=lambda k: _cagr(curves[k].loc[first:]))
    is_cagr = _cagr(curves[is_best].loc[first:])
    return dict(folds=pd.DataFrame(folds), oos_cagr=_cagr(oos_r), in_sample_best=dict(zip(keys, is_best)),
                in_sample_cagr=is_cagr, ratio=_cagr(oos_r) / is_cagr if is_cagr else np.nan, oos_returns=oos_r)
