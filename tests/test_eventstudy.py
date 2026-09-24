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


def test_summarize_cluster_t_shrinks_when_events_share_a_date():
    # Two clusters of perfectly correlated events: the iid t treats 8 observations as
    # independent; the cluster-robust t must see only 2 clusters and be smaller.
    cars = [0.05] * 4 + [-0.01] * 4
    s = summarize(cars, clusters=["a"] * 4 + ["b"] * 4)
    assert s["n_clusters"] == 2
    assert s["t_cluster"] is not None and abs(s["t_cluster"]) < abs(s["t_stat"])


def test_summarize_cluster_t_equals_iid_t_when_every_event_is_its_own_cluster():
    cars = [0.10, -0.02, 0.04, 0.08, -0.03]
    s = summarize(cars, clusters=list(range(5)))
    # one observation per cluster: the Liang-Zeger SE reduces to sqrt(sum e^2)/n, the ddof=0
    # variant of the iid SE, so t_cluster = t_iid * std1/std0 = t_iid * sqrt(n/(n-1)).
    assert s["t_cluster"] == pytest.approx(s["t_stat"] * np.sqrt(5 / (5 - 1)), rel=1e-9)


def test_summarize_cluster_labels_skip_none_cars_and_need_two_clusters():
    s = summarize([0.1, None, 0.2], clusters=["x", "y", "x"])
    assert s["n"] == 2 and s["n_clusters"] == 1 and s["t_cluster"] is None


def test_summarize_without_clusters_has_no_cluster_fields():
    assert "t_cluster" not in summarize([0.1, 0.2])
