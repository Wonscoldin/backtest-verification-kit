# Incidents: measurement bugs that made results look better than they were

Each one happened while I was running a live, automated, multi-strategy portfolio across crypto, gold, silver and equity indices (2026).
The pattern is almost always the same: **a good-looking number is usually a measurement bug.**
Every fix became a rule in the simulator and, where possible, a test that fails if the bug returns.

### Context: what "pass rate" means here

Part of the portfolio runs on **funded-trader evaluation accounts** (prop-firm style; how they work and each
firm's limits are in [CONSTRAINTS.md](CONSTRAINTS.md#how-a-prop-firm-evaluation-works)). They come with hard
rules: for example, losing more than 5% of the starting balance within one day, or 10% in total, ends the
account immediately — **including intraday, on unrealised losses**. A strategy is only useful there if its
equity path never touches those lines.

So for these accounts the backtest reports a **pass rate**: the share of simulated start dates (with
randomised fills) on which the account would have survived the evaluation. Three consequences drive several
incidents below:

* The rule is checked on the **path inside the day**, so a simulator that only looks at daily closes is
  measuring a different, easier game.
* The pass rate is a **step function of a few days**: one gap day in the window fails the whole run, so
  "98% vs 86%" is often one or two days, not a gradual difference. Count the breach days before arguing
  about half a percentage point.
* It is an intermediate metric. Sizing is still decided by expected money (see `verify/ev.py`): maximising
  the pass rate alone simply trades too small.

| # | What looked good | What was actually wrong | Size of the error | Rule / test now |
|---|---|---|---|---|
| 1 | Evaluation pass rate ~98% | The daily-loss rule was checked on **daily closes**. Intraday, many paths had already crossed the limit — which ends the account. | pass rate 97.6% → **76.0%** | Judge limits on the intraday path, never the close |
| 2 | Pass rate with gold/indices added | Those assets were measured on **daily closes** while crypto used hourly bars. One day when silver and gold fell together intraday decided most of the difference. | 98.6% → **86.0%** | Every asset on the same intraday resolution |
| 3 | Pullback-limit entry "+0.44% per trade" | The research loop checked `close < stop → discard` **before** `low ≤ limit → fill`, so every bar that filled *and* stopped (the worst trades) vanished. | **+0.44% → −0.91%**, 0th percentile vs random | Fill first, then stop — `test_limit_fill_and_stop_in_same_bar_is_kept_as_a_loss` |
| 4 | Multi-strategy portfolio | Same-day entries were processed in **alphabetical order of strategy name**, letting an afternoon order take a slot before a midnight one. | planning return cut by ~30% after fixing | Fixed, documented processing order |
| 5 | Holding period of 5 bars | Bars were counted as **calendar days** for weekday-only assets: positions were closed 2 days early, and the sim re-entered while the real position would still be open. | CAGR −1.5 to −6.6 points across accounts | Hold counted in the asset's own bars, plus a calendar test |
| 6 | Window ended early for one account | The end date was the minimum over *all* symbols' files — including two symbols the account never traded, whose files were stale. | window cut by 7 weeks | End = last bar of symbols actually traded |
| 7 | 8-signal combination, holdout Sharpe 1.36 | The 8 signals were chosen **after** looking at holdout numbers. Adding 10 unseen signals collapsed it. | **1.36 → 0.08** | Pre-registration: criteria fixed before measuring, every attempt counted |
| 8 | Live execution cost 15.3bp round trip | Stop fills were compared with the **mark price** instead of the **trigger price** the backtest assumes. | real cost **8.0bp** vs 11bp assumed | `exec_quality.py` reference-price rules |
| 9 | "Coverage" gate passed | A gate of "fills ≥10% of empty days" was passed by a strategy that was simply long 91% of the time. | gate had zero discriminating power | Gates are percentiles against a random null, not absolute numbers |
| 10 | `pytest \| tail` → exit 0 | The pipeline returned **tail's** exit code; one test had failed. | a broken check almost shipped | Capture the real exit code; never judge on truncated output |
| 11 | This kit's own random null | Found while reviewing this repo: the null drew 2n random days, sorted them and kept the **first n** trades, so random entries bunched into the early years (34% in the second half instead of 50%). | null mean +2.76% → **+1.87%** per trade | `test_null_entries_are_spread_over_the_whole_sample` |

## Habits these produced

* **One canonical simulator.** Variants are arguments to `run()`; nobody copies the loop. Most incidents above came from "a new script that forgot one correction".
* **Random null first.** Same symbols, same number of entries, same stop/hold/cost — only the entry days are random. A gate's threshold is a percentile of that null.
* **Three windows, plus "best day removed".** A result must hold in the full window, 2024+ and 2025+, and survive deleting its single best day.
* **Decide with the objective.** Sizing is judged by expected wealth (block bootstrap), not by a proxy like pass rate, which can be maximised by trading too small.
* **Live vs backtest every day.** Every signal the live system skipped must have a reason the backtest also knows about; unknown reasons raise an alert.
