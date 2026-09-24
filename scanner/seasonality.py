"""Turn-of-month calendar control (backlog #17): pure bucket math on an index series.

Expected null net of costs — the study exists to document the calendar effect's size, not to
trade it (an external 2021-26 NIFTYBEES backtest found +0.9%/yr gross, inside costs).
"""
from __future__ import annotations

import pandas as pd


def tom_flags(index: pd.DatetimeIndex, before: int = 1, after: int = 3) -> pd.Series:
    """True on the last `before` and first `after` trading days of each calendar month."""
    idx = pd.DatetimeIndex(index).sort_values()
    month = idx.to_period("M")
    pos = pd.Series(range(len(idx)), index=idx).groupby(month).cumcount()
    size = pd.Series(month, index=idx).map(pd.Series(month).value_counts())
    first = (pos < after).to_numpy().copy()
    last = (pos >= size.values - before).to_numpy().copy()
    # a series that starts or ends mid-month has a truncated month: its "first" / "last" trading
    # days are the sample's edges, not the calendar's
    if idx[0].day > 5:
        first &= (month != month[0])
    if idx[-1].day < 25:
        last &= (month != month[-1])
    return pd.Series(first | last, index=idx)


def bucket_returns(closes: pd.Series, before: int = 1, after: int = 3) -> dict[str, pd.Series]:
    """{'tom': daily returns on turn-of-month days, 'rest': the others}."""
    s = closes.sort_index()
    r = s.pct_change().dropna()
    f = tom_flags(s.index, before, after).reindex(r.index)
    return {"tom": r[f], "rest": r[~f]}
