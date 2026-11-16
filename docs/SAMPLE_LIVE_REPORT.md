# Sample: weekly live execution-cost report

Output of the live system's weekly report (crypto perpetuals, 2026-08-28 ~ 2026-11-16, 106 orders),
produced with the reference-price rules in `verify/exec_quality.py`. Account sizes and P&L are removed;
only costs in basis points remain. Positive slippage = worse than the reference.

| Side | Order type | Orders | Share of notional | Fee (bp) | Slippage (bp) | Total (bp) |
|---|---|---|---|---|---|---|
| Entry | Limit, filled as maker | 30 | 49.7% | 1.50 | 0.00 | 1.50 |
| Entry | Limit, filled as taker | 25 | 48.7% | 4.15 | −0.13 | 4.01 |
| Entry | Market | 1 | 1.6% | 4.40 | 0.00 | 4.40 |
| Exit | Market (holding period expired) | 33 | 59.2% | 4.04 | 0.99 | 5.03 |
| Exit | Stop-loss (vs trigger) | 12 | 30.9% | 4.09 | 1.39 | 5.48 |
| Exit | Limit, maker | 2 | 6.3% | 2.00 | 0.00 | 2.00 |
| Exit | Take-profit (vs trigger) | 3 | 3.6% | 4.40 | 0.70 | 5.10 |

**Round trip: 7.7bp** (entry 2.8 + exit 5.0; fees 6.8, slippage 1.0) **vs 11bp assumed in the backtest.**
Orders without a usable reference price: 0.

What the report led to: market exits at the end of the holding period were the largest cost bucket, so
expiry exits were switched to post-only maker orders with a market fallback after 5 minutes.
The backtest's cost assumption is recalibrated only after several weeks of live data — a cheaper
assumption is not "alpha".
