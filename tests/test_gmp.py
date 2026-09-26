"""Test-first spec for the investorgain grey-market-premium parser (scanner/gmp.py). Fixtures are
saved pages: Karamtara Engineering (2026, 14 daily GMPs) and Aether Industries (2022, 3)."""
from datetime import date
from pathlib import Path

from scanner.gmp import decision_gmp, gmp_rows, parse_gmp_page

FX = Path(__file__).parent / "fixtures" / "gmp"


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


def test_parse_recent_page_daily_series():
    ig_id, rows = parse_gmp_page(_load("1622.html"))
    assert ig_id == 1622
    assert len(rows) == 14
    assert rows[0] == {"gmp_date": date(2026, 9, 4), "gmp": 40.0}      # oldest first
    assert rows[-1] == {"gmp_date": date(2026, 9, 17), "gmp": 46.0}


def test_parse_older_page():
    ig_id, rows = parse_gmp_page(_load("291.html"))
    assert ig_id == 291
    assert [(r["gmp_date"], r["gmp"]) for r in rows] == [
        (date(2022, 6, 1), 15.0), (date(2022, 6, 2), 35.0), (date(2022, 6, 3), 55.0)]


def test_parse_rejects_non_gmp_pages():
    assert parse_gmp_page("<html>moved</html>") == (None, [])


def test_parse_skips_blank_and_dash_values():
    html = ('"gmpData":[{"Seq":2,"id":9,"ipo_id":7,"gmp_date":"02-01-2024","gmp":"-"},'
            '{"Seq":1,"id":8,"ipo_id":7,"gmp_date":"01-01-2024","gmp":"12.5"}]')
    assert parse_gmp_page(html) == (7, [{"gmp_date": date(2024, 1, 1), "gmp": 12.5}])


def test_rows_drop_placeholders_dated_after_listing():
    parsed = [{"gmp_date": date(2020, 7, 20), "gmp": 150.0}, {"gmp_date": date(2025, 10, 27), "gmp": 0.0}]
    assert gmp_rows(1049, 14, date(2020, 7, 23), parsed) == [
        {"chittorgarh_id": 1049, "investorgain_id": 14, "gmp_date": "2020-07-20", "gmp": 150.0}]


def test_rows_drop_quotes_long_before_listing():
    # pre-2017 ids all redirect to one unrelated investorgain page: its dates never fit the window
    parsed = [{"gmp_date": date(2018, 1, 5), "gmp": 20.0}, {"gmp_date": date(2017, 1, 30), "gmp": 8.0}]
    assert gmp_rows(611, 331, date(2017, 2, 3), parsed) == [
        {"chittorgarh_id": 611, "investorgain_id": 331, "gmp_date": "2017-01-30", "gmp": 8.0}]
    assert gmp_rows(611, 331, date(2016, 9, 1), parsed) == []


def test_decision_gmp_is_the_last_quote_by_issue_close():
    series = [{"gmp_date": date(2026, 9, d), "gmp": g} for d, g in ((4, 40.0), (10, 72.0), (11, 60.0), (17, 46.0))]
    assert decision_gmp(series, date(2026, 9, 11)) == 60.0     # close day counts
    assert decision_gmp(series, date(2026, 9, 3)) is None       # nothing seen before the decision
    assert decision_gmp([], date(2026, 9, 11)) is None


def test_targets_daily_window_and_backfill():
    from scanner.gmp import gmp_targets
    ipos = [{"chittorgarh_id": 1, "listing_date": "2026-09-10"}, {"chittorgarh_id": 2, "listing_date": "2026-09-20"},
            {"chittorgarh_id": 3, "listing_date": "2026-10-02"}, {"chittorgarh_id": 4, "listing_date": "2021-03-01"}]
    assert gmp_targets(ipos, date(2026, 9, 26), days=10) == [2, 3]            # recent + not yet listed
    assert gmp_targets(ipos, date(2026, 9, 26), since=date(2021, 1, 1)) == [1, 2, 3, 4]
