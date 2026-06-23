"""Tests for performance metrics: CAGR, Sharpe, Sortino, max drawdown."""
import numpy as np
import pandas as pd
import pytest

from ai_hedge_fund.metrics import cagr, sharpe_ratio, sortino_ratio, max_drawdown, summarize


def _equity_series(values, start="2020-01-01", freq="B"):
    idx = pd.date_range(start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


class TestCAGR:
    def test_doubling_in_one_year(self):
        # 252 business days = roughly 1 year. 100k → 200k → 100% return.
        eq = _equity_series([100_000] + [200_000] * 251)
        # Period is from idx[0] to idx[-1] = 251 business days ≈ 251/252 years
        result = cagr(eq)
        # Roughly 100% (might be slightly more due to fractional years)
        assert 0.95 < result < 1.10

    def test_no_growth_returns_zero(self):
        eq = _equity_series([100_000] * 252)
        assert cagr(eq) == pytest.approx(0.0, abs=1e-6)

    def test_loss_returns_negative(self):
        eq = _equity_series([100_000] + [50_000] * 251)
        result = cagr(eq)
        assert result < -0.40  # ~50% loss in ~1 year


class TestSharpe:
    def test_zero_volatility_returns_inf_or_nan(self):
        eq = _equity_series([100_000] * 100)
        result = sharpe_ratio(eq)
        # Constant equity → zero return std → undefined Sharpe.
        assert np.isnan(result) or np.isinf(result)

    def test_positive_returns_give_positive_sharpe(self):
        # Daily returns of +0.1% — definitely positive Sharpe
        rets = [100_000]
        for _ in range(252):
            rets.append(rets[-1] * 1.001)
        eq = _equity_series(rets)
        assert sharpe_ratio(eq) > 0


class TestMaxDrawdown:
    def test_no_drawdown(self):
        eq = _equity_series([100, 110, 120, 130, 140])
        assert max_drawdown(eq) == pytest.approx(0.0)

    def test_50_percent_drawdown(self):
        eq = _equity_series([100, 200, 100])
        # Peak 200 → 100, so drawdown = -50%
        assert max_drawdown(eq) == pytest.approx(-0.50)

    def test_drawdown_then_recovery(self):
        eq = _equity_series([100, 200, 50, 300])
        # Worst drawdown: 200 → 50 = -75%, even though it recovers
        assert max_drawdown(eq) == pytest.approx(-0.75)


class TestSortino:
    def test_no_negative_returns_gives_inf(self):
        # All positive returns → no downside vol → Sortino is inf or nan
        rets = [100_000]
        for _ in range(100):
            rets.append(rets[-1] * 1.001)
        eq = _equity_series(rets)
        result = sortino_ratio(eq)
        assert np.isnan(result) or np.isinf(result) or result > 100  # very large


class TestSummarize:
    def test_returns_dict_with_all_metrics(self):
        eq = _equity_series([100_000] + [105_000] * 251)
        s = summarize(eq)
        for key in ["cagr", "sharpe", "sortino", "max_drawdown", "total_return"]:
            assert key in s
