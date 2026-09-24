"""Test-first spec for the anchor lock-in expiry study (candidate signal #2)."""
import pandas as pd
import pytest

from scanner.lockin import lockin_events, window_return, blocking_action, WINDOWS


def _ipo(**kw):
    base = {"symbol": "ABC", "board": "sme", "listing_date": "2024-01-10", "issue_price": 100.0,
            "anchor_shares": 300, "shares_allotted": 1000,
            "anchor_lockin_30": "2024-02-08", "anchor_lockin_90": "2024-04-08"}
    return {**base, **kw}


def test_lockin_events_one_per_expiry_with_segments():
    ev = lockin_events([_ipo(), _ipo(symbol="OLD", listing_date="2021-06-01",
                                     anchor_lockin_30="2021-07-01", anchor_lockin_90=None,
                                     anchor_shares=None)])
    assert [(e["symbol"], e["kind"], e["expiry"]) for e in ev] == [
        ("ABC", "30d", "2024-02-08"), ("ABC", "90d", "2024-04-08"), ("OLD", "30d", "2021-07-01")]
    abc = ev[0]
    assert abc["board"] == "sme" and abc["issue_price"] == 100.0
    assert abc["anchor_frac"] == 0.3 and abc["era"] == "post_apr2022"
    assert ev[2]["anchor_frac"] is None and ev[2]["era"] == "pre_apr2022"


def test_lockin_events_skip_missing_or_impossible_dates():
    assert lockin_events([_ipo(anchor_lockin_30=None, anchor_lockin_90=None)]) == []
    assert lockin_events([_ipo(anchor_lockin_30="2023-12-01", anchor_lockin_90=None)]) == []  # pre-listing


def _series(vals, start="2024-02-01"):
    return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)), dtype="float64")


def test_window_return_is_benchmark_adjusted_around_first_trading_day():
    stock = _series([100, 100, 100, 100, 100, 90, 90, 90, 90, 90])   # T = 2024-02-08 (5th bday)
    bench = _series([100] * 10)
    # T index = searchsorted('2024-02-08') -> position 5 (2024-02-08 is a Thursday -> bdate #6)
    t = stock.index[stock.index.searchsorted(pd.Timestamp("2024-02-08"))]
    assert t == pd.Timestamp("2024-02-08")
    r = window_return(stock, bench, "2024-02-08", -1, 1)
    p0 = stock.loc[:t].iloc[-2]; p1 = stock.iloc[stock.index.get_loc(t) + 1]
    assert r == pytest.approx(p1 / p0 - 1)
    bench_up = _series([100, 100, 100, 100, 100, 100, 110, 110, 110, 110])
    assert window_return(stock, bench_up, "2024-02-08", -1, 1) == pytest.approx(p1 / p0 - 1 - 0.10)


def test_window_return_none_when_window_out_of_range():
    s = _series([100] * 6)
    assert window_return(s, s, "2024-02-08", -10, -1) is None
    assert window_return(s, s, "2024-02-08", 1, 10) is None
    assert window_return(None, s, "2024-02-08", -1, 1) is None


def test_windows_are_prespecified():
    assert WINDOWS == {"pre": (-10, -1), "event": (-1, 2), "post": (2, 10), "full": (-10, 10)}


def test_blocking_action_flags_splits_bonus_rights_in_window():
    acts = [{"symbol": "ABC", "event_type": "bonus", "event_date": "2024-02-20"},
            {"symbol": "ABC", "event_type": "dividend", "event_date": "2024-02-09"},
            {"symbol": "XYZ", "event_type": "split", "event_date": "2024-02-09"}]
    assert blocking_action(acts, "ABC", "2024-02-01", "2024-02-29") is True
    assert blocking_action(acts, "ABC", "2024-02-01", "2024-02-15") is False  # dividend is fine
    assert blocking_action(acts, "XYZ", "2024-03-01", "2024-03-31") is False


def test_format_unlocks_lists_upcoming_expiries_in_date_order():
    from scanner.lockin import format_unlocks
    rows = [
        {"symbol": "B", "event_type": "anchor_lockin_90", "event_date": "2026-10-05",
         "details": {"board": "mainboard", "anchor_shares": 1200000}},
        {"symbol": "A", "event_type": "anchor_lockin_30", "event_date": "2026-09-30",
         "details": {"board": "sme", "anchor_shares": 50000}},
    ]
    out = format_unlocks(rows)
    lines = out.splitlines()
    assert "A" in lines[1] and "30d" in lines[1] and "sme" in lines[1]
    assert "B" in lines[2] and "90d" in lines[2] and "12,00,000" in lines[2]
    assert format_unlocks([]).startswith("No anchor lock-in expiries")
