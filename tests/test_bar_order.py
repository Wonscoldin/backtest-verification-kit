"""Each test locks one rule whose violation once inflated a real backtest (docs/INCIDENTS.md)."""
import numpy as np
import pandas as pd

from verify import spec
from verify.backtest import run, signals, symbol_trades
from verify.exec_quality import summary

P = dict(entry_lookback=3, atr_len=2, stop_atr=1.0, hold_bars=3)


def bars(rows):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.index = pd.date_range("2024-01-01", periods=len(df), freq="D")
    return df


FLAT = [(100, 101, 99, 100)] * 4


def test_limit_fill_and_stop_in_same_bar_is_kept_as_a_loss():
    # bar 4 breaks out at 105; bar 5 dips to the limit AND through the stop -> must be a stopped trade, not skipped
    df = bars(FLAT + [(100, 106, 100, 105), (105, 105, 90, 95), (95, 96, 94, 95), (95, 96, 94, 95)])
    t = symbol_trades("X", df, entry="limit", limit_offset=0.01, **P)
    assert len(t) == 1 and t[0].reason == "stop" and t[0].exit_day == t[0].entry_day
    assert t[0].ret < 0


def test_stop_on_a_gap_fills_at_the_open_not_the_stop():
    df = bars(FLAT + [(100, 106, 100, 105), (105, 106, 104, 105), (80, 82, 79, 80), (80, 81, 79, 80)])
    t = symbol_trades("X", df, **P)[0]
    assert t.reason == "stop" and t.exit == 80 and t.exit < t.stop


def test_no_lookahead_future_bars_do_not_change_past_signals():
    rng = np.random.default_rng(1)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    df = bars([(x, x * 1.01, x * 0.99, x) for x in c])
    a = signals(df, 20).iloc[:200]
    df2 = df.copy()
    df2.iloc[200:] *= 3.0
    assert a.equals(signals(df2, 20).iloc[:200])


def test_costs_are_charged():
    rng = np.random.default_rng(2)
    c = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.03, 400)))
    df = bars([(x, x * 1.02, x * 0.98, x) for x in c])
    free, paid = run({"X": df}, cost_rt=0.0), run({"X": df}, cost_rt=0.002)
    assert len(free["trades"]) > 0 and paid["curve"].iloc[-1] < free["curve"].iloc[-1]


def test_stop_slippage_is_measured_against_trigger_not_mark():
    fills = pd.DataFrame([
        dict(side="sell", kind="stop", fill_price=99.9, ref_price=100.0, fee_bps=5.5),     # trigger 100
        dict(side="buy", kind="limit", fill_price=100.0, ref_price=100.0, fee_bps=2.0),
        dict(side="sell", kind="market", fill_price=101.0, ref_price=0.0, fee_bps=5.5),     # no reference: excluded
    ])
    s = summary(fills, assumed_rt_bps=spec.COST_RT * 1e4)
    assert s["no_reference"] == 1 and s["n"] == 3
    assert abs(s["slip_rt_bps"] - 10.0) < 1e-6        # (10bp + 0bp)/2 per side x 2
