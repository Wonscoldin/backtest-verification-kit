"""Implementation shortfall: on the trades the live system actually took, where did money leak versus the
backtest's reference prices?  (weekly report since 2026-11-16)

Why: live-vs-backtest monitoring was signal-level only (did live see the signal? if it skipped, does the
backtest know that reason?). Nobody measured *how much leaked inside the trades that were taken* -- entry
price, exit timing, fees, funding. Professional desks look at this every week.

Rule: do NOT re-simulate how the backtest would have exited (that would be a second simulator). Take the way
the live trade actually exited and compare it only with the backtest's reference price for that exit:
  reference entry = the planned limit price logged at order time (market-entry strategies: signal-bar close)
  reference exit  = stop / take-profit -> trigger price
                    holding-period expiry -> open of the bar at the backtest's expiry time
                    anything else (more than one bar from expiry: drawdown cuts, manual) -> "other", cost 0
Dollars, + = worse than the reference:
  entry_cost = dir * (avg entry - reference entry) * qty
  exit_cost  = dir * (reference exit - avg exit) * qty
  ideal      = dir * (reference exit - reference entry) * qty     (same size at reference prices, zero cost)
  live_net   = exchange closed P&L - funding
  identity:  live_net = ideal - entry_cost - exit_cost - fees - funding   (residual = rounding / partial fills)
"""
from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional

import pandas as pd

ASSUMED_RT = 0.0011
# bar length per strategy in minutes (default daily) and strategies whose hold counts calendar days
LEG_BAR_MIN = {"cbp4h": 240, "s5": 60, "bos": 60}
CAL_DAY_HOLD = {"gold_index"}


def journal_places(lines: Iterable[str], account_prefix: str = "Exchange-") -> pd.DataFrame:
    """PLACE decisions from the decision journal. Strategy = the part after the account prefix."""
    rows = []
    for ln in lines:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        acct = str(d.get("account") or "")
        if d.get("event") != "decision" or d.get("action") != "PLACE" or not acct.startswith(account_prefix):
            continue
        ref = d.get("planned_limit_price") or d.get("reference_close")
        rows.append({"t": pd.Timestamp(d["logged_at"]), "symbol": d.get("symbol"), "side": d.get("side"),
                     "leg": acct[len(account_prefix):], "ref_entry": float(ref) if ref else None,
                     "stop": d.get("stop_price"),
                     "signal_time": pd.Timestamp(d["signal_time"]) if d.get("signal_time") else None,
                     "attempt_id": d.get("attempt_id")})
    return pd.DataFrame(rows)


def trades(closed: List[dict], execs: List[dict], places: pd.DataFrame) -> pd.DataFrame:
    """One exchange closed-P&L row = one exit order. Attach the entry fills, the journal PLACE and the exit type."""
    ex = pd.DataFrame(execs)
    if not closed or ex.empty:
        return pd.DataFrame()
    ex["t"] = pd.to_datetime(ex["execTime"].astype("int64"), unit="ms", utc=True)
    ex["closedSize"] = pd.to_numeric(ex["closedSize"], errors="coerce").fillna(0)
    tr = ex[ex.get("execType", "Trade") == "Trade"]
    ctype = tr.groupby("orderId")["createType"].first().to_dict()
    opens = tr[tr["closedSize"] <= 0]
    fund = ex[ex["execType"] == "Funding"].copy()
    fund["execFee"] = pd.to_numeric(fund["execFee"], errors="coerce")
    out = []
    for r in closed:
        sym = r["symbol"]
        t_close = pd.to_datetime(int(r["updatedTime"]), unit="ms", utc=True)
        side = "long" if r["side"] == "Sell" else "short"      # the exit order's side is opposite to the position
        o_side = "Buy" if side == "long" else "Sell"
        op = opens[(opens["symbol"] == sym) & (opens["side"] == o_side) & (opens["t"] <= t_close)]
        if op.empty:
            continue
        t_open = op["t"].max()
        pl = places[(places["symbol"] == sym) & (places["side"] == side) & (places["t"] <= t_open + pd.Timedelta(minutes=5))] \
            if not places.empty else places
        p = pl.sort_values("t").iloc[-1] if len(pl) else None
        qty = float(r["closedSize"] or r["qty"])
        share = qty / max(float(r["qty"]) or qty, 1e-12)
        f = fund[(fund["symbol"] == sym) & (fund["t"] > t_open) & (fund["t"] <= t_close)]
        out.append({"symbol": sym, "side": side, "dir": 1.0 if side == "long" else -1.0, "qty": qty,
                    "t_open": t_open, "t_close": t_close, "close_oid": r["orderId"],
                    "close_type": ctype.get(r["orderId"], ""),
                    "entry": float(r["avgEntryPrice"]), "exit": float(r["avgExitPrice"]),
                    "entry_value": float(r["cumEntryValue"]) * share,
                    "fees": float(r.get("openFee") or 0) + float(r.get("closeFee") or 0),
                    "closed_pnl": float(r["closedPnl"]), "funding": float(f["execFee"].sum()) * share,
                    "leg": (p["leg"] if p is not None else None), "ref_entry": (p["ref_entry"] if p is not None else None),
                    "signal_time": (p["signal_time"] if p is not None else None)})
    return pd.DataFrame(out)


