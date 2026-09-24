"""Data-freshness check — the last step of the scheduled refresh workflows.

A loader can "succeed" while writing nothing (a source changes its format), so GitHub's
failure email alone misses silent staleness. Four kinds of rule, any failure exits non-zero ->
the run fails -> GitHub emails:

  age       newest row of each table within its cadence (QUERIES)
  floor     a recent window holds a minimum row volume (FLOORS) — catches a loader that
            writes one row and drops the rest
  frontier  the buyback id frontier keeps advancing, and a scan that sees pages but parses
            none fails (the 2026 chittorgarh format change went unnoticed for nine months)
  db size   Postgres stays inside the 500 MB free tier (warn > 300 MB, fail > 400 MB)

    python scripts/check_freshness.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MB = 1024 * 1024
DB_WARN_BYTES, DB_FAIL_BYTES = 300 * MB, 400 * MB
FRONTIER_MAX_DAYS = 60
FRONTIER_MIN_PAGES = 10   # a scan that saw this many pages and parsed none = format change


def queries(today: date) -> dict:
    """name -> (table, date column, extra PostgREST filters, max age in calendar days)."""
    return {
        "deals": ("market_deals", "deal_date", {}, 6),                    # daily, weekends + a holiday
        "corporate_actions": ("corporate_events", "event_date",
                              {"source": "eq.nse_ca", "event_date": f"lte.{today}"}, 7),
        "fo_ban": ("corporate_events", "created_at", {"source": "eq.nse_fo"}, 6),  # can be empty: age only
        "ipo_listings": ("ipos", "listing_date", {"listing_date": f"lte.{today}"}, 14),
        "rights_issues": ("rights_issues", "updated_at", {}, 10),
        "companies": ("companies", "updated_at", {}, 8),                  # weekly refresh
        "fundamentals": ("company_snapshot", "fetched_at", {}, 8),        # weekly refresh
        "filings": ("filings", "disclosed_at", {}, 5),                    # ~500 filings / trading day
        "kpis": ("company_kpis", "created_at", {}, 5),
        "scans_buyback_arb": ("scan_runs", "run_at", {"signal_name": "eq.buyback_arb"}, 3),
        "scans_rights_re": ("scan_runs", "run_at", {"signal_name": "eq.rights_re"}, 3),
        "board_meetings": ("corporate_events", "created_at", {"source": "eq.nse_bm"}, 10),
        "snapshot_history": ("company_snapshot_history", "as_of", {}, 8),   # weekly, with fundamentals
        # 2026-09-24 review unlocks (docs/GITHUB_PROJECT_REVIEW.md)
        "shareholding": ("shareholding", "updated_at", {}, 8),             # weekly: every symbol's latest quarter re-touched
        "insider_trades": ("insider_trades", "broadcast_at", {}, 5),       # ~35 PIT filings / trading day
        "pref_issues": ("pref_issues", "updated_at", {}, 5),               # daily 45-day window re-upserted
        "pref_lockin": ("corporate_events", "created_at", {"source": "eq.nse_pref"}, 21),  # ~2 listings / day
        # ~2 tenders/month settle; a result lands ~3 weeks after each close
        "buyback_results": ("buyback_results", "updated_at", {}, 120),
        "ofs_events": ("ofs_events", "updated_at", {}, 7),   # daily probe re-touches the newest ids
        # evaluated by frontier_stuck(), not stale(): a new buyback row = the frontier advanced
        "buyback_frontier": ("buybacks", "created_at", {}, FRONTIER_MAX_DAYS),
    }


QUERIES = queries(date.today())
RULES = {name: q[3] for name, q in QUERIES.items()}

# name -> (table, date column, filters, max age in TRADING days). The bhavcopy lands ~19:00 IST,
# before the 20:30 daily run, so a healthy store is 0 trading days old.
TRADING_QUERIES = {
    "prices": ("daily_prices", "trade_date", {}, 1),
    "index_prices": ("index_prices", "trade_date", {}, 1),
    "surveillance": ("surveillance_daily", "as_of", {}, 1),   # a snapshot every trading day
}
TRADING_RULES = {name: q[3] for name, q in TRADING_QUERIES.items()}

# name -> window volume floor. `days` = trading days back from today (None = whole table).
# Floors sit well under the live 2nd-percentile volume (measured 2026-09-24) so they only
# fire on a real loader failure, not a quiet week.
FLOORS = {
    "deals": {"table": "market_deals", "col": "deal_date", "filters": {}, "days": 3, "min": 40},
    "corporate_actions": {"table": "corporate_events", "col": "event_date",
                          "filters": {"source": "eq.nse_ca"}, "days": 21, "min": 20},
    "companies_listed": {"table": "companies", "col": None,
                         "filters": {"status": "eq.listed"}, "days": None, "min": 2500},
    "fundamentals": {"table": "company_snapshot", "col": "fetched_at", "filters": {},
                     "days": 6, "min": 2000},
    "filings": {"table": "filings", "col": "disclosed_at", "filters": {}, "days": 3, "min": 300},
    # the weekly holidays load writes this + next year; < 20 weekdays ahead = it stopped running
    "calendar_ahead": {"table": "trading_calendar", "col": None,
                       "filters": {"trade_date": f"gte.{date.today()}"}, "days": None, "min": 20},
    # ~3,400 equity rows per bhavcopy day; two days so a not-yet-published today can't fail it
    "prices": {"table": "daily_prices", "col": "trade_date", "filters": {}, "days": 2, "min": 2500},
    # the weekly membership diff keeps exactly 50 open NIFTY 50 intervals
    "nifty50_members": {"table": "index_membership", "col": None,
                        "filters": {"index_key": "eq.nifty50", "to_date": "is.null"}, "days": None, "min": 50},
    # the weekly shareholding run re-touches every listed symbol's latest quarter
    "shareholding": {"table": "shareholding", "col": "updated_at", "filters": {}, "days": 6, "min": 2000},
    "insider_trades": {"table": "insider_trades", "col": "broadcast_at", "filters": {}, "days": 3, "min": 30},
    # ~135 long-term + ~75 short-term ASM + ~75 GSM rows per snapshot
    "surveillance": {"table": "surveillance_daily", "col": "as_of", "filters": {}, "days": 2, "min": 100},
    # the daily 45-day window re-touches ~140 rows; NSE filters that window on the filing's latest
    # status date, so submission_date undercounts recent weeks and is not a usable floor column
    "pref_issues": {"table": "pref_issues", "col": "updated_at", "filters": {}, "days": 2, "min": 40},
}


# name -> (table, numerator filters, denominator filters, minimum share)
RATIOS = {
    "industry_known": ("companies", {"status": "eq.listed", "industry": "not.is.null"},
                       {"status": "eq.listed"}, 0.95),
}


# --- pure rules ---------------------------------------------------------------

def ratio_low(counts: dict, mins: dict) -> list[tuple]:
    """[(name, share, min)] for ratios under their minimum; counts: {name: (num, den)}."""
    out = []
    for name, lo in mins.items():
        num, den = counts.get(name, (None, None))
        share = None if num is None or not den else num / den
        if share is None or share < lo:
            out.append((name, share, lo))
    return out


def stale(latest: dict, rules: dict, today: date) -> list[tuple]:
    """[(name, newest_date, age_days, max_age)] for every table older than its rule (or empty)."""
    out = []
    for name, max_age in rules.items():
        d = latest.get(name)
        if d is None:
            out.append((name, None, None, max_age))
        elif (today - d).days > max_age:
            out.append((name, d, (today - d).days, max_age))
    return out


def stale_trading(latest: dict, rules: dict, today: date, hol) -> list[tuple]:
    """Like stale(), with ages in trading days (weekends + NSE holidays don't count)."""
    from scanner.trading_calendar import age_in_trading_days
    out = []
    for name, max_age in rules.items():
        age = age_in_trading_days(latest.get(name), today, hol)
        if age is None or age > max_age:
            out.append((name, latest.get(name), age, max_age))
    return out


def too_thin(counts: dict, floors: dict) -> list[tuple]:
    """[(name, n, floor)] for every window whose row count is under its floor (None = failed)."""
    return [(name, counts.get(name), floor) for name, floor in floors.items()
            if counts.get(name) is None or counts[name] < floor]


def window_start(today: date, n_trading: int, holidays=frozenset()) -> date:
    """First day of the window holding the last `n_trading` trading days up to today
    (weekends and `holidays` skipped)."""
    from scanner.trading_calendar import window_start as ws
    return ws(today, n_trading, holidays)


def frontier_stuck(last_advance: date | None, scan_params: dict, today: date,
                   max_days: int = FRONTIER_MAX_DAYS) -> str | None:
    """Why the buyback frontier looks stuck, or None if it's healthy."""
    if last_advance is None:
        return "no buyback rows"
    if (today - last_advance).days > max_days:
        return f"no new buyback for {(today - last_advance).days}d > {max_days}d"
    seen, parsed = scan_params.get("pages_seen") or 0, scan_params.get("tender_parsed")
    if seen >= FRONTIER_MIN_PAGES and parsed == 0:
        return f"last scan saw {seen} pages and parsed 0 tenders (page format changed?)"
    return None


def db_size_status(n_bytes: int | None) -> str:
    if n_bytes is None or n_bytes > DB_FAIL_BYTES:
        return "fail"
    return "warn" if n_bytes > DB_WARN_BYTES else "ok"


# --- thin I/O -------------------------------------------------------------------

def _as_date(v):
    if v is None:
        return None
    return datetime.fromisoformat(v.replace("Z", "+00:00")).date() if "T" in v else date.fromisoformat(v)


def _newest(table: str, col: str, filters: dict):
    from scanner import db
    rows = db.select(table, {"select": col, **filters, "order": f"{col}.desc.nullslast", "limit": "1"})
    return _as_date(rows[0][col]) if rows else None


def _window_count(spec: dict, today: date):
    from scanner import db
    from scanner.trading_calendar import holidays
    params = dict(spec["filters"])
    if spec["days"]:
        params[spec["col"]] = f"gte.{window_start(today, spec['days'], holidays())}"
    try:
        return db.count(spec["table"], params)
    except Exception as e:
        print(f"  count failed for {spec['table']}: {e}")
        return None


def _last_scan_params() -> dict:
    from scanner import db
    rows = db.select("scan_runs", {"select": "params", "signal_name": "eq.buyback_arb",
                                   "order": "run_at.desc", "limit": "1"})
    return (rows[0].get("params") or {}) if rows else {}


def main():
    from scanner import db
    today = date.today()
    from scanner.trading_calendar import holidays
    latest = {name: _newest(t, c, f) for name, (t, c, f, _) in QUERIES.items()}
    latest_td = {name: _newest(t, c, f) for name, (t, c, f, _) in TRADING_QUERIES.items()}
    age_rules = {k: v for k, v in RULES.items() if k != "buyback_frontier"}
    counts = {name: _window_count(spec, today) for name, spec in FLOORS.items()}
    ratios = {name: (db.count(t, num), db.count(t, den)) for name, (t, num, den, _) in RATIOS.items()}
    try:
        size = db.rpc("db_size_bytes", {})
    except Exception as e:
        print(f"  db_size_bytes failed: {e}")
        size = None
    frontier = frontier_stuck(latest["buyback_frontier"], _last_scan_params(), today)

    print(f"  {'rule':<20}{'newest':<12}{'max age':>8}")
    for name, d in latest.items():
        print(f"  {name:<20}{str(d):<12}{RULES[name]:>7}d")
    for name, d in latest_td.items():
        print(f"  {name:<20}{str(d):<12}{TRADING_RULES[name]:>7}td")
    print(f"  {'floor':<20}{'rows':>8}{'min':>8}")
    for name, spec in FLOORS.items():
        print(f"  {name:<20}{str(counts[name]):>8}{spec['min']:>8}")
    for name, (num, den) in ratios.items():
        print(f"  {name:<20}{num}/{den} (min {RATIOS[name][3]:.0%})")
    size_state = db_size_status(size)
    print(f"  db_size             {(size or 0) / MB:>7.0f} MB  ({size_state})")

    failures = [f"STALE: {n} newest={d} age={a}d > {m}d" for n, d, a, m in stale(latest, age_rules, today)]
    failures += [f"STALE: {n} newest={d} age={a} trading days > {m}" for n, d, a, m in
                 stale_trading(latest_td, TRADING_RULES, today, holidays())]
    failures += [f"THIN: {n} rows={c} < {f}" for n, c, f in
                 too_thin(counts, {n: s["min"] for n, s in FLOORS.items()})]
    failures += [f"RATIO: {n} = {r} < {m}" for n, r, m in
                 ratio_low(ratios, {n: v[3] for n, v in RATIOS.items()})]
    if frontier:
        failures.append(f"FRONTIER: {frontier}")
    if size_state == "fail":
        failures.append(f"DB SIZE: {size} bytes > {DB_FAIL_BYTES} (or unreadable)")
    elif size_state == "warn":
        print(f"WARN: database {size / MB:.0f} MB > {DB_WARN_BYTES / MB:.0f} MB")
    if failures:
        print("\n".join(failures))
        sys.exit(1)
    print("all freshness rules pass")


if __name__ == "__main__":
    main()
