from production import exec_quality as Q


def _x(oid, side, otype, ctype, price, qty, fee, order_price, mark, closed="0", maker=False, t=1794700000000, link=""):
    return {"execId": f"{oid}-{price}", "orderId": oid, "symbol": "XRPUSDT", "side": side, "orderType": otype,
            "createType": ctype, "execType": "Trade", "execPrice": str(price), "execQty": str(qty),
            "execValue": str(price * qty), "execFee": str(fee), "orderPrice": str(order_price),
            "markPrice": str(mark), "closedSize": closed, "isMaker": maker, "execTime": str(t), "orderLinkId": link}


def test_limit_entry_slippage_is_against_order_price_and_tag_gives_strategy():
    o = Q.orders([_x("a", "Sell", "Limit", "CreateByUser", 0.9147, 100, 0.04, 0.9146, 0.9147, link="aq-short-abc")])
    r = o.iloc[0]
    assert r["role"] == "limit (taker)" and r["kind"] == Q.ENTRY and r["leg"] == "short"
    assert r["slip_bps"] < 0                       # sold above the limit = favourable (negative)


def test_stop_uses_trigger_not_mark_and_missing_trigger_is_excluded():
    # the mark lags far above the fill: against the mark this looks like big slippage, against the trigger it is small
    rows = [_x("s1", "Sell", "Market", "CreateByStopLoss", 0.9990, 100, 0.04, 0, 1.0100, closed="100"),
            _x("s2", "Sell", "Market", "CreateByStopLoss", 0.9990, 100, 0.04, 0, 1.0100, closed="100")]
    o = Q.orders(rows, {"s1": 1.0})
    assert abs(o.set_index("orderId").loc["s1", "slip_bps"] - 10.0) < 1e-6
    s = Q.summary(o)
    assert s["no_ref"] == 1 and s["n"] == 1        # a stop without a trigger is excluded, not priced with the mark


def test_round_trip_is_entry_plus_exit_value_weighted_and_level():
    rows = [_x("e", "Buy", "Limit", "CreateByUser", 1.0, 100, 0.02, 1.0, 1.0, maker=True),
            _x("c", "Sell", "Market", "CreateByUser", 0.999, 100, 0.044, 0, 1.0, closed="100")]
    s = Q.summary(Q.orders(rows))
    assert abs(s["entry_bps"] - 2.0) < 1e-6
    assert abs(s["exit_bps"] - (0.044 / 99.9 * 1e4 + 10.0)) < 1e-6
    assert Q.level(s["rt_bps"]) == "bad" and Q.level(12.0) == "warn" and Q.level(9.0) == "ok" and Q.level(None) == "idle"


def test_funding_rows_are_not_trades():
    r = _x("f", "Buy", "UNKNOWN", "", 1.0, 1, 0.01, 0, 1.0)
    r["execType"] = "Funding"
    assert Q.orders([r]).empty