def canon_expiry(leg: str, signal_time: pd.Timestamp, hold: int) -> Optional[pd.Timestamp]:
    """Backtest expiry = signal bar start + one bar (entry) + hold. Some assets count hold in calendar days."""
    if signal_time is None or pd.isna(signal_time) or not hold:
        return None
    bar = pd.Timedelta(minutes=LEG_BAR_MIN.get(leg, 1440))
    if leg in CAL_DAY_HOLD:
        return signal_time + bar + pd.Timedelta(days=hold)
    return signal_time + bar * (1 + hold)


def decompose(t: pd.DataFrame, triggers: Dict[str, float], bar_open_at, holds: Dict[str, int]) -> pd.DataFrame:
    """Attach reference prices and split the money. bar_open_at(symbol, ts, minutes) -> open of the bar starting at ts."""
    if t.empty:
        return t
    t = t.copy()
    kinds, refx = [], []
    for r in t.itertuples():
        ct = r.close_type
        if ct in ("CreateByStopLoss", "CreateByTakeProfit") and triggers.get(r.close_oid):
            kinds.append("stop" if ct == "CreateByStopLoss" else "take-profit")
            refx.append(triggers[r.close_oid])
            continue
        exp = canon_expiry(r.leg, r.signal_time, holds.get(r.leg)) if r.leg else None
        bar_min = LEG_BAR_MIN.get(r.leg, 1440)
        if exp is not None and abs((r.t_close - exp).total_seconds()) <= bar_min * 60:
            px = bar_open_at(r.symbol, exp, min(bar_min, 60))
            if px:
                kinds.append("expiry")
                refx.append(px)
                continue
        kinds.append("other")
        refx.append(r.exit)
    t["exit_kind"], t["ref_exit"] = kinds, refx
    t["ref_entry"] = t["ref_entry"].where(t["ref_entry"].notna(), t["entry"])
    t["entry_cost"] = t["dir"] * (t["entry"] - t["ref_entry"]) * t["qty"]
    t["exit_cost"] = t["dir"] * (t["ref_exit"] - t["exit"]) * t["qty"]
    t["ideal"] = t["dir"] * (t["ref_exit"] - t["ref_entry"]) * t["qty"]
    t["live_net"] = t["closed_pnl"] - t["funding"]
    t["assumed_cost"] = ASSUMED_RT * t["entry_value"]
    t["resid"] = t["live_net"] - (t["ideal"] - t["entry_cost"] - t["exit_cost"] - t["fees"] - t["funding"])
    return t


def by_leg(t: pd.DataFrame) -> pd.DataFrame:
    if t is None or t.empty:
        return pd.DataFrame()
    g = t.assign(leg=t["leg"].fillna("(no journal)")).groupby("leg")
    s = g.agg(trades=("qty", "size"), entry_value=("entry_value", "sum"), ideal=("ideal", "sum"),
              entry_cost=("entry_cost", "sum"), exit_cost=("exit_cost", "sum"), fees=("fees", "sum"),
              funding=("funding", "sum"), live_net=("live_net", "sum"), assumed_cost=("assumed_cost", "sum"),
              resid=("resid", "sum"))
    s["exec_cost"] = s["entry_cost"] + s["exit_cost"] + s["fees"]
    s["vs_assumption"] = s["exec_cost"] - s["assumed_cost"]     # + = execution leaked more than the backtest assumed
    tot = s.sum(numeric_only=True).to_frame("total").T
    return pd.concat([s, tot])
