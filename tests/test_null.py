import numpy as np
import pandas as pd

from verify.null import random_null


def _walk(seed, n, drift=0.0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, 0.03, n)))
    return pd.DataFrame({"open": c, "high": c * 1.02, "low": c * 0.98, "close": c},
                        index=pd.date_range("2018-01-01", periods=n, freq="D"))


def test_null_on_pure_noise_is_not_extreme():
    """On a random walk the breakout signal has no edge, so it should sit inside the null, not at its tail."""
    # one seed lands in either 2.5% tail 5% of the time by construction, so judge the median over several worlds
    pct = [random_null({s: _walk(10 * k + i, 900) for i, s in enumerate("ABC")}, n_draws=100, seed=k)["percentile"]
           for k in range(7)]
    assert 15 < float(np.median(pct)) < 85, pct


def test_null_entries_are_spread_over_the_whole_sample():
    """Regression: the null once kept the FIRST n random trades, so it only sampled the early years."""
    # on real BTC daily data the old code put only 34% of random entries in the second half (fair = 50%)
    df = _walk(5, 2000, drift=0.0005)
    mid = df.index[len(df) // 2]
    shares = [(pd.DatetimeIndex(random_null({"A": df}, n_draws=1, seed=s)["last_draw_entries"]) > mid).mean()
              for s in range(30)]
    share_late = float(np.mean(shares))
    assert 0.42 < share_late < 0.58, f"random entries bunched: {share_late:.0%} in the second half"
