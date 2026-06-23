"""Test-first spec for the event-study return math."""
import numpy as np
import pandas as pd
import pytest

from scanner.eventstudy import forward_abnormal_return, summarize


def _series(values, start="2025-01-01"):
    idx = pd.bdate_range(start=start, periods=len(values))
    return pd.Series(values, index=idx, dtype="float64")


def test_abnormal_is_stock_minus_bench_over_window():
    # Stock +10% over the window, benchmark +4% -> abnormal +6%.
    stock = _series([100, 100, 110] + [110] * 10)   # entry at idx1=100, exit at idx3=110
    bench = _series([200, 200, 208] + [208] * 10)   # 200 -> 208 = +4%
    car = forward_abnormal_return(stock, bench, t0="2025-01-01", horizon=2, entry_lag=1)
    assert car == pytest.approx(0.10 - 0.04, abs=1e-9)


def test_returns_none_when_pre_window_precedes_series_start():
    # entry_lag=-10 on an event near the series start -> negative index, must be None.
    stock = _series([100, 101, 102, 103, 104])
    bench = _series([200, 201, 202, 203, 204])
    assert forward_abnormal_return(stock, bench, t0="2025-01-01",
                                   horizon=10, entry_lag=-10) is None


def test_returns_none_when_too_recent():
    stock = _series([100, 101, 102])
    bench = _series([200, 201, 202])
    # horizon runs past the end of the series.
    assert forward_abnormal_return(stock, bench, t0="2025-01-01", horizon=20) is None


def test_returns_none_for_empty():
    assert forward_abnormal_return(pd.Series(dtype="float64"),
                                   _series([1, 2, 3]), t0="2025-01-01", horizon=1) is None


def test_summarize_basic_stats():
    s = summarize([0.10, -0.02, 0.04, None, 0.08])
    assert s["n"] == 4
    assert s["mean"] == pytest.approx((0.10 - 0.02 + 0.04 + 0.08) / 4)
    assert s["pct_positive"] == pytest.approx(0.75)


def test_summarize_empty():
    s = summarize([None, None])
    assert s["n"] == 0 and s["mean"] is None
