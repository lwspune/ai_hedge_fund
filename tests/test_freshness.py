"""The freshness check: every table's newest row must be within its expected cadence, windows
must hold a minimum row volume, the buyback frontier must keep advancing, the DB must fit."""
import re
from datetime import date, timedelta
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
                          "scans_rights_re", "buyback_frontier", "board_meetings",
                          "shareholding", "insider_trades", "pref_issues", "pref_lockin"}
    assert "calendar_ahead" in FLOORS          # trading_calendar must extend past today


def test_risk_metrics_rules():
    from scripts.check_freshness import TRADING_RULES
    assert TRADING_RULES["risk_metrics"] == 1                     # rewritten every trading day
    f = FLOORS["risk_metrics"]
    assert f["table"] == "risk_metrics" and f["days"] is None and f["min"] == 1500


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
    allow = {"tenders", "outcomes", "symbol_changes", "candidates",   # manual / written with scan_runs
             "validation_runs",                                         # on-demand (validate.yml)
             "alerts_sent"}                                             # empty for weeks when nothing is new
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
    assert {"prices", "index_prices", "surveillance"} <= set(TRADING_RULES)


def test_ratio_rules():
    from scripts.check_freshness import RATIOS, ratio_low
    assert ratio_low({"industry_known": (3147, 3156)}, {"industry_known": 0.95}) == []
    assert ratio_low({"industry_known": (2000, 3156)}, {"industry_known": 0.95}) == \
        [("industry_known", 2000 / 3156, 0.95)]
    assert ratio_low({"industry_known": (None, 3156)}, {"industry_known": 0.95})[0][1] is None
    assert "industry_known" in RATIOS


def test_holes_lists_missing_trading_days_inside_the_window():
    """The 2026-09-01..09 price hole passed every age / floor rule: the newest row was fresh."""
    from scripts.check_freshness import holes
    hol = frozenset({date(2026, 9, 14)})                       # Ganesh Chaturthi
    today = date(2026, 9, 30)
    all_days = {date(2026, 8, 1) + timedelta(days=k) for k in range(61)}
    present = {d for d in all_days if d.weekday() < 5 and d not in hol}
    assert holes(present, today, 20, hol) == []
    gap = {date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8, 9)}
    assert holes(present - gap, today, 25, hol) == sorted(gap)
    assert holes(present - gap, today, 10, hol) == []          # outside the window
    # today not published yet is the age rule's business, not a hole
    assert holes(present - {today}, today, 20, hol) == []


def test_hole_rules_cover_prices_and_benchmarks():
    from scripts.check_freshness import HOLE_TABLES, HOLE_WINDOW
    assert HOLE_WINDOW == 60
    assert set(HOLE_TABLES) == {"prices", "index_^CRSLDX", "index_^NSEI", "sector_indices"}


def test_market_regime_rules():
    from scripts.check_freshness import TRADING_RULES
    assert TRADING_RULES["market_regime"] == 1
    f = FLOORS["market_regime"]
    assert f["table"] == "market_regime" and f["days"] is None and f["min"] == 1400



def test_sector_holes_start_at_each_index_s_first_row():
    """An index launched inside the window is checked from its first row; one that stops is a hole."""
    from scripts.check_freshness import HOLE_TABLES, sector_holes
    assert HOLE_TABLES["sector_indices"] == ("sectors", None)
    hol = frozenset()
    today = date(2026, 9, 30)
    days = [date(2026, 9, d) for d in (21, 22, 23, 24, 25, 28, 29)]           # the last 7 sessions before today
    rows = {"Nifty Bank": set(days) | {date(2026, 9, 1)},                     # full + an older row
            "Nifty Power": set(days[3:]),                                     # launched 24 Sep: fine
            "Nifty Media": {date(2026, 9, 1)} | set(days[:4])}                # stopped after the 24th: a hole
    got = sector_holes(rows, today, 7, hol)
    assert got == {"Nifty Media": [date(2026, 9, 25), date(2026, 9, 28), date(2026, 9, 29)]}
    assert sector_holes({}, today, 7, hol) == {}



def test_sector_regime_rules():
    from scripts.check_freshness import TRADING_RULES
    assert TRADING_RULES["sector_regime"] == 1
    f = FLOORS["sector_regime"]
    assert f["table"] == "sector_regime" and f["days"] is None and f["min"] == 15
