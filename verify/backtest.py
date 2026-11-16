"""Canonical simulator. One function, `run()`; variants are keyword arguments.

Bar-order rules (each one is a past incident, see docs/INCIDENTS.md):
  * Signals use bar t's close; the earliest fill is bar t+1. Nothing reads bar t+1 before that.
  * Inside one bar the order is FILL FIRST, THEN STOP. A limit order that fills and is stopped in the
    same bar is a real (and usually the worst) trade -- dropping it inflates results.
  * A stop hit on a gap fills at the open, not at the stop price.
  * Same-day entries are processed in a fixed, documented order (spec.UNIVERSE order), never by
    dict/alphabetical accident.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import spec


@dataclass
class Trade:
    symbol: str
    signal_day: pd.Timestamp
    entry_day: pd.Timestamp
    exit_day: pd.Timestamp
    entry: float
    stop: float
    exit: float
    reason: str          # "stop" | "time"

    @property
    def ret(self) -> float:
        return self.exit / self.entry - 1.0


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def signals(df: pd.DataFrame, entry_lookback: int) -> pd.Series:
    """True on bar t if close[t] breaks the highest high of the previous `entry_lookback` bars (t excluded)."""
    return df["close"] > df["high"].shift(1).rolling(entry_lookback).max()


def symbol_trades(sym: str, df: pd.DataFrame, entry_lookback: int, atr_len: int, stop_atr: float, hold_bars: int,
                  entry: str = "market", limit_offset: float = 0.0, entry_days: Optional[List[int]] = None) -> List[Trade]:
    """Trades for one symbol, one position at a time. `entry_days` (bar indices) overrides the signal --
    used by the random null so that the null shares every other rule with the real strategy."""
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    a = atr(df, atr_len).to_numpy()
    sig = signals(df, entry_lookback).to_numpy() if entry_days is None else np.isin(np.arange(len(df)), entry_days)
    out, t, n = [], 0, len(df)
    while t < n - 1:
        if not sig[t] or np.isnan(a[t]):
            t += 1
            continue
        e = t + 1
        if entry == "market":
            px = o[e]
        else:                                           # limit below the signal close
            lim = c[t] * (1.0 - limit_offset)
            if l[e] > lim:                              # not filled -> signal expires
                t += 1
                continue
            px = min(o[e], lim)
        stop = px - stop_atr * a[t]
        last = min(e + hold_bars - 1, n - 1)
        exit_px, reason, x = c[last], "time", last
        for b in range(e, last + 1):                    # bar e included: fill first, then stop
            if l[b] <= stop:
                exit_px = stop if b == e else min(stop, o[b])
                reason, x = "stop", b
                break
        out.append(Trade(sym, df.index[t], df.index[e], df.index[x], px, stop, exit_px, reason))
        t = x + 1                                       # one position per symbol
    return out


def portfolio(trades: List[Trade], closes: Dict[str, pd.Series], cost_rt: float, risk: float, max_pos: int,
              order: tuple) -> tuple:
    """Risk-based sizing, max concurrent positions, daily mark-to-market equity curve.

    Each position is capped at 50% of equity, so with `max_pos` > 2 the book can exceed 1x (cash goes negative,
    i.e. margin, as on a perpetuals account). Funding/borrow on that margin is not charged -- see KNOWN_OPTIMISM.
    """
    rank = {s: i for i, s in enumerate(order)}
    by_day: Dict[pd.Timestamp, List[Trade]] = {}
    for tr in sorted(trades, key=lambda x: (x.entry_day, rank.get(x.symbol, 1e9))):
        by_day.setdefault(tr.entry_day, []).append(tr)
    days = sorted(set().union(*[set(s.index) for s in closes.values()]))
    cash, open_, taken, curve = 1.0, [], [], []
    for d in days:
        for tr in by_day.get(d, []):
            if len(open_) >= max_pos or any(p["t"].symbol == tr.symbol for p in open_):
                continue
            eq = cash + sum(p["q"] * closes[p["t"].symbol].get(d, p["t"].entry) for p in open_)
            dist = (tr.entry - tr.stop) / tr.entry
            notional = min(eq * risk / max(dist, 1e-9), eq * 0.5)
            q = notional / tr.entry
            cash -= q * tr.entry + notional * cost_rt / 2
            open_.append({"t": tr, "q": q})
            taken.append(tr)
        for p in [p for p in open_ if p["t"].exit_day == d]:
            cash += p["q"] * p["t"].exit - p["q"] * p["t"].exit * cost_rt / 2
            open_.remove(p)
        curve.append(cash + sum(p["q"] * closes[p["t"].symbol].get(d, p["t"].entry) for p in open_))
    return pd.Series(curve, index=pd.DatetimeIndex(days)), taken


def run(data: Dict[str, pd.DataFrame], cost_rt: float = spec.COST_RT, risk: float = spec.RISK_PER_TRADE,
        max_pos: int = spec.MAX_POSITIONS, entry: str = "market", limit_offset: float = 0.0, **strategy_overrides) -> dict:
    """The canonical run. Override one knob at a time: run(data, stop_atr=3.0)."""
    p = {**spec.STRATEGY, **strategy_overrides}
    trades = [t for s, df in data.items() for t in symbol_trades(s, df, entry=entry, limit_offset=limit_offset, **p)]
    curve, taken = portfolio(trades, {s: df["close"] for s, df in data.items()}, cost_rt, risk, max_pos, tuple(data))
    r = curve.pct_change().dropna()
    yrs = len(r) / 365.25
    return dict(curve=curve, trades=taken, candidates=trades, params=p,
                cagr=(curve.iloc[-1] ** (1 / yrs) - 1) * 100 if yrs > 0 else np.nan,
                mdd=((curve / curve.cummax()) - 1).min() * 100,
                known_optimism=spec.KNOWN_OPTIMISM)
