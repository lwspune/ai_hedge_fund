"""Data-freshness check — the last step of the scheduled refresh workflows.

A loader can "succeed" while writing nothing (a source changes its format), so GitHub's
failure email alone misses silent staleness. This checks each table's newest row against its
expected cadence and exits non-zero if any is stale -> the run fails -> GitHub emails.

    python scripts/check_freshness.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# name -> (table, date column, extra PostgREST filters, max age in calendar days)
QUERIES = {
    "deals": ("market_deals", "deal_date", {}, 6),                       # daily, weekends + a holiday
    "corporate_actions": ("corporate_events", "event_date",
                          {"source": "eq.nse_ca", "event_date": f"lte.{date.today()}"}, 7),
    "ipo_listings": ("ipos", "listing_date", {"listing_date": f"lte.{date.today()}"}, 14),
    "companies": ("companies", "updated_at", {}, 8),                     # weekly refresh
    "fundamentals": ("company_snapshot", "fetched_at", {}, 8),           # weekly refresh
    "filings": ("filings", "disclosed_at", {}, 5),                       # ~500 filings / trading day
}
RULES = {name: q[3] for name, q in QUERIES.items()}


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


def _newest(table: str, col: str, filters: dict):
    from scanner import db
    rows = db.select(table, {"select": col, **filters, "order": f"{col}.desc.nullslast", "limit": "1"})
    if not rows or rows[0][col] is None:
        return None
    v = rows[0][col]
    return datetime.fromisoformat(v.replace("Z", "+00:00")).date() if "T" in v else date.fromisoformat(v)


def main():
    today = date.today()
    latest = {name: _newest(t, c, f) for name, (t, c, f, _) in QUERIES.items()}
    for name, d in latest.items():
        print(f"  {name:<18} newest {d}  (max age {RULES[name]}d)")
    bad = stale(latest, RULES, today)
    if bad:
        for name, d, age, max_age in bad:
            print(f"STALE: {name} newest={d} age={age}d > {max_age}d")
        sys.exit(1)
    print("all tables fresh")


if __name__ == "__main__":
    main()
