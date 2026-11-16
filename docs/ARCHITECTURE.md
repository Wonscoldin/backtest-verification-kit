# The live system (architecture)

The private system this kit comes from is run like a small trading company by one person: research,
execution, risk, monitoring, deployment and reporting are separate, automated parts. Four of its real
modules are published in [`production/`](../production) with their tests; the rest stays private because it
contains strategy parameters (the edge) and account/infrastructure details.

```
                    ┌──────────────── research ────────────────┐
 market data ─────► │ canonical backtest  ◄── spec (one file)    │ ── pinned numbers (a test fails if they move)
 (exchange, broker, │ random-null gates · EV · walk-forward      │ ── corrections list + known-optimism list
  intraday feeds)   │ pre-registration · rejected-ideas ledger   │
                    └───────────────┬───────────────────────────┘
                                    │ manifests (what each strategy may trade, how big)
                                    ▼
          ┌──────────── runners: one container per strategy per account ─────────────┐
          │ signal → sizing → risk guards → order plan → execution → decision journal │
          └───────┬───────────────────────────────────────────────┬───────────────────┘
                  ▼                                               ▼
     crypto exchange (REST)                          prop-firm accounts (MetaTrader)
     limit/offset entries, maker-first exits,        file bridge to an EA (MQL5) on the terminal;
     resting-order refresh, idle cash → savings      every order tagged with its strategy id
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          ▼
   monitoring (5 layers): heartbeat → health → deployed-file drift → live-vs-backtest parity → invariants
   reports: daily parity · weekly signal replay, execution cost, implementation shortfall · monthly evidence archive
   alerts: Telegram, with state transitions instead of repeats
```

## Scale

* **~30 containers** on the main server: one runner per strategy per account, plus coordinators and guards.
* **~40 scheduled jobs**: monitors, reports, evidence export, savings sweep, cross-server checks.
* Two execution venues with different mechanics: a crypto exchange over REST, and prop-firm accounts through
  MetaTrader terminals driven by a custom Expert Advisor.
* One deploy command for all of it, and a test suite that must pass before anything ships.

## Parts

| Area | What it does | Why it exists (the incident behind it) |
|---|---|---|
| **Canonical backtest** | One simulator for every account; all constants in one spec file; pinned headline numbers | New scripts kept forgetting one correction each — see [INCIDENTS](INCIDENTS.md) |
| **Runners** | Manifest-driven: signal, sizing, guards, order plan, journal of every decision (PLACE or SKIP with a reason) | A skip without a logged reason once hid a filter that discarded every Monday bar |
| **Exchange execution** | Offset/limit entries, maker-first exits with a market fallback, refresh of resting orders | Market exits were the largest cost bucket ([sample report](SAMPLE_LIVE_REPORT.md)) |
| **MetaTrader bridge** | Python writes commands, an MQL5 EA executes; every order carries a strategy tag in its comment | One strategy once "adopted" another's position by guessing from symbol and stop |
| **Risk guards** | Daily loss guard, intraday equity breaker, drawdown cut (−10% from peak → halve), performance-degradation guard vs the backtest distribution, cross-account opposite-position guard, weekend and rollover handling, concurrency and exposure caps | Each one maps to a firm rule or a measured worst day ([CONSTRAINTS](CONSTRAINTS.md)) |
| **Parity monitoring** | Daily: every live skip must have a reason the backtest models; weekly: replay the backtest's signals against what live did | Half of the mismatches in a manual audit were silent live-only skips |
| **Execution reporting** | Weekly execution cost from raw fills; weekly implementation shortfall per strategy | A dashboard cell for "slippage vs assumption" had never been filled |
| **Deployment** | One command: upload, compare file hashes on the server, run each changed service for one dry tick with real feeds and no orders, then approve the new baseline — only if every hash matches. Uncommitted files are refused. | Manual copies skipped the approval step 6 times in one day; a partial deploy once silently reverted approved sizing |
| **Evidence & accounting** | Exchange raw records archived twice a month with a SHA-256 ledger; time-weighted returns that exclude cash flows and logged manual trades | A balance that grew by deposits is not a return |
| **Defect ledger** | Every defect: who found it (machine or human) and how long it lived | Two defects in one day were found by a person reading alerts — the machines could not see "successful but wrong" |

## Real modules in this repository

| `production/` | Runs in the live system | Tests |
|---|---|---|
| [`maker_first_close.py`](../production/maker_first_close.py) | every holding-period exit on the exchange | `tests/test_prod_maker_first_close.py` |
| [`exec_quality.py`](../production/exec_quality.py) | weekly execution-cost report | `tests/test_prod_exec_quality.py` |
| [`shortfall.py`](../production/shortfall.py) | weekly implementation-shortfall report | `tests/test_prod_shortfall.py` |
| [`parity_watch.py`](../production/parity_watch.py) | daily live-vs-backtest skip check | `tests/test_prod_parity_watch.py` |

They are the live code with comments translated and account, firm and infrastructure identifiers replaced.
The logic is unchanged.
