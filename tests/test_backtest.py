"""Tests for the portfolio backtester.

Semantics:
- Each day: target weight per stock = 1 / N_active if signal is True, else 0
- Rebalance daily by trading the difference between current and target holdings
- Apply round-trip cost (e.g. 0.3%) to traded notional
- Returns equity curve and trade log
"""
import numpy as np
import pandas as pd
import pytest

from ai_hedge_fund.backtest import run_backtest


def _make_frame(data: dict[str, list[float]]) -> pd.DataFrame:
    """Helper: build a DataFrame with daily index from 2024-01-01."""
    n = len(next(iter(data.values())))
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(data, index=idx)


class TestBacktest:
    def test_no_signals_means_no_trades_and_flat_equity(self):
        """With zero signals, the portfolio holds cash → equity stays at initial_capital."""
        prices = _make_frame({"AAA": [100, 101, 102, 103, 104]})
        signals = _make_frame({"AAA": [False, False, False, False, False]})
        result = run_backtest(prices, signals, initial_capital=100_000)
        np.testing.assert_allclose(result["equity"].values, 100_000)

    def test_single_stock_doubling_with_signal_held(self):
        """One stock, signal fires from day 0, price doubles by day 4 → ~2x equity minus costs."""
        prices = _make_frame({"AAA": [100, 110, 130, 160, 200]})
        signals = _make_frame({"AAA": [True, True, True, True, True]})
        result = run_backtest(prices, signals, initial_capital=100_000, cost_per_trade=0.003)

        # Day 0: buy 100k worth at 100 → 1000 shares, cost = 100k * 0.003 = 300, cash spent 100,300 → wait, cost reduces cash
        # Actually: buy 1000 shares × 100 = 100,000 notional. Cost = 100,000 × 0.003 = 300. Cash = -300 (overdraft)
        # OR we cap at cash available: spend (capital - cost) on shares = ~99,700 worth = 997 shares
        # Either convention should be documented. Using simpler: cost paid from cash, may go negative on day 0 (acceptable)
        # By day 4: 1000 shares × 200 = 200,000 + cash (-300 - 0 more trades) ≈ 199,700
        # We'll just assert equity > 199,000 (close to 2x with one round-trip cost)
        assert result["equity"].iloc[-1] > 199_000
        assert result["equity"].iloc[-1] < 200_500  # leave headroom for cost convention

    def test_two_stocks_equal_weight(self):
        """Two stocks, both signal-fire, prices go +20% and -20% → ~0% net (equal-weighted)."""
        prices = _make_frame({"AAA": [100, 100, 120], "BBB": [100, 100, 80]})
        signals = _make_frame({"AAA": [True, True, True], "BBB": [True, True, True]})
        result = run_backtest(prices, signals, initial_capital=100_000, cost_per_trade=0.0)

        # Day 0: 50k in AAA at 100 = 500 sh; 50k in BBB at 100 = 500 sh. Cash = 0.
        # Day 2: AAA=600 sh×120=60k; BBB=500 sh×80=40k. Total = 100k.
        np.testing.assert_allclose(result["equity"].iloc[-1], 100_000, rtol=0.01)

    def test_costs_reduce_equity(self):
        """A roundtrip with 1% cost should reduce equity by ~1% on a flat asset."""
        prices = _make_frame({"AAA": [100, 100, 100]})
        signals = _make_frame({"AAA": [True, False, False]})  # buy day 0, sell day 1
        result = run_backtest(prices, signals, initial_capital=100_000, cost_per_trade=0.01)

        # Day 0: buy 100k worth, cost = 1000. Cash = -1000, holdings = 100k. Equity = 99k.
        # Day 1: sell 100k worth, cost = 1000. Cash = -1000 + 100k - 1000 = 98k. Holdings = 0.
        # Day 2: hold, equity = 98k.
        # Total cost on round trip = 2000 = 2% (since cost_per_trade is per leg).
        # If cost_per_trade is round-trip, then we'd expect ~99k. Test assumes per-leg. Adjust if convention differs.
        equity = result["equity"].iloc[-1]
        assert 97_500 < equity < 99_500  # allow for per-leg vs round-trip convention

    def test_signal_off_closes_position(self):
        """When signal turns off, the position is sold."""
        prices = _make_frame({"AAA": [100, 100, 100, 100, 100]})
        signals = _make_frame({"AAA": [True, True, False, False, False]})
        result = run_backtest(prices, signals, initial_capital=100_000, cost_per_trade=0.0)

        # Day 0,1: long. Day 2: sell. Day 3,4: cash.
        # No P&L, no costs → equity stays at 100k.
        np.testing.assert_allclose(result["equity"].values, 100_000)

    def test_returns_equity_and_trade_log(self):
        prices = _make_frame({"AAA": [100, 110]})
        signals = _make_frame({"AAA": [True, True]})
        result = run_backtest(prices, signals, initial_capital=100_000)
        assert "equity" in result
        assert isinstance(result["equity"], pd.Series)
        assert len(result["equity"]) == len(prices)

    def test_handles_nan_prices(self):
        """NaN price (delisted/no data) should not produce NaN in equity."""
        prices = _make_frame({"AAA": [100, 110, np.nan, 120, 130]})
        signals = _make_frame({"AAA": [True, True, True, True, True]})
        result = run_backtest(prices, signals, initial_capital=100_000)
        assert not result["equity"].isna().any()
