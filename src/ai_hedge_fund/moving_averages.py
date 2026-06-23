"""Moving average implementations matching the Google Sheets logic.

The user's sheets use a Linear-Weighted Moving Average (LWMA) where weights
are 1, 2, ..., N — newest bar gets the highest weight (= N), oldest gets 1.
Verified against column B of Stocks_Buy_Signal_Analyser_15Yr.xlsx.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def lwma(prices: pd.Series, period: int) -> pd.Series:
    """Linear-weighted moving average. Returns NaN for the first `period - 1` rows."""
    if period <= 0:
        raise ValueError("period must be >= 1")
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = weights.sum()

    return prices.rolling(window=period).apply(
        lambda w: float(np.dot(w, weights) / weight_sum),
        raw=True,
    )
