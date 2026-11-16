"""Incident #3 reproduced on public data: what happens if, inside the entry bar, the stop check runs
before the fill check?

    python -m examples.same_bar_demo

Correct order (the simulator): fill at the limit, then check the stop in the same bar.
Buggy order (the research loop that once produced "+0.44% per trade"):
    if close < stop: discard the signal      # looks like "the setup failed"
    elif low <= limit: fill
So every trade that filled and then fell through its stop on the same bar disappears.
"""
import numpy as np

from verify import spec
from verify.backtest import symbol_trades
from verify.data import load_daily

P = {**spec.STRATEGY, "entry_lookback": 20}
OFFSET = 0.02            # limit 2% below the signal close (a pullback entry)

rows = []
for s in spec.UNIVERSE:
    df = load_daily(s, start=spec.START)
    for t in symbol_trades(s, df, entry="limit", limit_offset=OFFSET, **P):
        close_e = df.loc[t.entry_day, "close"]
        rows.append((t.ret - spec.COST_RT, close_e < t.stop, t.reason == "stop" and t.exit_day == t.entry_day))

r = np.array([x[0] for x in rows])
dropped_by_bug = np.array([x[1] for x in rows])
same_bar_stop = np.array([x[2] for x in rows])
print(f"limit entries filled: {len(r)}")
print(f"filled and stopped in the same bar: {same_bar_stop.sum()} ({same_bar_stop.mean()*100:.1f}%), "
      f"mean {r[same_bar_stop].mean()*100:+.2f}%")
print(f"correct order : mean {r.mean()*100:+.3f}% per trade")
print(f"buggy order   : mean {r[~dropped_by_bug].mean()*100:+.3f}% per trade "
      f"({dropped_by_bug.sum()} worst trades silently removed)")
