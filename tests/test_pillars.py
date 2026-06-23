"""Tests for the 3 production pillars (EMA, Drawdown, Zone) and Aggregate ensemble."""
import numpy as np
import pandas as pd
import pytest

from ai_hedge_fund.pillars import (
    ema_pillar, drawdown_pillar, zone_pillar,
    aggregate_signal, signal_count_pct,
)


@pytest.fixture
def rising_prices():
    return pd.Series(np.linspace(100, 200, 400))


@pytest.fixture
def falling_prices():
    return pd.Series(np.linspace(200, 100, 400))


class TestEMAPillar:
    """Sheet rule (audited 2026-06-12): `IF(WMA_N >= price, "Yes")` → price AT/BELOW
    the moving average. Mean-reversion / buy-the-dip, NOT trend-following."""

    def test_no_signal_in_uptrend(self, rising_prices):
        sig = ema_pillar(rising_prices)
        # Rising series: price stays above its lagging LWMA → price > MA → no buy
        assert not sig.iloc[300:].any()

    def test_fires_in_strict_downtrend(self, falling_prices):
        sig = ema_pillar(falling_prices)
        # Falling series: price below its lagging LWMA → price <= MA → buy fires
        assert sig.iloc[300:].all()


class TestDrawdownPillar:
    def test_no_signal_on_rising_prices(self, rising_prices):
        sig = drawdown_pillar(rising_prices, threshold=0.10)
        assert not sig.any()

    def test_fires_after_drawdown(self):
        # Build a peak-and-fall: 100 → 200 → 150 (-25% drawdown)
        prices = pd.Series([100, 150, 200, 180, 160, 150])
        sig = drawdown_pillar(prices, threshold=0.10)
        # At index 3 (price=180): drawdown from 200 = -10%, should fire
        assert sig.iloc[3]
        # At index 5 (price=150): drawdown = -25%, fires
        assert sig.iloc[5]

    def test_threshold_respected(self):
        prices = pd.Series([100, 200, 195])  # -2.5% drawdown
        sig = drawdown_pillar(prices, threshold=0.10)
        assert not sig.any()


class TestZonePillar:
    def test_no_signal_on_strict_uptrend(self, rising_prices):
        # In monotone rising, every bar IS the max but no bar is the rolling MIN
        # (the min keeps being the start of the window)
        sig = zone_pillar(rising_prices)
        # The first bar of each rolling window IS the rolling min — but `prices.rolling().min()` returns
        # NaN for the first N-1 bars. So actual "at low" only fires for bars where current = window min.
        # In monotone rising, the window min = oldest bar in window, which the current bar equals only
        # at the first valid bar. Should fire ~rarely.
        # Just verify it doesn't fire for the bulk of the post-warmup period.
        assert sig.iloc[310:].sum() < 5

    def test_fires_at_50_day_low(self):
        # Construct: rises 0→50, then crashes to a new low
        rise = np.linspace(100, 200, 100)
        crash = np.linspace(200, 50, 100)
        prices = pd.Series(np.concatenate([rise, crash]))
        sig = zone_pillar(prices)
        # At the very last bar (50), it IS the 50-day low
        assert sig.iloc[-1]


class TestAggregate:
    def test_mode_breadth_ordering(self):
        # Construct prices: rising → drawdown → recovery
        rise = np.linspace(100, 200, 200)
        drop = np.linspace(200, 140, 100)  # -30% drawdown
        prices = pd.Series(np.concatenate([rise, drop]))
        sig_any = aggregate_signal(prices, mode="any")
        sig_majority = aggregate_signal(prices, mode="majority")
        sig_all = aggregate_signal(prices, mode="all")
        # ANY should be at least as broad as MAJORITY which is at least as broad as ALL
        assert sig_any.sum() >= sig_majority.sum() >= sig_all.sum()

    def test_default_mode_is_production_all(self):
        # Sheet's Overall/Buy = IF(SUM(pillars)=3) → ALL 3 pillars. The default must
        # reproduce that, not the looser ANY rule.
        rise = np.linspace(100, 200, 200)
        drop = np.linspace(200, 140, 100)
        prices = pd.Series(np.concatenate([rise, drop]))
        assert aggregate_signal(prices).equals(aggregate_signal(prices, mode="all"))

    def test_invalid_mode_raises(self):
        prices = pd.Series([100.0] * 50)
        with pytest.raises(ValueError):
            aggregate_signal(prices, mode="bogus")


class TestSignalCountPct:
    def test_returns_fraction_in_zero_one(self, rising_prices):
        s = signal_count_pct(rising_prices)
        valid = s.dropna()
        assert (valid >= 0).all() and (valid <= 1).all()

    def test_higher_in_drawdown_than_uptrend(self):
        # EMA is now mean-reversion: in a pure uptrend price > MA, so EMA, drawdown
        # and zone all contribute ~0 → score near 0.
        rise = pd.Series(np.linspace(100, 300, 400))
        s_up = signal_count_pct(rise).iloc[-50:].mean()
        assert s_up < 0.10
        # In a sustained drawdown, price <= MA (EMA fires) and drawdown thresholds
        # trip → score clearly higher than in the uptrend.
        drop = pd.Series(np.concatenate([np.linspace(100, 300, 200),
                                         np.linspace(300, 180, 200)]))
        s_down = signal_count_pct(drop).iloc[-50:].mean()
        assert s_down > s_up
