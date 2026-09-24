"""Trading-day arithmetic (DATA_INFRA_SPEC WP6): pure functions over a holiday set."""
from datetime import date

from scanner.trading_calendar import age_in_trading_days, is_trading_day, next_trading_day, trading_days_between

HOL = {date(2026, 10, 2)}   # Fri: Gandhi Jayanti


def test_is_trading_day():
    assert is_trading_day(date(2026, 10, 1), HOL)
    assert not is_trading_day(date(2026, 10, 2), HOL)
    assert not is_trading_day(date(2026, 10, 3), HOL)       # Saturday


def test_next_trading_day_skips_weekend_and_holiday():
    assert next_trading_day(date(2026, 10, 1), HOL) == date(2026, 10, 5)


def test_trading_days_between_half_open():
    # (Thu 1st, Mon 5th] = Mon only (Fri holiday, weekend)
    assert trading_days_between(date(2026, 10, 1), date(2026, 10, 5), HOL) == 1
    assert trading_days_between(date(2026, 10, 5), date(2026, 10, 5), HOL) == 0
    assert trading_days_between(date(2026, 10, 5), date(2026, 10, 1), HOL) == -1


def test_age_in_trading_days():
    # data from Thu 1st, checked Mon 5th: one trading day old (Mon's print not in yet)
    assert age_in_trading_days(date(2026, 10, 1), date(2026, 10, 5), HOL) == 1
    assert age_in_trading_days(None, date(2026, 10, 5), HOL) is None
