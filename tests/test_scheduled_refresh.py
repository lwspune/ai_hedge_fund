"""The scheduled-refresh plan: which scripts run, with which args, per cadence."""
from datetime import date

import pytest

from scripts.scheduled_refresh import steps


def test_daily_steps_cover_events_and_self_heal_deals():
    s = steps("daily", date(2026, 9, 24))
    assert ["refresh_events.py", "actions"] in s
    assert ["refresh_events.py", "fo-ban"] in s
    assert ["refresh_events.py", "ipos"] in s
    assert ["refresh_events.py", "rights"] in s
    assert ["refresh_events.py", "board-meetings"] in s   # results dates (WP6)
    assert ["refresh_events.py", "bands"] in s
    px = s.index(["refresh_prices.py"])                     # cloud price store (WP3)
    assert s.index(["refresh_events.py", "fo-ban"]) < px < s.index(["-m", "scanner.run", "buyback_arb", "--save"])
    assert px < s.index(["-m", "scanner.run", "rights_re", "--save"])   # scans read today's closes
    assert ["refresh_filings.py"] in s
    assert s.index(["extract_kpis.py", "--limit", "1500"]) > s.index(["refresh_filings.py"])
    assert ["refill_deals.py", "--from", "2026-09-14"] in s  # 10-day lookback heals pauses
    assert ["-m", "scanner.run", "buyback_arb", "--save"] in s  # primary signal refreshed daily
    assert ["-m", "scanner.run", "rights_re", "--save"] in s   # RE panel data
    assert s[-1] == ["check_freshness.py"]  # silent staleness fails the run


def test_weekly_steps_refresh_master_before_fundamentals():
    s = steps("weekly", date(2026, 9, 27))
    assert s.index(["refresh_companies.py"]) < s.index(["refresh_fundamentals.py"])
    assert ["refresh_events.py", "holidays"] in s          # trading calendar (WP6)
    assert ["refresh_prices.py", "--prune"] in s           # daily_prices retention (WP3)
    assert ["archive_filings.py"] in s                     # filings retention (WP8)
    assert s[-1] == ["check_freshness.py"]


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        steps("hourly", date(2026, 9, 24))


def test_command_runs_scripts_by_path_and_modules_with_dash_m():
    import sys
    from pathlib import Path
    from scripts.scheduled_refresh import ROOT, command
    assert command(["refresh_events.py", "ipos"]) == [sys.executable, "-u", str(ROOT / "scripts" / "refresh_events.py"), "ipos"]
    assert command(["-m", "scanner.run", "x"]) == [sys.executable, "-u", "-m", "scanner.run", "x"]
