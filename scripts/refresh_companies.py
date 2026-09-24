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
from scanner.master import fetch_all  # noqa: E402

CHUNK = 500
COLS = ("symbol,name,series,listing_date,face_value,isin,industry,industry_source,indices,"
        "is_financial,status,delisted_on,delist_source,last_seen_listed")


def main():
    today = date.today()
    previous = db.select_all("companies", {"select": COLS, "status": "eq.listed"})
    sectors = {r["symbol"]: r["sector"] for r in db.select_all("company_snapshot", {"select": "symbol,sector"})
               if r.get("sector")}
    companies, changes = fetch_all(sectors, previous, today)
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
    listed = [c for c in companies if c["status"] == "listed"]
    filled = sum(c["industry"] is not None for c in listed)
    print(f"upserted {len(companies)} companies ({len(listed)} listed, {len(gone)} newly delisted: "
          f"{[c['symbol'] for c in gone][:20]}), industry known for {filled}/{len(listed)}, "
          f"{len(changes)} symbol changes")


if __name__ == "__main__":
    main()
