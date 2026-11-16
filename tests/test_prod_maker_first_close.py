"""Locks: (1) an exit always happens (2) symbols wait together (3) a stop during the wait sends no market order
(4) post-only rejections are re-posted (5) if the maker path fails, the market path still runs."""
from production.maker_first_close import close_maker_first


class _Client:
    """Fakes positions, quotes and order states. script[symbol] = status returned on each poll."""

    def __init__(self, sizes, script=None, place_fail=()):
        self.sizes = dict(sizes)
        self.script = script or {}
        self.place_fail = set(place_fail)
        self.orders, self.cancelled, self.market = {}, [], []
        self.n = 0

    def get_positions(self, symbol):
        side, size = self.sizes.get(symbol, ("Buy", 0.0))
        return {"result": {"list": [{"side": side, "size": str(size)}]}}

    def get_ticker(self, symbol):
        return {"result": {"list": [{"bid1Price": "99.9", "ask1Price": "100.1"}]}}

    def place_limit_order(self, symbol, side, qty, price, reduce_only, post_only):
        assert reduce_only and post_only, "expiry exits must be reduce-only and post-only"
        if symbol in self.place_fail:
            raise RuntimeError("retCode 10001")
        self.n += 1
        oid = f"o{self.n}"
        self.orders[oid] = {"sym": symbol, "side": side, "price": price, "polls": 0}
        return {"result": {"orderId": oid}}

    def get_order(self, symbol, oid):
        o = self.orders[oid]
        seq = self.script.get(symbol, ["New"])
        st = seq[min(o["polls"], len(seq) - 1)]
        o["polls"] += 1
        if st == "Filled":
            self.sizes[symbol] = (self.sizes[symbol][0], 0.0)
        if st == "StopHit":                      # stop fired while waiting: position 0, reduce-only cancelled
            self.sizes[symbol] = (self.sizes[symbol][0], 0.0)
            st = "Cancelled"
        if st == "Partial":
            side, size = self.sizes[symbol]
            self.sizes[symbol] = (side, size / 2)
            st = "PartiallyFilled"
        return {"result": {"list": [{"orderStatus": st}]}}

    def cancel_order(self, symbol, oid):
        self.cancelled.append(oid)

    def close_market(self, symbol):
        side, size = self.sizes[symbol]
        self.market.append((symbol, size))
        self.sizes[symbol] = (side, 0.0)
        return {"success": True}


class _Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _run(cl, syms, wait=300):
    c = _Clock()
    return close_maker_first(cl, syms, cl.close_market, wait_s=wait, poll_s=15, _sleep=c.sleep, _now=c.now), c


def test_maker_fill_needs_no_market_order_and_prices_at_best_quote():
    cl = _Client({"ADA": ("Buy", 100.0), "XLM": ("Sell", 50.0)}, {"ADA": ["New", "Filled"], "XLM": ["Filled"]})
    out, _ = _run(cl, ["ADA", "XLM"])
    assert out["ADA"]["success"] and out["XLM"]["success"] and cl.market == []
    px = {o["sym"]: (o["side"], o["price"]) for o in cl.orders.values()}
    assert px["ADA"] == ("Sell", 100.1) and px["XLM"] == ("Buy", 99.9), "long exits sell at the ask, short exits buy at the bid"


def test_unfilled_until_deadline_always_closes_at_market_and_waits_together():
    cl = _Client({"A": ("Buy", 10.0), "B": ("Buy", 10.0)}, {"A": ["New"], "B": ["New"]})
    out, clock = _run(cl, ["A", "B"], wait=300)
    assert sorted(cl.market) == [("A", 10.0), ("B", 10.0)], "after the deadline the exit must happen at market"
    assert set(cl.cancelled) == {"o1", "o2"}
    assert clock.t <= 300 + 15, "symbols must wait together, not one after another"
    assert all(v["success"] for v in out.values())


def test_partial_fill_market_closes_only_the_remainder():
    cl = _Client({"A": ("Buy", 10.0)}, {"A": ["Partial", "PartiallyFilled"]})
    out, _ = _run(cl, ["A"])
    assert cl.market == [("A", 5.0)]
    assert out["A"]["maker_qty"] == 5.0 and out["A"]["market_qty"] == 5.0


def test_stop_during_wait_sends_no_market_order():
    cl = _Client({"A": ("Buy", 10.0)}, {"A": ["StopHit"]})
    out, _ = _run(cl, ["A"])
    assert cl.market == [] and out["A"]["success"]


def test_post_only_reject_is_reposted_then_goes_market_without_waiting():
    cl = _Client({"A": ("Buy", 10.0), "B": ("Buy", 10.0)}, {"A": ["Cancelled"], "B": ["New"]})
    out, _ = _run(cl, ["A", "B"])
    assert len([o for o in cl.orders.values() if o["sym"] == "A"]) == 4, "first order + 3 re-posts"
    assert ("A", 10.0) in cl.market and out["A"]["success"]


def test_placement_failure_goes_straight_to_market():
    cl = _Client({"A": ("Buy", 10.0)}, place_fail={"A"})
    out, clock = _run(cl, ["A"])
    assert cl.market == [("A", 10.0)] and out["A"]["success"] and clock.t == 0
