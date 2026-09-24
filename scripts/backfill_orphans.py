"""One-off: give every orphan symbol a `companies` row (DATA_INFRA_SPEC WP4).

An orphan is a symbol that appears in filings / market_deals / corporate_events but not in
`companies` — companies delisted after NSE's delisted.csv went stale (~2020) and before the
weekly delisting-by-diff existed (RELCAPITAL, IDFC, ...). Each gets a delisted row
(delist_source 'manual'): name from its filings, delisted_on = its last close in the cloud
price store, else the last date it was seen. Run from Actions: backfill.yml, what=orphans.

    python scripts/backfill_orphans.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def orphan_rows(orphans: list[dict], last_trade: dict) -> list[dict]:
    """`companies` rows for orphans. last_trade: {symbol: date of its last close}."""
    return [{"symbol": o["symbol"], "name": o.get("company"), "series": None, "listing_date": None,
             "face_value": None, "isin": None, "industry": None, "industry_source": None,
             "indices": [], "is_financial": None, "status": "delisted",
             "delisted_on": (last_trade.get(o["symbol"]) or date.fromisoformat(o["last_seen"])).isoformat(),
             "delist_source": "manual", "last_seen_listed": None}
            for o in orphans]


def main():
    from scanner import db
    from scanner.pricestore import get_closes
    orphans = db.rpc_all("orphan_symbols", {})
    print(f"{len(orphans)} orphan symbols")
    last_trade = {}
    for o in orphans:
        seen = date.fromisoformat(o["last_seen"])
        try:
            s = get_closes(o["symbol"], max(seen - timedelta(days=400), date(2020, 1, 1)),
                           seen + timedelta(days=400), source="db")
        except Exception as e:  # a symbol the store can't price just falls back to last_seen
            print(f"  {o['symbol']}: price lookup failed ({e})")
            s = None
        if s is not None:
            last_trade[o["symbol"]] = s.index.max().date()
    rows = orphan_rows(orphans, last_trade)
    for i in range(0, len(rows), 500):
        db.insert("companies", rows[i:i + 500], on_conflict="symbol", return_rows=False,
                  ignore_duplicates=True)   # never overwrite a row the master loader created meanwhile
    for r in rows:
        print(f"  {r['symbol']:<14} delisted_on {r['delisted_on']}  {r['name'] or ''}")
    print(f"inserted {len(rows)} delisted orphan rows ({len(last_trade)} dated by last close)")


if __name__ == "__main__":
    main()
