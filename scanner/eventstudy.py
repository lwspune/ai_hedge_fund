"""Pure event-study math for validating the bulk/block-deal signal.

For a deal disclosed after close on T0, a public follower can only enter from
T+1. So we measure the *post-disclosure* abnormal return: stock return from the
entry day to entry+horizon, minus the benchmark's return over the same calendar
dates. That is the number that actually accrues to a follower — distinct from the
pre-event run-up the literature attributes to front-running.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def forward_abnormal_return(stock: pd.Series, bench: pd.Series, t0,
                            horizon: int, entry_lag: int = 1):
    """Benchmark-adjusted return from T0+entry_lag to T0+entry_lag+horizon.

    `stock` and `bench` are close prices indexed by date. Returns None when there
    isn't enough data (symbol missing, event too recent, gaps).
    """
    if stock is None or len(stock) == 0:
        return None
    stock = stock.sort_index()
    t0 = pd.Timestamp(t0)

    idx = stock.index
    pos = idx.searchsorted(t0)  # first trading day >= t0
    entry = pos + entry_lag
    exit_ = entry + horizon
    if entry < 0 or exit_ < 0 or entry >= len(idx) or exit_ >= len(idx):
        return None

    d_entry, d_exit = idx[entry], idx[exit_]
    s_ret = stock.iloc[exit_] / stock.iloc[entry] - 1.0

    # Benchmark over the *same calendar dates* (asof handles holiday misalignment).
    b = bench.sort_index()
    b_entry = b.asof(d_entry)
    b_exit = b.asof(d_exit)
    if pd.isna(b_entry) or pd.isna(b_exit) or b_entry == 0:
        return None
    b_ret = b_exit / b_entry - 1.0

    return float(s_ret - b_ret)


def summarize(cars: list) -> dict:
    """Aggregate a list of abnormal returns into headline stats."""
    vals = np.array([c for c in cars if c is not None], dtype="float64")
    if len(vals) == 0:
        return {"n": 0, "mean": None, "median": None, "pct_positive": None, "t_stat": None}
    mean = float(vals.mean())
    std = float(vals.std(ddof=1)) if len(vals) > 1 else float("nan")
    t_stat = float(mean / (std / np.sqrt(len(vals)))) if std and not np.isnan(std) else None
    return {
        "n": int(len(vals)),
        "mean": mean,
        "median": float(np.median(vals)),
        "pct_positive": float((vals > 0).mean()),
        "t_stat": t_stat,
    }


def window_return(stock: pd.Series | None, bench: pd.Series, event_date, a: int, b: int):
    """Benchmark-adjusted return from close T+a to close T+b (T = first trading day >=
    event_date). None if either end falls outside the series."""
    if stock is None or len(stock) == 0:
        return None
    stock = stock.sort_index()
    t = stock.index.searchsorted(pd.Timestamp(event_date))
    i, j = t + a, t + b
    if i < 0 or j >= len(stock) or t >= len(stock) or j <= i:
        return None
    d_i, d_j = stock.index[i], stock.index[j]
    bb = bench.sort_index()
    b_i, b_j = bb.asof(d_i), bb.asof(d_j)
    if pd.isna(b_i) or pd.isna(b_j) or b_i == 0 or stock.iloc[i] == 0:
        return None
    return float(stock.iloc[j] / stock.iloc[i] - 1 - (b_j / b_i - 1))
