import numpy as np
import pandas as pd

from verify.null import random_null


def test_null_on_pure_noise_is_not_extreme():
    """On a random walk the breakout signal has no edge, so it should sit inside the null, not at its tail."""
    rng = np.random.default_rng(7)
    data = {}
    for s in ("A", "B", "C"):
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, 900)))
        df = pd.DataFrame({"open": c, "high": c * 1.02, "low": c * 0.98, "close": c},
                          index=pd.date_range("2020-01-01", periods=900, freq="D"))
        data[s] = df
    r = random_null(data, n_draws=200, seed=1)
    assert 2.5 < r["percentile"] < 97.5
