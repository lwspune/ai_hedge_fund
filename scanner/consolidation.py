"""Price consolidation: a liquid stock trading in a tight range, and the first close outside it.

A consolidation is a 40-session window whose (highest high - lowest low) / mean close is <= 10%,
on a stock whose median daily turnover is >= Rs 1 crore (illiquid stocks look flat because nothing
trades). A breakout is the first close above the range high (up) or below the range low (down) —
the range is the window ending the session before, so it is frozen when the break happens. Wide-
range breakouts (a 40-day high / low out of a range > 10%) are recorded as the control. One event
per symbol, kind and direction per 40 sessions. Validation: scripts/validate_consolidation.py;
live scan: `python -m scanner.run consolidation`. Tested in tests/test_consolidation.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW = 40
MAX_RANGE = 0.10
MIN_TURNOVER_LAKH = 100.0      # Rs 1 crore / day, median over the window
PRIOR = 60                     # the move before the base: 60 sessions before the window starts


def _run_length(flags: pd.Series) -> pd.Series:
    """Consecutive True count ending at each row."""
    grp = (~flags).cumsum()
    return flags.astype(int).groupby(grp).cumsum()


def _window_stats(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Range stats of the n-session window ending at each row (not shifted)."""
    hi, lo = df["high"].rolling(n).max(), df["low"].rolling(n).min()
    mean_close = df["close"].rolling(n).mean()
    out = pd.DataFrame({"hi": hi, "lo": lo, "range": (hi - lo) / mean_close,
                        "liquid": df["turnover_lakh"].rolling(n).median() >= MIN_TURNOVER_LAKH,
                        "vol_mean": df["volume"].rolling(n).mean()}, index=df.index)
    out["tight"] = (out["range"] <= MAX_RANGE) & out["liquid"]
    out["run"] = _run_length(out["tight"].fillna(False))
    return out


def breakout_events(df: pd.DataFrame, symbol: str, n: int = WINDOW) -> list[dict]:
    """Every breakout of the window ending the session before: tight (the event) or wide (control).
    `df`: daily bars indexed by date with close, high, low, volume, turnover_lakh, delivery_pct."""
    if len(df) <= n:
        return []
    df = df.sort_index()
    w = _window_stats(df, n).shift(1)                       # the range as it stood before today
    prior = df["close"].shift(n) / df["close"].shift(n + PRIOR) - 1
    up, down = df["close"] > w["hi"], df["close"] < w["lo"]
    out, last = [], {}
    for i in np.flatnonzero((up | down).to_numpy() & w["liquid"].fillna(False).to_numpy().astype(bool)):
        t = df.index[i]
        tight = bool(w["tight"].iat[i])
        direction = "up" if up.iat[i] else "down"
        key = (tight, direction)
        if key in last and i - last[key] < n:
            continue
        last[key] = i
        vm = w["vol_mean"].iat[i]
        out.append({
            "symbol": symbol, "date": t, "direction": direction, "tight": tight,
            "range_pct": float(w["range"].iat[i]),
            "days_in_range": int(n + w["run"].iat[i] - 1) if tight else 0,
            "prior_move": float(prior.iat[i]) if pd.notna(prior.iat[i]) else None,
            "vol_ratio": float(df["volume"].iat[i] / vm) if vm and vm > 0 else None,
            "delivery_pct": float(df["delivery_pct"].iat[i]) if pd.notna(df["delivery_pct"].iat[i]) else None,
            "turnover_lakh": float(df["turnover_lakh"].iloc[max(0, i - n):i].median()),
            "close": float(df["close"].iat[i]),
        })
    return out


def current_state(df: pd.DataFrame, symbol: str, n: int = WINDOW) -> dict | None:
    """The live scan: is the stock in a tight range right now, for how long, and where in it."""
    if len(df) < n:
        return None
    df = df.sort_index()
    w = _window_stats(df, n).iloc[-1]
    last = df.iloc[-1]
    span = w["hi"] - w["lo"]
    recent = df["volume"].iloc[-10:].mean()
    return {"symbol": symbol, "date": df.index[-1], "in_range": bool(w["tight"]),
            "range_pct": float(w["range"]), "days_in_range": int(n + w["run"] - 1) if w["tight"] else 0,
            "position": float((last["close"] - w["lo"]) / span) if span > 0 else 0.5,
            "vol_trend": float(recent / w["vol_mean"]) if w["vol_mean"] else None,
            "close": float(last["close"]), "hi": float(w["hi"]), "lo": float(w["lo"])}
