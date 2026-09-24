"""The scheduled-refresh plan: which scripts run, with which args, per cadence."""
from datetime import date

import pytest

from scripts.scheduled_refresh import steps


def test_daily_steps_cover_events_and_self_heal_deals():
    s = steps("daily", date(2026, 9, 24))
    assert ["refresh_events.py", "actions"] in s
    assert ["refresh_events.py", "fo-ban"] in s
    assert ["refresh_events.py", "ipos"] in s
    assert ["refill_deals.py", "--from", "2026-09-14"] in s  # 10-day lookback heals pauses


def test_weekly_steps_refresh_master_before_fundamentals():
    s = steps("weekly", date(2026, 9, 27))
    assert s == [["refresh_companies.py"], ["refresh_fundamentals.py"],
                 ["rebuild_snapshot_history.py"]]


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        steps("hourly", date(2026, 9, 24))
