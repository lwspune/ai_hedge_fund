"""Refresh the company master (infra I1): NSE/niftyindices static CSVs -> companies +
symbol_changes. Idempotent upserts; safe to re-run weekly.

    python scripts/refresh_companies.py

Reads last run's listed set (delisting by diff: absent today -> delisted, never deleted) and
screener sectors (industry fallback) from Supabase first. Fails rather than writes when a
download is truncated or the diff would delist > 50 symbols at once.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.master import curated_intervals, fetch_all, membership_diff  # noqa: E402
from scanner.rebalance import load_next50_events  # noqa: E402

CHUNK = 500
COLS = ("symbol,name,series,listing_date,face_value,isin,industry,industry_source,indices,"
        "is_financial,status,delisted_on,delist_source,last_seen_listed")


def refresh_membership(members: dict, today: date) -> None:
    """index_membership (WP5): close intervals for symbols that left an index, open new ones;
    re-upsert the curated Next-50 history (idempotent) so point-in-time membership predates
    the first weekly diff."""
    current = db.select_all("index_membership", {"select": "symbol,index_key,from_date",
                                                 "source": "eq.niftyindices_list", "to_date": "is.null"})
    close, open_ = membership_diff(current, members, today)
    rows = [{**r, "source": "niftyindices_list"} for r in close] + open_
    events = [{"symbol": e.symbol, "leg": e.leg, "effective": str(e.effective)}
              for e in load_next50_events(clean_only=False)]
    start = min(str(e.announce) for e in load_next50_events(clean_only=False))
    rows += curated_intervals(events, "niftynext50", start)
    for i in range(0, len(rows), CHUNK):
        db.insert("index_membership", rows[i:i + CHUNK], on_conflict="symbol,index_key,from_date",
                  return_rows=False)
    print(f"index_membership: {len(open_)} opened, {len(close)} closed, "
          f"{len(rows) - len(open_) - len(close)} curated Next-50 intervals")


def main():
    today = date.today()
    previous = db.select_all("companies", {"select": COLS, "status": "eq.listed"})
    sectors = {r["symbol"]: r["sector"] for r in db.select_all("company_snapshot", {"select": "symbol,sector"})
               if r.get("sector")}
    companies, changes, members = fetch_all(sectors, previous, today)
    now = datetime.now(timezone.utc).isoformat()
    # delisted-by-diff rows come first in `companies`: they release ISINs that renamed
    # symbols' new rows claim, so they go in their own earlier batch
    gone = [c for c in companies if c.get("delist_source") == "equity_l_diff" and c["delisted_on"] == today.isoformat()]
    rest = [c for c in companies if c not in gone]
    for batch in (gone, rest):
        for i in range(0, len(batch), CHUNK):
            db.insert("companies", [{**c, "updated_at": now} for c in batch[i:i + CHUNK]],
                      on_conflict="symbol", return_rows=False)
    for i in range(0, len(changes), CHUNK):
        db.insert("symbol_changes", changes[i:i + CHUNK],
                  on_conflict="old_symbol,new_symbol,changed_on", return_rows=False)
    refresh_membership(members, today)
    listed = [c for c in companies if c["status"] == "listed"]
    filled = sum(c["industry"] is not None for c in listed)
    print(f"upserted {len(companies)} companies ({len(listed)} listed, {len(gone)} newly delisted: "
          f"{[c['symbol'] for c in gone][:20]}), industry known for {filled}/{len(listed)}, "
          f"{len(changes)} symbol changes")


if __name__ == "__main__":
    main()
