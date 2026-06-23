"""Tests for Strategy 1 (Gain_100DMA_50DMA < 0) signal computation."""
import numpy as np
import pandas as pd
import pytest

from ai_hedge_fund.signals import (
    strategy_1, strategy_1_inverted, strategy_3,
    strategy_2a, strategy_2b, strategy_4a, strategy_4b,
    price_signal, gain_ma_smoothed,
)


@pytest.fixture
def rising_prices():
    """200 bars of monotonically rising prices — 100DMA should rise → Gain_100DMA_50DMA > 0."""
    return pd.Series(np.linspace(100, 200, 200))


@pytest.fixture
def falling_prices():
    """200 bars of monotonically falling prices — 100DMA should fall → Gain_100DMA_50DMA < 0."""
    return pd.Series(np.linspace(200, 100, 200))


class TestGainMASmoothed:
    """`gain_ma_smoothed(prices, ma_period=N, smooth_period=M)` returns LWMA-smoothed daily slope of LWMA(N)."""

    def test_rising_prices_gives_positive_gain(self, rising_prices):
        result = gain_ma_smoothed(rising_prices, ma_period=100, smooth_period=50)
        # Last value should be positive (MA was rising)
        assert result.iloc[-1] > 0

    def test_falling_prices_gives_negative_gain(self, falling_prices):
        result = gain_ma_smoothed(falling_prices, ma_period=100, smooth_period=50)
        assert result.iloc[-1] < 0

    def test_warmup_period_returns_nan(self, rising_prices):
        """First valid value at index ma_period + smooth_period - 1 = 149 (0-indexed)."""
        result = gain_ma_smoothed(rising_prices, ma_period=100, smooth_period=50)
        # Need 100 bars for MA + 1 for pct_change + 49 for the 50-bar LWMA = 150 bars
        # First valid at index 149 (0-indexed)
        assert result.iloc[:148].isna().all()
        assert pd.notna(result.iloc[149])

    def test_constant_prices_gives_zero_gain(self):
        """Flat prices → MA flat → MA slope = 0 → smoothed slope = 0."""
        prices = pd.Series([100.0] * 200)
        result = gain_ma_smoothed(prices, ma_period=100, smooth_period=50)
        # After warmup, all should be 0
        np.testing.assert_allclose(result.iloc[150:].values, 0.0, atol=1e-10)


class TestStrategy1:
    """Strategy 1: signal = (Gain_100DMA_50DMA < 0)."""

    def test_signal_is_boolean_series(self, rising_prices):
        sig = strategy_1(rising_prices)
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool

    def test_no_signal_on_rising_prices(self, rising_prices):
        """In a rising market, Gain_100DMA_50DMA > 0 → no buy signal."""
        sig = strategy_1(rising_prices)
        # No signal anywhere after warmup
        assert not sig.iloc[150:].any()

    def test_signal_fires_on_falling_prices(self, falling_prices):
        """In a falling market, Gain_100DMA_50DMA < 0 → buy signal fires."""
        sig = strategy_1(falling_prices)
        # Signal should fire on at least some of the post-warmup bars
        assert sig.iloc[150:].any()
        # With monotonic decline, after warmup it should fire on every bar
        assert sig.iloc[150:].all()

    def test_warmup_period_no_signal(self, rising_prices):
        """During warmup (insufficient data for MA + smoothing), signal is False (not NaN)."""
        sig = strategy_1(rising_prices)
        # First ~149 bars: NaN comparison should evaluate to False
        assert not sig.iloc[:149].any()

    def test_preserves_index(self):
        idx = pd.date_range("2020-01-01", periods=200, freq="B")
        prices = pd.Series(np.linspace(100, 200, 200), index=idx)
        sig = strategy_1(prices)
        assert list(sig.index) == list(idx)


class TestStrategy1Inverted:
    """Inverted: signal = (Gain_100DMA_50DMA > 0)."""

    def test_fires_on_rising_prices(self, rising_prices):
        sig = strategy_1_inverted(rising_prices)
        assert sig.iloc[150:].all()

    def test_no_signal_on_falling_prices(self, falling_prices):
        sig = strategy_1_inverted(falling_prices)
        assert not sig.iloc[150:].any()

    def test_inverted_is_complement_of_original_post_warmup(self, rising_prices):
        """In post-warmup zone, exactly one of (s1, s1_inv) fires per bar — except when slope == 0 (neither)."""
        s1 = strategy_1(rising_prices)
        s1i = strategy_1_inverted(rising_prices)
        # No bar where both fire
        assert not (s1 & s1i).any()


