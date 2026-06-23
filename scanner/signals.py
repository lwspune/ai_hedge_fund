"""Pure mean-reversion signal math — no I/O, no network.

The signal: a name is flagged when it is both technically oversold
(RSI under a threshold AND price meaningfully below its 200-DMA) and passes a
fundamental quality gate (large enough, low enough debt). Keeping this layer
pure makes it deterministically testable and reusable by a future backtest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(closes, period: int = 14) -> float:
    """Latest Wilder RSI of a close series. Raises if fewer than period+1 points."""
    s = pd.Series(list(closes), dtype="float64")
    if len(s) < period + 1:
        raise ValueError(f"need at least {period + 1} closes for RSI({period}), got {len(s)}")

    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder smoothing ~ EWM with alpha = 1/period.
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    last_gain = float(avg_gain.iloc[-1])
    last_loss = float(avg_loss.iloc[-1])
    if last_loss == 0:
        return 100.0 if last_gain > 0 else 50.0  # no losses (or flat) -> saturated/neutral
    rs = last_gain / last_loss
    return 100.0 - 100.0 / (1.0 + rs)


def pct_from_sma(closes, window: int = 200) -> float:
    """Signed fractional distance of the last close from its `window`-day SMA.

    -0.20 means the price is 20% below the moving average. Raises if too short.
    """
    s = pd.Series(list(closes), dtype="float64")
    if len(s) < window:
        raise ValueError(f"need at least {window} closes for SMA({window}), got {len(s)}")
    sma = s.iloc[-window:].mean()
    last = float(s.iloc[-1])
    return last / float(sma) - 1.0


def passes_quality(market_cap_cr, debt_to_equity, min_mcap_cr: float, max_de: float) -> bool:
    """Fundamental gate: large enough AND low enough debt.

    Missing fundamentals fail closed — an unknown never silently passes.
    """
    if market_cap_cr is None or debt_to_equity is None:
        return False
    return float(market_cap_cr) >= min_mcap_cr and float(debt_to_equity) <= max_de


def evaluate(closes, market_cap_cr, debt_to_equity, cfg: dict) -> dict:
    """Run the full signal for one name. Returns metrics + pass flags + verdict."""
    r = rsi(closes, period=cfg["rsi_period"])
    dist = pct_from_sma(closes, window=cfg["dma_window"])
    quality_ok = passes_quality(
        market_cap_cr, debt_to_equity, cfg["min_mcap_cr"], cfg["max_de"]
    )

    oversold = r < cfg["rsi_max"]
    below_dma = dist <= -abs(cfg["below_dma_min"])
    signal = bool(oversold and below_dma and quality_ok)

    return {
        "rsi": r,
        "pct_from_dma": dist,
        "market_cap_cr": market_cap_cr,
        "debt_to_equity": debt_to_equity,
        "oversold": oversold,
        "below_dma": below_dma,
        "quality_ok": quality_ok,
        "signal": signal,
    }
