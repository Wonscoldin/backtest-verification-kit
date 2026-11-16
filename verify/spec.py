"""The ONLY place configuration constants live.

Rule: scripts never re-type a constant from here. A variant is a keyword argument to `backtest.run()`,
not a copied simulator. Every past incident in docs/INCIDENTS.md that came from "a new script that
forgot one correction" is why this file exists.
"""

UNIVERSE = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT")
START = "2020-01-01"

# Example strategy: textbook Donchian breakout (long only). Deliberately generic -- this repo is about
# verification, not about the edge.
STRATEGY = dict(entry_lookback=20, atr_len=14, stop_atr=2.0, hold_bars=10)

COST_RT = 0.0011          # round-trip cost as a fraction (fees + slippage), measured live -- see verify/exec_quality.py
RISK_PER_TRADE = 0.01     # fraction of equity lost if the stop is hit
MAX_POSITIONS = 4

# Known optimism that is NOT corrected yet. Quote it whenever you quote a number.
KNOWN_OPTIMISM = (
    "Daily bars: intraday path inside a bar is unknown; stop fills assume the worse of stop price and open.",
    "No funding/borrow cost on perpetuals.",
    "Universe chosen today (survivorship): delisted coins are absent.",
)
