# One signal, several rulebooks

The same family of signals runs on a crypto exchange account (own capital) and on funded-trader evaluation
accounts from three prop firms (A, B, C below). Each firm has its own rulebook: loss limits, swap schedules,
spreads, trading hours, position-size caps, and rules about opposite positions. A backtest that ignores
any one of them is measuring a different game.

## How a prop-firm evaluation works

1. Pay a fee and trade a firm-provided account (CFDs on gold, silver, indices and crypto through a
   MetaTrader-style broker), usually in **two phases with profit targets** (e.g. +10%, then +5%).
2. Throughout, never breach the **loss limits**. They are checked continuously, **intraday and on unrealised
   losses**; one touch ends the account and the fee is lost.
3. Pass both phases and the account becomes **funded**: the firm pays out a share (typically ~80%) of the
   profits, and the same loss limits keep applying for as long as the account lives.

| | Daily loss limit | Total loss limit | Notes that mattered for the model |
|---|---|---|---|
| Firm A | 5% | 10% | swap charged on gold/index CFDs; live code skips symbols whose spread is too wide |
| Firm B | 5% | 10% | closed on weekends; no opposite positions on the same symbol |
| Firm C | **4%** | **6%** | the tightest limits; broker swap far above typical rates; per-order lot caps |

So the objective is not "maximise return" and not "maximise pass rate". It is **expected money over
three years**: payouts × the probability that the account survives, minus fees for the attempts that fail.
The private backtest computes that directly (fees, phases, payouts); `verify/ev.py` here shows the
block-bootstrap core of it. Every decision below is judged by EV first and only then by the pass rate.

The pattern for every rule was the same:
1. **Model the rule in the one canonical simulator** (not in a side script).
2. **Find the days that decide the outcome** before touching parameters.
3. **Decide with expected money** (3-year block-bootstrap EV) in three windows (all / 2024+ / 2025+),
   not with the metric the rule is about.
4. Record when a decision went against the pre-registered criterion, and why.

| Rule | What the naive backtest did | What I found | Decision | Result |
|---|---|---|---|---|
| **Intraday daily-loss limit** (all firms) | checked the limit on daily closes | most "passes" had already breached intraday | judge on the intraday path | pass rate 97.6% → 76.0% (the honest number) |
| **Correlated metals** (firm B) | allowed gold, silver and platinum together | the pass-rate drop was **one day**: three metals falling together | at most 2 precious metals at once | breach days 1 → 0 in all windows · pass 60–85% → ~98.5% · EV **+16 / +34 / +66%** |
| **Daily equity breaker** (firm A) | none | the same breach days again | flatten everything at −4% intraday | pass 64 → 98% (2024+) with EV within noise (−3.0 / +1.4 / −0.8%). Pre-registered gate required EV up in all three windows; adopted anyway as a recorded owner decision |
| **Swap** (firm C) | used a flat crypto swap rate | the broker charged ~10× more on BTC/ETH (~150%/yr on longs); at real rates the old setup lost money in 2024+ | per-symbol swap + park three high-swap symbols across the daily rollover (close 21:02, re-enter 22:02) + drop one symbol | 2024+ CAGR **−2.7% → +14.5%** in the backtest at real rates |
| **Swap vs spread trade-off** (firm C) | — | for silver and platinum the spread paid to park and re-enter is **larger** than the swap saved | park only where swap > spread; triple-swap Wednesday is the only candidate for metals | avoided a "fix" that costs money every day |
| **Swap on gold/indices** (firm A) | 0 | real long swap −7 to −16%/yr | charge it | CAGR −0.6 points, pass −0.3 pt |
| **Spread caps** (firm A) | traded platinum at 0.11% | live code skips symbols whose spread exceeds 0.5%; platinum was always skipped | exclude it in the backtest too (better EV than trading it at the real spread) | CAGR 21.5 → 19.4 — the backtest now matches what live can do |
| **Weekend closure** (firm B) | closed expiring crypto positions on Sat/Sun | the account cannot trade on weekends; live closes Monday 00:00 | model the Monday close | CAGR +0.55 (a correction, not alpha) |
| **No opposite positions on one symbol** (firm B) | allowed one strategy long and another short on the same symbol | a compliance risk, not a P&L question | the ranking strategy yields the symbol and takes the next rank | EV +1.0 to +1.8%, rule satisfied |
| **Lot-size cap** (firm C) | — | splitting orders around the cap looked like free capacity | rejected: the cap was acting as a safety; splitting created 3 breach days where there were 0 | kept the cap |

## What this shows

* **The constraint, not the signal, often decides the result.** Several of the biggest changes in expected
  money came from modelling a rule correctly, not from a better entry.
* **Measure the objective, then look at the rule metric.** The metals cap raised the pass rate *and* EV;
  the breaker raised the pass rate with EV flat — two different kinds of decision, recorded differently.
* **Cheap-looking fixes have costs.** Rollover parking and order splitting both looked free and were not.
* **Live and backtest must enforce the same rules.** A daily parity check flags any live skip whose reason
  the backtest does not model.

Numbers are from the private canonical backtest at the time of each decision. They are in-sample and were
later discounted by walk-forward ratios before being used for planning.
