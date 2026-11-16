"""Public daily OHLCV from Binance spot (no API key). Cached to ./data/<SYMBOL>_1d.csv."""
from __future__ import annotations

import os
import time

import pandas as pd
import requests

URL = "https://api.binance.com/api/v3/klines"
COLS = ["open_time", "open", "high", "low", "close", "volume"]


def load_daily(symbol: str, start: str = "2019-01-01", cache_dir: str = "data", refresh: bool = False) -> pd.DataFrame:
    path = os.path.join(cache_dir, f"{symbol}_1d.csv")
    if os.path.exists(path) and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)
    rows, t = [], int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    while True:
        r = requests.get(URL, params={"symbol": symbol, "interval": "1d", "startTime": t, "limit": 1000}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows += batch
        t = batch[-1][0] + 86_400_000
        if len(batch) < 1000:
            break
        time.sleep(0.2)
    df = pd.DataFrame([x[:6] for x in rows], columns=COLS)
    df.index = pd.to_datetime(df.pop("open_time"), unit="ms", utc=True).dt.tz_localize(None)
    df = df.astype(float)
    df = df[df.index < pd.Timestamp.utcnow().tz_localize(None).normalize()]   # drop the unfinished bar
    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(path)
    return df
