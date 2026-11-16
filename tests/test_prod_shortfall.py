import json

import pandas as pd

from production import shortfall as SF

T0 = pd.Timestamp("2026-11-10T00:00:00Z")


def _ms(t):
    return str(int(pd.Timestamp(t).timestamp() * 1000))


def _place(sym, side, leg, ref, sig, t):
    return json.dumps({"event": "decision", "action": "PLACE", "account": f"Exchange-{leg}", "symbol": sym, "side": side,
                       "logged_at": pd.Timestamp(t).isoformat(), "signal_time": pd.Timestamp(sig).isoformat(),
                       "planned_limit_price": ref, "stop_price": 0.9 * ref, "attempt_id": "a1"})


def _exec(oid, sym, side, t, closed="0", ctype="CreateByUser", etype="Trade", fee="0"):
    return {"execId": oid + _ms(t), "orderId": oid, "symbol": sym, "side": side, "execTime": _ms(t),
            "closedSize": closed, "createType": ctype, "execType": etype, "execFee": fee}


def _closed(oid, sym, close_side, entry, exit_, qty, t, open_fee, close_fee):
    d = 1 if close_side == "Sell" else -1
    pnl = d * (exit_ - entry) * qty - open_fee - close_fee
    return {"orderId": oid, "symbol": sym, "side": close_side, "avgEntryPrice": str(entry), "avgExitPrice": str(exit_),
            "qty": str(qty), "closedSize": str(qty), "cumEntryValue": str(entry * qty), "openFee": str(open_fee),
            "closeFee": str(close_fee), "closedPnl": str(pnl), "updatedTime": _ms(t)}


def test_expiry_uses_backtest_expiry_bar_open_and_identity_holds():
    # 4h strategy: signal bar 00:00 -> entry 04:00 -> hold 5 bars -> backtest expiry = 00:00 + 4h x 6 = next day 00:00
    places = SF.journal_places([_place("ADAUSDT", "long", "cbp4h", 1.000, T0, T0 + pd.Timedelta(hours=4, minutes=2))])
    execs = [_exec("in", "ADAUSDT", "Buy", T0 + pd.Timedelta(hours=4, minutes=3)),
             _exec("f1", "ADAUSDT", "Buy", T0 + pd.Timedelta(hours=8), etype="Funding", fee="0.05"),
             _exec("out", "ADAUSDT", "Sell", T0 + pd.Timedelta(hours=24, minutes=4), closed="100")]
    closed = [_closed("out", "ADAUSDT", "Sell", 1.001, 1.048, 100, T0 + pd.Timedelta(hours=24, minutes=4), 0.04, 0.02)]
    seen = []

    def bar_open(sym, ts, m):
        seen.append(ts)
        return 1.050

    d = SF.decompose(SF.trades(closed, execs, places), {}, bar_open, {"cbp4h": 5}).iloc[0]
    assert seen[0] == T0 + pd.Timedelta(hours=24)
    assert d["exit_kind"] == "expiry" and d["ref_exit"] == 1.050
    assert abs(d["entry_cost"] - 0.1) < 1e-9 and abs(d["exit_cost"] - 0.2) < 1e-9 and abs(d["ideal"] - 5.0) < 1e-9
    assert abs(d["resid"]) < 1e-9, "identity: live = ideal - entry cost - exit cost - fees - funding"


def test_short_stop_uses_trigger_and_cost_sign_is_positive_when_worse():
    places = SF.journal_places([_place("XRPUSDT", "short", "short", 1.000, T0, T0 + pd.Timedelta(days=1, minutes=3))])
    execs = [_exec("in", "XRPUSDT", "Sell", T0 + pd.Timedelta(days=1, minutes=4)),
             _exec("sl", "XRPUSDT", "Buy", T0 + pd.Timedelta(days=2), closed="10", ctype="CreateByStopLoss")]
    closed = [_closed("sl", "XRPUSDT", "Buy", 0.999, 1.302, 10, T0 + pd.Timedelta(days=2), 0, 0)]
    d = SF.decompose(SF.trades(closed, execs, places), {"sl": 1.300}, lambda *a: None, {"short": 5}).iloc[0]
    assert d["exit_kind"] == "stop" and abs(d["exit_cost"] - 0.02) < 1e-9 and abs(d["entry_cost"] - 0.01) < 1e-9
    assert abs(d["resid"]) < 1e-9


def test_runner_exit_far_from_expiry_is_other_with_zero_exit_cost():
    places = SF.journal_places([_place("SOLUSDT", "long", "donchian", 100.0, T0, T0 + pd.Timedelta(days=1))])
    execs = [_exec("in", "SOLUSDT", "Buy", T0 + pd.Timedelta(days=1, minutes=1)),
             _exec("cut", "SOLUSDT", "Sell", T0 + pd.Timedelta(days=3), closed="1")]
    closed = [_closed("cut", "SOLUSDT", "Sell", 100.0, 95.0, 1, T0 + pd.Timedelta(days=3), 0, 0)]
    d = SF.decompose(SF.trades(closed, execs, places), {}, lambda *a: 99.0, {"donchian": 10}).iloc[0]
    assert d["exit_kind"] == "other" and d["exit_cost"] == 0.0
