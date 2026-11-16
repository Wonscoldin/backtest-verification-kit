"""Measure live execution cost against the backtest's assumption.

The reference price decides what you are measuring:
  * limit order   -> the order's own price
  * stop / take-profit -> the TRIGGER price (what the backtest assumes), NOT the mark price at fill time.
    Measuring stops against the mark price once showed a round trip of 15.3bp; against the trigger it was 8.0bp.
  * market order  -> mid/mark at submission
Fills without a usable reference are counted and excluded, never silently priced at 0.
"""
from __future__ import annotations

import pandas as pd


def slippage_bps(fills: pd.DataFrame) -> pd.DataFrame:
    """fills: columns side ('buy'/'sell'), kind ('limit'/'stop'/'tp'/'market'), fill_price, ref_price, fee_bps.
    Positive slippage = worse than reference."""
    f = fills.copy()
    sign = f["side"].map({"buy": 1.0, "sell": -1.0})
    f["ref_ok"] = f["ref_price"].fillna(0) > 0
    f["slip_bps"] = sign * (f["fill_price"] / f["ref_price"] - 1.0) * 1e4
    f.loc[~f["ref_ok"], "slip_bps"] = float("nan")
    return f


def summary(fills: pd.DataFrame, assumed_rt_bps: float) -> dict:
    f = slippage_bps(fills)
    ok = f[f["ref_ok"]]
    per_side = (ok["slip_bps"] + ok["fee_bps"]).mean()
    return dict(n=len(f), no_reference=int((~f["ref_ok"]).sum()), round_trip_bps=2 * per_side,
                fee_rt_bps=2 * ok["fee_bps"].mean(), slip_rt_bps=2 * ok["slip_bps"].mean(),
                assumed_rt_bps=assumed_rt_bps, within_assumption=bool(2 * per_side <= assumed_rt_bps))
