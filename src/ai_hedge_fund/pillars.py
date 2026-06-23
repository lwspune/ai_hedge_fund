"""The 3 production pillars from the user's Aggregate sheet: EMA, Drawdown, Zone.

Each pillar uses an ANY rule across 4 sub-signals (per the audit on 2026-05-10).
The Drawdown pillar's 4 thresholds (10/15/20/30%) are cumulative, so the ANY rule
collapses to a single check: drawdown <= -10%. Documented and accepted.

Formula audit (2026-06-12, from Stocks_{EMA,Drawdown,Zone,Aggregate}_Signal.xlsx):
all three pillars are "buy weakness" / mean-reversion signals. The EMA pillar fires
when price is AT/BELOW its moving average (`IF(WMA_N >= price, "Yes")`), NOT above —
the inverse of the original implementation. Drawdown (expanding-ATH cummax) and Zone
(price == rolling N-day low) were already faithful. The Aggregate's Overall/Buy is
ALL 3 pillars (`IF(SUM(pillars)=3)`), so `aggregate_signal` defaults to mode="all".
"""
from __future__ import annotations

import pandas as pd

from .moving_averages import lwma


def ema_pillar(prices: pd.Series) -> pd.Series:
    """ANY of: price <= 50/100/200/300-day LWMA. Mean-reversion / buy-the-dip.

    Sheet rule (audited): `IF(WMA_N >= price, "Yes")` — buy when price has fallen
    to or below its moving average. Sub-signals are independent across timeframes
    (price can be below the short MA but above the long MA, etc.); ANY rule fires
    whenever at least one timeframe says "price is at/below trend".
    """
    below_50 = prices <= lwma(prices, 50)
    below_100 = prices <= lwma(prices, 100)
    below_200 = prices <= lwma(prices, 200)
    below_300 = prices <= lwma(prices, 300)
    return (below_50 | below_100 | below_200 | below_300).fillna(False)


def drawdown_pillar(prices: pd.Series, threshold: float = 0.10) -> pd.Series:
    """Buy when current drawdown from cumulative peak is at least `threshold` (default 10%).

    Sheet uses 4 thresholds (10/15/20/30%) with cumulative-Yes pattern, so under
    the ANY rule the pillar fires iff the smallest threshold is hit. Default
    threshold = 0.10 reproduces the production behavior.

    Uses a small float tolerance (1e-9) so exact-threshold drawdowns trigger.
    """
    peak = prices.cummax()
    dd = prices / peak - 1
    return (dd <= -threshold + 1e-9).fillna(False)


def zone_pillar(prices: pd.Series) -> pd.Series:
    """ANY of: price at the rolling 50/100/200/300-day low.

    "At low" = price equals the rolling minimum. Independent across timeframes:
    a 50-day low isn't necessarily a 200-day low.
    """
    at_50 = prices <= prices.rolling(50, min_periods=50).min()
    at_100 = prices <= prices.rolling(100, min_periods=100).min()
    at_200 = prices <= prices.rolling(200, min_periods=200).min()
    at_300 = prices <= prices.rolling(300, min_periods=300).min()
    return (at_50 | at_100 | at_200 | at_300).fillna(False)


def aggregate_signal(prices: pd.Series, mode: str = "all") -> pd.Series:
    """Combine the three pillars into a single buy signal.

    Default mode="all" reproduces the sheet's production `Overall/Buy`
    (`IF(SUM(pillars)=3, "Yes")` — all 3 pillars must fire). "any"/"majority"
    are looser variants kept for experimentation.

    Args:
        mode: "all"      → all 3 pillars fire (sheet's Overall/Buy; default)
              "majority" → at least 2 of 3 pillars fire
              "any"      → at least one pillar fires (most permissive)
    """
    e = ema_pillar(prices).astype(int)
    d = drawdown_pillar(prices).astype(int)
    z = zone_pillar(prices).astype(int)
    n = e + d + z
    if mode == "any":
        return n >= 1
    if mode == "majority":
        return n >= 2
    if mode == "all":
        return n >= 3
    raise ValueError(f"unknown mode {mode!r}; expected 'any', 'majority', or 'all'")


def signal_count_pct(prices: pd.Series) -> pd.Series:
    """Continuous Signal/Count score: fraction of all 12 sub-signals firing.

    EMA(4) + Drawdown(4) + Zone(4) = 12 sub-signals. Returns a value in [0, 1].
    Useful for position-sizing or confidence-weighted allocation.

    NOTE: Drawdown sub-signals are cumulative; deeper drawdowns trigger more
    sub-signals at once. So Drawdown contribution is in {0, 1, 2, 3, 4}/4
    based on actual drawdown depth. EMA and Zone are independent.
    """
    # EMA: 4 independent at/below-MA conditions (mean-reversion, audited 2026-06-12)
    ema_count = sum((prices <= lwma(prices, p)).astype(int) for p in (50, 100, 200, 300))

    # Drawdown: count thresholds met
    peak = prices.cummax()
    dd = prices / peak - 1
    dd_count = (
        (dd <= -0.10).astype(int)
        + (dd <= -0.15).astype(int)
        + (dd <= -0.20).astype(int)
        + (dd <= -0.30).astype(int)
    )

    # Zone: 4 independent rolling-low conditions
    zone_count = sum(
        (prices <= prices.rolling(p, min_periods=p).min()).astype(int)
        for p in (50, 100, 200, 300)
    )

    total = (ema_count + dd_count + zone_count) / 12.0
    return total
