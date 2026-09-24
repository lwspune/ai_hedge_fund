"""Refill market_deals for a date range from nselib (NSE's historical bulk/block data).
Each date is reloaded atomically (reload_market_deals RPC), so re-runs are idempotent.
Fills gaps the daily edge function missed (it can only fetch *today's* CSV).

    python scripts/refill_deals.py --from 2026-01-01 [--to 2026-09-24]
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.deals import market_deal_rows  # noqa: E402


def month_chunks(frm: date, to: date):
    cur = frm
    while cur <= to:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1)
        yield cur, min(nxt - timedelta(days=1), to)
        cur = nxt


def fetch(frm: date, to: date) -> list[dict]:
    from nselib import capital_market as cm
    rows = []
    for fn, kind in ((cm.bulk_deal_data, "bulk"), (cm.block_deals_data, "block")):
        for attempt in range(3):
            try:
                df = fn(from_date=frm.strftime("%d-%m-%Y"), to_date=to.strftime("%d-%m-%Y"))
                if df is not None and len(df):
                    rows += market_deal_rows(df.to_dict("records"), kind)
                break
            except Exception as e:  # nselib raises bare Exceptions on empty/throttled ranges
                print(f"  retry {kind} {frm}: {e!r}"[:120])
                time.sleep(3 + 3 * attempt)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", type=date.fromisoformat, required=True)
    ap.add_argument("--to", type=date.fromisoformat, default=date.today())
    a = ap.parse_args()
    total = 0
    for f, t in month_chunks(a.frm, a.to):
        by_date = defaultdict(list)
        for r in fetch(f, t):
            by_date[r["deal_date"]].append(r)
        for d in sorted(by_date):
            total += db.rpc("reload_market_deals", {"p_date": d, "p_rows": by_date[d]})
        print(f"  {f:%Y-%m}: {len(by_date)} dates, {sum(map(len, by_date.values()))} deals", flush=True)
        time.sleep(1)
    print(f"reloaded {total} deals")


if __name__ == "__main__":
    main()
