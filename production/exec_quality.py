"""Execution quality from raw exchange fills, against the backtest's round-trip cost assumption.

Why: the backtest assumes one number for cost. A dashboard had a "slippage vs assumption" cell that nothing
ever filled -- a monitor built and never read. If execution is where a public-signal strategy wins or
loses, a machine has to measure it every week.

Input: rows of the exchange's execution list. Fills are grouped into ORDERS:
  fee_bps  = fee / filled value
  slip_bps = adverse price difference (+ = worse). Reference price:
             limit order   -> its own order price (entry limits sit at the signal-bar close = backtest fill)
             stop / TP     -> the TRIGGER price, from order history
             market order  -> mark price at fill
  The first version measured stops against the mark price: 12.8bp stop slippage, 15.3bp round trip,
  "over budget". Against the trigger it was 2.8bp -- in fast markets the index-based mark lags the fill.
  Stops without a known trigger are NOT priced with the mark; they are excluded and counted.
Round trip = value-weighted entry cost + exit cost. Raw exchange data only, no estimates.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

import pandas as pd

ASSUMED_RT_BPS = 11.0     # the backtest's round-trip assumption
WARN_RT_BPS = 11.0
BAD_RT_BPS = 15.0
ENTRY, EXIT = "entry", "exit"


def _role(r) -> str:
    ct, ot = r["createType"], r["orderType"]
    if ct == "CreateByStopLoss":
        return "stop-loss"
    if ct == "CreateByTakeProfit":
        return "take-profit"
    if ot == "Market":
        return "market"
    return "limit (maker)" if r["maker_share"] >= 0.5 else "limit (taker)"


def orders(rows: Iterable[dict], triggers: Optional[dict] = None, tag_pattern: str = r"^aq-([a-z0-9]+)-") -> pd.DataFrame:
    """Fill rows -> one row per order. Non-trade rows (funding) are dropped.
    triggers: {orderId: triggerPrice}; a stop/TP without one gets ref_ok=False.
    tag_pattern extracts the strategy ("leg") from the client order id the runners stamp on every order."""
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df
    df = df[df.get("execType", "Trade") == "Trade"].copy()
    if df.empty:
        return df
    for c in ("execPrice", "execQty", "execValue", "execFee", "orderPrice", "markPrice", "closedSize"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["maker"] = df["isMaker"].astype(bool).astype(float)
    df["t"] = pd.to_datetime(df["execTime"].astype("int64"), unit="ms", utc=True)
    g = df.groupby("orderId", sort=False)
    o = g.agg(symbol=("symbol", "first"), side=("side", "first"), orderType=("orderType", "first"),
              createType=("createType", "first"), orderLinkId=("orderLinkId", "first"),
              t=("t", "max"), qty=("execQty", "sum"), value=("execValue", "sum"), fee=("execFee", "sum"),
              closed=("closedSize", "max"), orderPrice=("orderPrice", "first"))
    o["vwap"] = o["value"] / o["qty"]
    o["mark"] = g.apply(lambda x: (x["markPrice"] * x["execQty"]).sum() / x["execQty"].sum(), include_groups=False)
    o["maker_share"] = g.apply(lambda x: (x["maker"] * x["execValue"]).sum() / x["execValue"].sum(), include_groups=False)
    o = o.reset_index()
    o["kind"] = (o["closed"] > 0).map({True: EXIT, False: ENTRY})
    o["role"] = o.apply(_role, axis=1)
    ref = o["orderPrice"].where(o["orderType"] == "Limit", o["mark"])
    ref = ref.where(ref > 0, o["mark"])
    trig = pd.to_numeric(o["orderId"].map(triggers or {}), errors="coerce")
    cond = o["role"].isin(["stop-loss", "take-profit"])
    o["ref_ok"] = ~cond | (trig > 0)
    ref = ref.where(~cond, trig)
    sign = o["side"].map({"Buy": 1.0, "Sell": -1.0})
    o["slip_bps"] = sign * (o["vwap"] - ref) / ref * 1e4
    o["fee_bps"] = o["fee"] / o["value"] * 1e4
    o["cost_bps"] = o["fee_bps"] + o["slip_bps"]
    o["leg"] = o["orderLinkId"].fillna("").str.extract(tag_pattern, expand=False)
    return o


def drop_manual(o: pd.DataFrame, is_manual: Callable[[str, pd.Timestamp], bool]) -> pd.DataFrame:
    """Remove manual orders (logged intervention windows): measure the automated system only."""
    if o is None or o.empty:
        return o
    return o[[not is_manual(str(s), t) for s, t in zip(o["symbol"], o["t"])]].reset_index(drop=True)


def _wavg(x: pd.DataFrame, col: str) -> float:
    return float((x[col] * x["value"]).sum() / x["value"].sum()) if len(x) and x["value"].sum() > 0 else float("nan")


def summary(o: pd.DataFrame, since: Optional[pd.Timestamp] = None) -> dict:
    """Table by (entry/exit, order type) plus the measured round trip."""
    if o is None or o.empty:
        return {"n": 0, "table": pd.DataFrame(), "rt_bps": None}
    if since is not None:
        o = o[o["t"] >= since]
    no_ref = int((~o["ref_ok"]).sum()) if "ref_ok" in o.columns else 0
    if no_ref:
        o = o[o["ref_ok"]]
    if o.empty:
        return {"n": 0, "table": pd.DataFrame(), "rt_bps": None}
    rows = []
    for (k, r), x in o.groupby(["kind", "role"]):
        rows.append({"side": k, "type": r, "orders": len(x), "share_%": 0.0, "fee_bp": _wavg(x, "fee_bps"),
                     "slip_bp": _wavg(x, "slip_bps"), "total_bp": _wavg(x, "cost_bps"), "_v": x["value"].sum()})
    t = pd.DataFrame(rows)
    for k in (ENTRY, EXIT):
        m = t["side"] == k
        t.loc[m, "share_%"] = t.loc[m, "_v"] / t.loc[m, "_v"].sum() * 100
    t = t.drop(columns="_v").sort_values(["side", "share_%"], ascending=[True, False]).reset_index(drop=True)
    ent, ext = o[o["kind"] == ENTRY], o[o["kind"] == EXIT]
    e_c, x_c = _wavg(ent, "cost_bps"), _wavg(ext, "cost_bps")
    rt = (e_c + x_c) if len(ent) and len(ext) else None
    return {"n": int(len(o)), "no_ref": no_ref, "table": t, "entry_bps": e_c, "exit_bps": x_c, "rt_bps": rt,
            "rt_fee_bps": (_wavg(ent, "fee_bps") + _wavg(ext, "fee_bps")) if rt is not None else None,
            "rt_slip_bps": (_wavg(ent, "slip_bps") + _wavg(ext, "slip_bps")) if rt is not None else None,
            "from": o["t"].min(), "to": o["t"].max()}


def level(rt_bps: Optional[float]) -> str:
    if rt_bps is None:
        return "idle"
    return "bad" if rt_bps > BAD_RT_BPS else ("warn" if rt_bps > WARN_RT_BPS else "ok")
