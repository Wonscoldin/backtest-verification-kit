# Deep dive: the trade that fills and dies in the same bar

**Incident #3.** A pullback-limit entry looked like the first strategy to pass every account:
**+0.44% per trade**. Re-measured with the state machine the live runner actually executes, it was
**−0.91% per trade, 0th percentile against random entry, negative in all six years.**

## What the research loop did

Inside each bar after a signal it asked two questions, in this order:

```python
# research loop (wrong)
if bar.close < stop:          # "the setup failed" -> forget the signal
    continue
if bar.low <= limit:          # fill
    enter(limit)
```

A bar that first dipped to the limit (fill) and then kept falling through the stop is, in real life,
**a filled trade that is stopped out in the same bar** — usually the worst trade the strategy takes.
The loop instead saw `close < stop` first and threw the signal away. Those trades never existed.
On one coin they were 37% of all fills, averaging −2.65%.

## The rule now

Inside one bar the order is **fill first, then stop**, for entries *and* exits:

```python
# verify/backtest.py
px = min(bar.open, limit)                 # fill (at the open if it gapped below the limit)
stop = px - stop_atr * atr
for b in range(entry_bar, last_bar + 1):  # the entry bar is included
    if low[b] <= stop:
        exit = stop if b == entry_bar else min(stop, open[b])   # a gap fills at the open
        break
```

Locked by `tests/test_bar_order.py::test_limit_fill_and_stop_in_same_bar_is_kept_as_a_loss`.

## Reproduce it on public data

```bash
python -m examples.same_bar_demo
```

On the example breakout with a 2% limit (daily bars, 6 coins), the effect is smaller than in the incident
but points the same way:

```
limit entries filled: 292
filled and stopped in the same bar: 10 (3.4%), mean -12.75%
correct order : mean +7.224% per trade
buggy order   : mean +7.754% per trade (7 worst trades silently removed)
```

How much this bug inflates a result depends on how often fills and stops share a bar: rare for a
breakout on daily bars, common for a pullback entry on hourly bars — which is exactly where it bit.

## The general lesson

Before adopting a limit-order strategy, measure it with the **same state machine the live runner uses**,
and diff the research numbers against it trade by trade. If the difference can't be explained,
don't quote the research number.
