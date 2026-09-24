"""NSE trading-day arithmetic (DATA_INFRA_SPEC WP6).

Pure functions take the holiday set explicitly; `holidays()` loads it once per process from
the `trading_calendar` table (weekday rows with is_trading=false), refreshed weekly from NSE's
holiday master by `scripts/refresh_events.py holidays`. If the table can't be read, it falls
back to weekends-only (and says so) rather than failing a scan.
Named trading_calendar, not calendar, so it never shadows the stdlib module.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def is_trading_day(d: date, hol) -> bool:
    return d.weekday() < 5 and d not in hol


def next_trading_day(d: date, hol) -> date:
    d += timedelta(days=1)
    while not is_trading_day(d, hol):
        d += timedelta(days=1)
    return d


def trading_days_between(a: date, b: date, hol) -> int:
    """Trading days in (a, b]; negative when b < a."""
    if b < a:
        return -trading_days_between(b, a, hol)
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += is_trading_day(d, hol)
    return n


def age_in_trading_days(newest: date | None, today: date, hol) -> int | None:
    """How many trading days have passed since `newest` (0 = up to date)."""
    return None if newest is None else trading_days_between(newest, today, hol)


def window_start(today: date, n_trading: int, hol) -> date:
    """First day of the window holding the last `n_trading` trading days up to today."""
    d, seen = today, 0
    while True:
        if is_trading_day(d, hol):
            seen += 1
            if seen == n_trading:
                return d
        d -= timedelta(days=1)


@lru_cache(maxsize=1)
def holidays() -> frozenset:
    try:
        from scanner import db
        rows = db.select_all("trading_calendar", {"select": "trade_date", "is_trading": "eq.false"})
        return frozenset(date.fromisoformat(r["trade_date"]) for r in rows)
    except Exception as e:
        print(f"  trading_calendar unavailable ({e}); weekends-only calendar")
        return frozenset()
