"""Expiry exits: maker first, market after a deadline.  (live since 2026-11-15)

Why: holding-period exits were market orders, paying taker fee + slippage on the largest cost bucket
(see docs/SAMPLE_LIVE_REPORT.md). Post a reduce-only, post-only limit at the best quote; whatever has not
filled after `wait_s` is closed at market. **The position is always closed** -- the set of trades is
identical to the backtest; only price and fee change. Measured before adoption on 5-minute data with no
future information: the saving's confidence-interval lower bound was > 0 in all three windows, net of the
~8% of orders that miss and chase.

Rules learned the hard way:
* Waiting symbol by symbol made six same-day exits take 30 minutes -> post everything first, wait together.
* A post-only order rejected because price moved through it is re-posted at the new best quote, up to
  `max_reprice` times, then that symbol goes to market immediately (others keep waiting).
* If the stop-loss fires while waiting, the position is already 0: cancel the limit, send no market order.
* If placing the maker order fails at all, go to market at once -- an exit must never be skipped.
"""
from __future__ import annotations

import time as _time
from typing import Callable, Dict, Iterable, Optional


def close_maker_first(client, symbols: Iterable[str], close_market: Callable[[str], dict],
                      wait_s: float = 300.0, poll_s: float = 15.0, max_reprice: int = 3,
                      on_event: Optional[Callable[..., None]] = None, on_error: Optional[Callable[[str], None]] = None,
                      _sleep=None, _now=None) -> Dict[str, dict]:
    """client: exchange REST wrapper with get_positions / get_ticker / place_limit_order / get_order / cancel_order.
    close_market(symbol) -> {"success": bool, ...} is the existing market-exit path.
    Returns {symbol: {"success", "maker_qty", "market_qty", "message"}}."""
    sleep = _sleep or _time.sleep
    now = _now or _time.monotonic
    event = on_event or (lambda *a, **k: None)
    error = on_error or (lambda msg: None)
    out: Dict[str, dict] = {}
    pend: Dict[str, dict] = {}

    def position(sym):
        p = (client.get_positions(symbol=sym).get("result") or {}).get("list") or []
        p = [x for x in p if float(x.get("size") or 0) > 0]
        return (p[0]["side"], float(p[0]["size"])) if p else (None, 0.0)

    def post(sym, side, qty):
        tk = client.get_ticker(symbol=sym)["result"]["list"][0]
        # closing a long sells at the best ask, closing a short buys at the best bid -> front of the maker queue
        px = float(tk["ask1Price"] if side == "Sell" else tk["bid1Price"])
        r = client.place_limit_order(symbol=sym, side=side, qty=qty, price=px, reduce_only=True, post_only=True)
        return ((r or {}).get("result") or {}).get("orderId"), px

    def market(sym, maker_qty, market_qty, note):
        res = close_market(sym) or {}
        ok = res.get("success", True) is not False
        return {"success": ok, "maker_qty": maker_qty, "market_qty": market_qty,
                "message": note if ok else str(res.get("message"))}

    for sym in symbols:
        try:
            pside, size = position(sym)
            if size <= 0:
                out[sym] = {"success": True, "maker_qty": 0.0, "market_qty": 0.0, "message": "no open position"}
                continue
            cside = "Sell" if pside == "Buy" else "Buy"
            oid, px = post(sym, cside, size)
            pend[sym] = {"side": cside, "size": size, "oid": oid, "reprice": 0, "px": px}
            event("CLOSE_MAKER_PLACED", symbol=sym, side=cside, qty=size, price=px)
        except Exception as e:  # noqa: BLE001 -- the exit must happen
            error(f"{sym}: maker exit could not be placed, going to market: {e}")
            out[sym] = market(sym, 0.0, None, f"maker placement failed -> market ({e})")

    deadline = now() + float(wait_s)
    while pend and now() < deadline:
        sleep(poll_s)
        for sym in list(pend):
            st = pend[sym]
            if st["oid"] is None:
                continue
            try:
                o = ((client.get_order(sym, st["oid"]) or {}).get("result") or {}).get("list") or []
                status = (o[0].get("orderStatus") if o else "") or ""
            except Exception as e:  # noqa: BLE001
                error(f"{sym}: order lookup failed: {e}")
                continue
            if status == "Filled":
                out[sym] = {"success": True, "maker_qty": st["size"], "market_qty": 0.0, "message": f"maker fill at {st['px']}"}
                del pend[sym]
            elif status in ("Cancelled", "Rejected", "Deactivated"):
                # post-only rejection, or the position is already 0 (stop hit) so reduce-only was cancelled
                _, size = position(sym)
                if size <= 0:
                    out[sym] = {"success": True, "maker_qty": 0.0, "market_qty": 0.0,
                                "message": "position closed while waiting (stop) -- no market order"}
                    del pend[sym]
                    continue
                if st["reprice"] < max_reprice:
                    st["reprice"] += 1
                    try:
                        st["oid"], st["px"] = post(sym, st["side"], size)
                        st["size"] = size
                    except Exception as e:  # noqa: BLE001
                        error(f"{sym}: re-post failed, going to market: {e}")
                        st["oid"] = None
                else:
                    st["oid"] = None
                if st["oid"] is None:          # only this symbol goes to market now; the others keep waiting
                    out[sym] = market(sym, 0.0, size, "post-only re-posts exhausted -> market")
                    del pend[sym]

    # deadline: cancel what is left, then close the remainder at market
    for sym, st in pend.items():
        if st["oid"]:
            try:
                client.cancel_order(sym, st["oid"])
            except Exception as e:  # noqa: BLE001 -- it may have just filled; the position re-read below is the truth
                error(f"{sym}: cancel failed (may have filled): {e}")
        try:
            _, left = position(sym)
        except Exception as e:  # noqa: BLE001
            out[sym] = {"success": False, "message": f"position re-read failed: {e}"}
            continue
        if left <= 0:
            out[sym] = {"success": True, "maker_qty": st["size"] or 0.0, "market_qty": 0.0, "message": "maker fill just before deadline"}
            continue
        maker = max(0.0, (st["size"] or left) - left)
        out[sym] = market(sym, maker, left, f"deadline {wait_s:.0f}s -- maker {maker} / market {left}")
    return out
