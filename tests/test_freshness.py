"""The freshness check: every table's newest row must be within its expected cadence, windows
must hold a minimum row volume, the buyback frontier must keep advancing, the DB must fit."""
import re
from datetime import date
from pathlib import Path

from scripts.check_freshness import (FLOORS, RULES, db_size_status, frontier_stuck, stale,
                                     too_thin, window_start)

ROOT = Path(__file__).resolve().parent.parent


def test_stale_flags_old_and_missing_tables_only():
    today = date(2026, 9, 24)
    latest = {"deals": date(2026, 9, 23), "corporate_actions": date(2026, 9, 10),
              "ipo_listings": None}
    rules = {"deals": 6, "corporate_actions": 7, "ipo_listings": 14}
    assert stale(latest, rules, today) == [
        ("corporate_actions", date(2026, 9, 10), 14, 7),
        ("ipo_listings", None, None, 14),
    ]
    assert stale({"deals": date(2026, 9, 18)}, {"deals": 6}, today) == []   # exactly 6 days: ok


def test_rules_cover_the_scheduled_tables():
    assert set(RULES) >= {"deals", "corporate_actions", "ipo_listings", "companies", "fundamentals",
                          "filings", "fo_ban", "rights_issues", "kpis", "scans_buyback_arb",
                          "scans_rights_re", "buyback_frontier", "board_meetings"}
    assert "calendar_ahead" in FLOORS          # trading_calendar must extend past today


def test_too_thin_flags_windows_under_their_floor():
    floors = {"deals": 40, "filings": 300, "companies": 2500}
    counts = {"deals": 39, "filings": 300, "companies": None}
    assert too_thin(counts, floors) == [("deals", 39, 40), ("companies", None, 2500)]


def test_floors_are_positive_and_named_like_rules():
    for name, spec in FLOORS.items():
        assert spec["min"] > 0, name


def test_window_start_counts_back_weekdays():
    # Thu 2026-09-24: 3 trading days = Tue, Wed, Thu -> window starts Tue 22nd
    assert window_start(date(2026, 9, 24), 3) == date(2026, 9, 22)
    # Mon 2026-09-28: Thu, Fri, Mon -> starts Thu 24th (weekend skipped)
    assert window_start(date(2026, 9, 28), 3) == date(2026, 9, 24)


def test_window_start_skips_holidays():
    hol = {date(2026, 9, 23)}
    assert window_start(date(2026, 9, 24), 3, holidays=hol) == date(2026, 9, 21)


def test_frontier_stuck_by_age():
    today = date(2026, 9, 24)
    assert frontier_stuck(date(2026, 7, 1), {}, today, max_days=60)            # 85 days
    assert not frontier_stuck(date(2026, 8, 1), {}, today, max_days=60)


def test_frontier_stuck_when_pages_seen_but_nothing_parses():
    """The WP1 failure: pages exist, every one rejected — a format change, not a quiet market."""
    today = date(2026, 9, 24)
    fresh = date(2026, 9, 20)
    assert frontier_stuck(fresh, {"pages_seen": 12, "tender_parsed": 0}, today, 60)
    assert not frontier_stuck(fresh, {"pages_seen": 4, "tender_parsed": 0}, today, 60)
    assert not frontier_stuck(fresh, {"pages_seen": 30, "tender_parsed": 3}, today, 60)
    assert frontier_stuck(None, {}, today, 60)


def test_db_size_status():
    mb = 1024 * 1024
    assert db_size_status(250 * mb) == "ok"
    assert db_size_status(301 * mb) == "warn"
    assert db_size_status(401 * mb) == "fail"
    assert db_size_status(None) == "fail"


def _schema_tables_with_dates():
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    out = set()
    for m in re.finditer(r"create table if not exists (\w+)\s*\((.*?)\n\);", sql, re.S | re.I):
        if re.search(r"\b(date|timestamptz)\b", m.group(2)):
            out.add(m.group(1))
    return out


def test_every_dated_table_has_a_rule():
    from scripts.check_freshness import QUERIES, TRADING_QUERIES
    covered = ({q[0] for q in QUERIES.values()} | {q[0] for q in TRADING_QUERIES.values()}
               | {f["table"] for f in FLOORS.values()})
    allow = {"tenders", "outcomes", "symbol_changes", "candidates"}  # manual / written with scan_runs
    missing = _schema_tables_with_dates() - covered - allow
    assert not missing, f"tables with no freshness rule: {missing}"


def test_stale_trading_counts_trading_days_not_calendar_days():
    from scripts.check_freshness import TRADING_RULES, stale_trading
    hol = {date(2026, 10, 2)}
    # prices newest Thu 1st; checked Mon 5th -> 1 trading day old (Fri holiday, weekend) -> ok
    assert stale_trading({"prices": date(2026, 10, 1)}, {"prices": 1}, date(2026, 10, 5), hol) == []
    assert stale_trading({"prices": date(2026, 9, 30)}, {"prices": 1}, date(2026, 10, 5), hol) == \
        [("prices", date(2026, 9, 30), 2, 1)]
    assert stale_trading({"prices": None}, {"prices": 1}, date(2026, 10, 5), hol) == [("prices", None, None, 1)]
    assert {"prices", "index_prices"} <= set(TRADING_RULES)


def test_ratio_rules():
    from scripts.check_freshness import RATIOS, ratio_low
    assert ratio_low({"industry_known": (3147, 3156)}, {"industry_known": 0.95}) == []
    assert ratio_low({"industry_known": (2000, 3156)}, {"industry_known": 0.95}) == \
        [("industry_known", 2000 / 3156, 0.95)]
    assert ratio_low({"industry_known": (None, 3156)}, {"industry_known": 0.95})[0][1] is None
    assert "industry_known" in RATIOS
