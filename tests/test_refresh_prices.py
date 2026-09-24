"""refresh_prices planning helpers (DATA_INFRA_SPEC WP3)."""
from datetime import date

from scripts.refresh_prices import calendar_from_presence, in_table_window, months_of


def test_calendar_from_presence_marks_past_weekdays_only():
    checked = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 5)]
    present = {date(2026, 10, 1), date(2026, 10, 5)}
    rows = calendar_from_presence(checked, present, today=date(2026, 10, 5))
    # Sat 3rd skipped (weekend); Mon 5th = today, not yet final -> skipped
    assert rows == [
        {"trade_date": "2026-10-01", "is_trading": True, "description": None, "source": "nse_bhavcopy"},
        {"trade_date": "2026-10-02", "is_trading": False, "description": None, "source": "nse_bhavcopy"},
    ]


def test_in_table_window():
    today = date(2026, 9, 24)
    assert in_table_window(date(2024, 9, 25), today, keep_days=730)
    assert not in_table_window(date(2024, 9, 23), today, keep_days=730)


def test_months_of_groups_dates():
    ds = [date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)]
    assert months_of(ds) == {"2026-08": [date(2026, 8, 31)], "2026-09": [date(2026, 9, 1), date(2026, 9, 2)]}


def test_holiday_copy_of_previous_day_is_not_a_trading_day():
    """NSE serves the previous session's file under a holiday's name (2026-09-14 -> 09-11 data)."""
    from scripts.refresh_prices import file_is_for
    rows = [{"symbol": "X", "trade_date": "2026-09-11"}]
    assert file_is_for(rows, date(2026, 9, 11))
    assert not file_is_for(rows, date(2026, 9, 14))
