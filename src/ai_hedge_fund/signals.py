"""Trading signals ported from the user's Google Sheets.

Strategy 1 (the headline rule from Buy_Signal_Analyser_15Yr):
    Gain_100DMA_50DMA < 0
where Gain_100DMA_50DMA = LWMA(daily_slope_of_LWMA(close, 100), 50) - baseline.

Baseline (R4 cell) was empty in the audited file → treated as 0.
Verified clean of look-ahead bias on 2026-05-10.
"""
from __future__ import annotations

import pandas as pd

from .moving_averages import lwma


def gain_ma_smoothed(
    prices: pd.Series,
    ma_period: int,
    smooth_period: int,
    baseline: float = 0.0,
) -> pd.Series:
    """Double-smoothed daily returns — exactly matches the sheet's `Gain_NDMA_MDMA` formulas.

    Sheet construction (verified 2026-05-11 against Buy_Signal_Analyser_15Yr.xlsx):
      Col N = Price Gain = E_today / E_yesterday - 1  (daily returns)
      Col Q (Gain_100DMA) = LWMA(N, 100)
      Col R (Gain_100DMA_50DMA) = LWMA(Q, 50) - $R$4  ← baseline cell, treated as 0

    So the signal is: take daily returns → smooth them with a 100-bar LWMA →
    smooth that with a 50-bar LWMA → subtract baseline. This is double-smoothed
    return strength, NOT the slope of a smoothed price as I had it before.
    """
    daily_returns = prices.pct_change()
    layer1 = lwma(daily_returns, period=ma_period)
    layer2 = lwma(layer1, period=smooth_period)
    return layer2 - baseline


def strategy_1(prices: pd.Series) -> pd.Series:
    """Buy when the 50-day LWMA-smoothed slope of the 100DMA is negative.

    From the sheet: `Gain_100DMA_50DMA < 0`. Mean-reversion / "buy weakness".
    Returns a boolean Series; warmup bars (insufficient data) are False.
    """
    g = gain_ma_smoothed(prices, ma_period=100, smooth_period=50)
    return (g < 0).fillna(False)


def strategy_1_inverted(prices: pd.Series) -> pd.Series:
    """Inverse of Strategy 1: buy when the smoothed 100DMA slope is positive.

    Trend-following / "buy strength". If the original `< 0` rule loses
    significantly to buy-and-hold in trending markets, the inversion should win
    in those same regimes.
    """
    g = gain_ma_smoothed(prices, ma_period=100, smooth_period=50)
    return (g > 0).fillna(False)


def strategy_3(prices: pd.Series) -> pd.Series:
    """Stricter mean-reversion: Strategy 1 + price below 50DMA + 50DMA below 300DMA.

    From the sheet: `Gain_100DMA_50DMA < 0 AND price <= 50DMA AND 50DMA <= 300DMA`.
    All three conditions confirm a multi-timeframe downtrend before buying.
    """
    g = gain_ma_smoothed(prices, ma_period=100, smooth_period=50)
    ma_50 = lwma(prices, period=50)
    ma_300 = lwma(prices, period=300)
    cond = (g < 0) & (prices <= ma_50) & (ma_50 <= ma_300)
    return cond.fillna(False)


def price_signal(prices: pd.Series) -> pd.Series:
    """Composite trend indicator: +1/-1 for each of 3 stack conditions, summed and /1000.

    From the sheet: `Price_Signal = SUM(Price_GT_50DMA, 50DMA_GT_100DMA, 100DMA_GT_200DMA) / 1000`.
    Range: {-0.003, -0.001, +0.001, +0.003}. Negative = trend stack mostly bearish.
    """
    ma_50 = lwma(prices, period=50)
    ma_100 = lwma(prices, period=100)
    ma_200 = lwma(prices, period=200)
    price_gt_50 = (prices > ma_50).astype(int) * 2 - 1
    ma50_gt_ma100 = (ma_50 > ma_100).astype(int) * 2 - 1
    ma100_gt_ma200 = (ma_100 > ma_200).astype(int) * 2 - 1
    # NaN-aware: where any input is NaN, mark result NaN
    valid = ma_50.notna() & ma_100.notna() & ma_200.notna()
    raw = (price_gt_50 + ma50_gt_ma100 + ma100_gt_ma200) / 1000.0
    return raw.where(valid, other=float("nan"))


def strategy_2a(prices: pd.Series) -> pd.Series:
    """S1 + Price Signal < 0 (trend stack mostly bearish: at most 1 of 3 up-stack conditions hold)."""
    g = gain_ma_smoothed(prices, ma_period=100, smooth_period=50)
    ps = price_signal(prices)
    return ((g < 0) & (ps < 0)).fillna(False)


def strategy_2b(prices: pd.Series) -> pd.Series:
    """S1 + Price Signal < -0.001 (all three trend-stack conditions bearish)."""
    g = gain_ma_smoothed(prices, ma_period=100, smooth_period=50)
    ps = price_signal(prices)
    return ((g < 0) & (ps < -0.001)).fillna(False)


def strategy_4a(prices: pd.Series) -> pd.Series:
    """S1 + price below 300DMA + cross-UP through 50DMA today.

    Sheet conditions (row N):
      R_N<0 AND E_N<F_N AND E_(N-1)<=L_N AND E_N>=L_N
    Tactical reversal: in a long-term downtrend, the bar where price crosses
    back above the 50DMA from below.
    """
    g = gain_ma_smoothed(prices, ma_period=100, smooth_period=50)
    ma_50 = lwma(prices, period=50)
    ma_300 = lwma(prices, period=300)
    prev_close = prices.shift(1)
    cond = (
        (g < 0)
        & (prices < ma_300)
        & (prev_close <= ma_50)  # yesterday at/below today's 50DMA
        & (prices >= ma_50)      # today at/above today's 50DMA
    )
    return cond.fillna(False)


def strategy_4b(prices: pd.Series) -> pd.Series:
    """S4a + Gain_200DMA_50DMA < 0 (200DMA also showing weakness)."""
    g_100 = gain_ma_smoothed(prices, ma_period=100, smooth_period=50)
    g_200 = gain_ma_smoothed(prices, ma_period=200, smooth_period=50)
    ma_50 = lwma(prices, period=50)
    ma_300 = lwma(prices, period=300)
    prev_close = prices.shift(1)
    cond = (
        (g_200 < 0)
        & (g_100 < 0)
        & (prices < ma_300)
        & (prev_close <= ma_50)
        & (prices >= ma_50)
    )
    return cond.fillna(False)
