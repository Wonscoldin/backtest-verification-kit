import numpy as np
import pandas as pd

from verify.walkforward import anchored, grid_curves

GRID = {"entry_lookback": (10, 20), "stop_atr": (1.5, 3.0)}


def _data(seed=0, n=1500):
    rng = np.random.default_rng(seed)
    out = {}
    for s in ("A", "B"):
        c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.03, n)))
        out[s] = pd.DataFrame({"open": c, "high": c * 1.02, "low": c * 0.98, "close": c},
                              index=pd.date_range("2020-01-01", periods=n, freq="D"))
    return out


def test_simulator_is_causal_so_slicing_one_run_is_valid():
    """Changing data after a date must not change returns before it -- otherwise slicing would leak."""
    d1 = _data()
    d2 = {s: df.copy() for s, df in d1.items()}
    cut = pd.Timestamp("2022-06-01")
    for df in d2.values():
        df.loc[cut:] *= 2.5
    a, b = grid_curves(d1, GRID), grid_curves(d2, GRID)
    for k in a:
        x, y = a[k].loc[:cut - pd.Timedelta(days=30)], b[k].loc[:cut - pd.Timedelta(days=30)]
        assert np.allclose(x.values, y.values)


def test_choice_for_a_fold_ignores_the_future():
    d1 = _data(1)
    d2 = {s: df.copy() for s, df in d1.items()}
    for df in d2.values():
        df.loc["2023-01-01":] = df.loc["2023-01-01":].iloc[::-1].values     # scramble the test period
    f1 = anchored(d1, GRID, [2023], ev_draws=100)["folds"].iloc[0]["chosen"]
    f2 = anchored(d2, GRID, [2023], ev_draws=100)["folds"].iloc[0]["chosen"]
    assert f1 == f2