class TestStrategy3:
    """Strategy 3: Gain_100DMA_50DMA < 0 AND price < 50DMA AND 50DMA < 300DMA."""

    def test_no_signal_on_rising_prices(self, rising_prices):
        """In a strong uptrend none of the three conditions hold."""
        sig = strategy_3(rising_prices)
        assert not sig.any()

    def test_fires_on_falling_prices(self, falling_prices):
        """In a falling market all three conditions should hold (after warmup of 300+ bars)."""
        # Need 300 bars for the 300DMA + 50 for smoothing = 350+ bars
        prices = pd.Series(np.linspace(500, 100, 400))
        sig = strategy_3(prices)
        # After warmup, signal should fire on at least some bars
        assert sig.iloc[350:].any()

    def test_strategy_3_is_subset_of_strategy_1(self, falling_prices):
        """Strategy 3 is more restrictive — its signal must imply Strategy 1's signal."""
        prices = pd.Series(np.linspace(500, 100, 400))
        s1 = strategy_1(prices)
        s3 = strategy_3(prices)
        # Whenever s3 fires, s1 must also fire
        assert (s3 & ~s1).sum() == 0

    def test_returns_boolean_series(self, rising_prices):
        sig = strategy_3(rising_prices)
        assert sig.dtype == bool


class TestPriceSignal:
    def test_rising_prices_give_positive(self):
        # Need 200+ bars for 200DMA to fully populate
        prices = pd.Series(np.linspace(100, 300, 300))
        ps = price_signal(prices)
        # Strong uptrend: all 3 conditions hold -> +0.003
        np.testing.assert_allclose(ps.iloc[200:].values, 0.003)

    def test_falling_prices_give_negative(self):
        prices = pd.Series(np.linspace(300, 100, 300))
        ps = price_signal(prices)
        np.testing.assert_allclose(ps.iloc[200:].values, -0.003)

    def test_warmup_returns_nan(self):
        prices = pd.Series(np.arange(100, 300, dtype=float))
        ps = price_signal(prices)
        # Need 200 bars for 200DMA; first valid at index 199
        assert ps.iloc[:198].isna().all()
        assert pd.notna(ps.iloc[199])


class TestStrategies2a2b:
    def test_2a_is_subset_of_1(self, falling_prices):
        s1 = strategy_1(falling_prices)
        s2a = strategy_2a(falling_prices)
        # Wherever 2a fires, 1 must fire
        assert (s2a & ~s1).sum() == 0

    def test_2b_is_subset_of_2a(self):
        prices = pd.Series(np.linspace(500, 100, 400))
        s2a = strategy_2a(prices)
        s2b = strategy_2b(prices)
        assert (s2b & ~s2a).sum() == 0

    def test_2a_no_signal_on_rising(self, rising_prices):
        assert not strategy_2a(rising_prices).any()


class TestStrategies4a4b:
    def test_4a_no_signal_on_strict_monotonic_decline(self, falling_prices):
        """In a strict monotonic decline, price never crosses up through 50DMA → no S4a signal."""
        sig = strategy_4a(falling_prices)
        assert not sig.any()

    def test_4a_fires_on_recovery_from_dip(self):
        """V-shaped pattern: long downtrend then a recovery should trigger S4a near the bottom turn."""
        # 300 bars of decline 500->100, then 100 bars of recovery 100->150
        decline = np.linspace(500, 100, 300)
        recovery = np.linspace(100, 150, 100)
        prices = pd.Series(np.concatenate([decline, recovery]))
        sig = strategy_4a(prices)
        # During recovery phase, signal should fire at least once when price crosses 50DMA
        assert sig.iloc[300:].any()

    def test_4b_is_subset_of_4a(self):
        decline = np.linspace(500, 100, 350)
        recovery = np.linspace(100, 150, 100)
        prices = pd.Series(np.concatenate([decline, recovery]))
        s4a = strategy_4a(prices)
        s4b = strategy_4b(prices)
        assert (s4b & ~s4a).sum() == 0
