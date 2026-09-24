"""Test-first spec for the turn-of-month control (backlog #17): calendar buckets on an index."""
import pandas as pd

from scanner.seasonality import bucket_returns, tom_flags


def _idx():
    # Jan 2026 trading days (weekdays) + first days of Feb
    days = pd.bdate_range("2026-01-26", "2026-02-06")
    return pd.Series(range(1, len(days) + 1), index=days, dtype="float64")


def test_tom_flags_mark_last_k_and_first_k_trading_days_of_each_month():
    s = _idx()
    f = tom_flags(s.index, before=1, after=3)
    assert list(f[f].index.strftime("%Y-%m-%d")) == ["2026-01-30", "2026-02-02", "2026-02-03", "2026-02-04"]


def test_bucket_returns_splits_daily_returns_by_flag():
    s = _idx()
    r = bucket_returns(s, before=1, after=3)
    assert set(r) == {"tom", "rest"}
    assert len(r["tom"]) + len(r["rest"]) == len(s) - 1   # first day has no return
    assert abs(r["tom"].sum() + r["rest"].sum() - s.pct_change().dropna().sum()) < 1e-12
