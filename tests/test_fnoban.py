"""Test-first spec for the F&O ban reversal study (candidate signal #6)."""
import pandas as pd
import pytest

from scanner.fnoban import ban_episodes, reversal, far_from_bans, WINDOWS

CAL = pd.bdate_range("2024-01-01", "2024-03-29")  # trading calendar (weekdays)


def test_ban_episodes_group_consecutive_trading_days_across_weekends():
    rows = [("ABC", "2024-01-04"), ("ABC", "2024-01-05"), ("ABC", "2024-01-08"),  # Thu, Fri, Mon
            ("ABC", "2024-01-15"),                                               # new episode
            ("XYZ", "2024-01-05")]
    eps = ban_episodes(rows, CAL)
    assert [(e["symbol"], e["first"], e["last"], e["days"], e["exit"]) for e in eps] == [
        ("ABC", "2024-01-04", "2024-01-08", 3, "2024-01-09"),
        ("ABC", "2024-01-15", "2024-01-15", 1, "2024-01-16"),
        ("XYZ", "2024-01-05", "2024-01-05", 1, "2024-01-08"),
    ]


def test_ban_episodes_ignore_duplicates_and_open_episode_has_no_exit():
    rows = [("ABC", "2024-03-28"), ("ABC", "2024-03-28"), ("ABC", "2024-03-29")]
    eps = ban_episodes(rows, CAL)
    assert len(eps) == 1 and eps[0]["days"] == 2 and eps[0]["exit"] is None  # still banned


def test_reversal_signs_the_window_against_the_pre_move():
    assert reversal(0.05, -0.02) == pytest.approx(0.02)   # ran up, then fell: reversal earned
    assert reversal(-0.04, 0.03) == pytest.approx(0.03)   # sold off, then bounced
    assert reversal(0.05, 0.01) == pytest.approx(-0.01)   # kept going: continuation
    assert reversal(0.0, 0.02) is None and reversal(None, 0.02) is None and reversal(0.01, None) is None


def test_far_from_bans_excludes_placebo_dates_near_any_ban():
    bans = {"ABC": [pd.Timestamp("2024-02-01")]}
    assert far_from_bans("ABC", pd.Timestamp("2024-03-15"), bans, CAL, gap=20) is True
    assert far_from_bans("ABC", pd.Timestamp("2024-02-10"), bans, CAL, gap=20) is False
    assert far_from_bans("XYZ", pd.Timestamp("2024-02-02"), bans, CAL, gap=20) is True


def test_windows_are_prespecified():
    assert WINDOWS == {"entry": ("first", -1, 2), "during": ("first", -1, None),
                       "exit": ("exit", -1, 5), "post": ("exit", 0, 10)}


def test_ban_episodes_skip_dates_beyond_the_calendar():
    """Today's ban list can be newer than the benchmark's last close."""
    eps = ban_episodes([("ABC", "2024-03-29"), ("ABC", "2024-04-01")], CAL)
    assert [(e["first"], e["last"], e["exit"]) for e in eps] == [("2024-03-29", "2024-03-29", None)]
