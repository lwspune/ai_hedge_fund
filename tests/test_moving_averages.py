"""Tests for linear-weighted moving average matching the sheet's behavior."""
import numpy as np
import pandas as pd
import pytest

from ai_hedge_fund.moving_averages import lwma


class TestLWMA:
    def test_basic_5_period_window_3(self):
        """LWMA(period=3) on [10,11,12,13,14] — verified by hand against the sheet formula."""
        # weights for each window: oldest=1, newest=3
        # window of 3 sums: (oldest*1 + middle*2 + newest*3) / 6
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
        result = lwma(prices, period=3)

        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])
        # at index 2: (10*1 + 11*2 + 12*3) / 6 = 68/6
        assert result.iloc[2] == pytest.approx(68 / 6)
        # at index 3: (11*1 + 12*2 + 13*3) / 6 = 74/6
        assert result.iloc[3] == pytest.approx(74 / 6)
        # at index 4: (12*1 + 13*2 + 14*3) / 6 = 80/6
        assert result.iloc[4] == pytest.approx(80 / 6)

    def test_period_larger_than_series(self):
        """If period > len(prices), every value is NaN."""
        prices = pd.Series([1.0, 2.0, 3.0])
        result = lwma(prices, period=10)
        assert result.isna().all()

    def test_constant_series_returns_constant(self):
        """LWMA of a flat series equals the constant (after warmup)."""
        prices = pd.Series([5.0] * 20)
        result = lwma(prices, period=5)
        # first 4 values are NaN, rest should be 5.0
        assert result.iloc[:4].isna().all()
        np.testing.assert_allclose(result.iloc[4:].values, 5.0)

    def test_recency_weighted_higher_than_simple_average(self):
        """For an upward-trending series, LWMA > SMA (recent bars weighted more)."""
        prices = pd.Series(np.arange(1, 21, dtype=float))  # 1..20 increasing
        wma = lwma(prices, period=10)
        sma = prices.rolling(window=10).mean()
        # at index 9 (first valid): SMA = (1+2+...+10)/10 = 5.5
        # LWMA at idx 9: (1*1 + 2*2 + ... + 10*10) / sum(1..10) = 385 / 55 = 7.0
        assert sma.iloc[9] == pytest.approx(5.5)
        assert wma.iloc[9] == pytest.approx(7.0)
        # LWMA strictly greater than SMA on rising series
        assert (wma.iloc[9:] > sma.iloc[9:]).all()

    def test_matches_sheet_formula_period_20(self):
        """Reproduce the sheet's =SUMPRODUCT(E6:E25, $B$6:$B$25)/SUM($B$6:$B$25) for period=20."""
        # Synthetic 25-bar series
        prices = pd.Series([100.0 + i for i in range(25)])  # 100, 101, ..., 124
        wma = lwma(prices, period=20)
        # at index 19 (20-bar lookback complete): weights sum = 1+2+...+20 = 210
        # weighted sum = sum_{i=0..19} price[i] * (i+1) = sum_{i=0..19} (100+i)*(i+1)
        #             = 100*sum(1..20) + sum(i*(i+1) for i in 0..19)
        #             = 100*210 + sum_{i=0..19} (i^2 + i)
        # i^2 sum 0..19 = 19*20*39/6 = 2470
        # i sum 0..19 = 190
        # so weighted sum = 21000 + 2470 + 190 = 23660
        # WMA = 23660 / 210 = 112.6666...
        assert wma.iloc[19] == pytest.approx(23660 / 210)

    def test_returns_pandas_series_with_same_index(self):
        """Output should be a pandas Series with the same index as input."""
        idx = pd.date_range("2024-01-01", periods=10, freq="D")
        prices = pd.Series(range(10, 20), index=idx, dtype=float)
        result = lwma(prices, period=3)
        assert isinstance(result, pd.Series)
        assert list(result.index) == list(idx)
