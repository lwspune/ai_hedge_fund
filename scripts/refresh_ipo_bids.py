"""Fill ipos.sub_retail_nse — NSE's retail times-subscribed (scanner/ipobids.py) — for NSE mainboard
IPOs that don't have it yet. The free retail figure for issues whose consolidated one chittorgarh
keeps behind its paywall; the IPO study scales it (NSE carries ~65% of retail bids).

    python scripts/refresh_ipo_bids.py [--since 2020-01-01]   # backfill.yml what=ipo-bids
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.ipobids import fetch_retail_times, session  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, default=date(2020, 1, 1))
    a = ap.parse_args()
    todo = db.select_all("ipos", {"select": "chittorgarh_id,symbol", "board": "eq.mainboard",
                                  "listing_at": "ilike.*NSE*", "sub_retail_nse": "is.null",
                                  "listing_date": f"gte.{a.since}", "order": "listing_date"})
    todo = [r for r in todo if r["symbol"]]
    print(f"{len(todo)} mainboard IPOs to read", flush=True)
    s, stats = session(), {"filled": 0, "none": 0, "error": 0}
    for k, r in enumerate(todo, 1):
        try:
            t = fetch_retail_times(r["symbol"], s)
        except (requests.RequestException, ValueError) as e:   # ValueError: a non-JSON reply
            stats["error"] += 1
            print(f"  {r['symbol']}: {e!r}"[:120])
            continue
        if t:
            db.update("ipos", {"chittorgarh_id": f"eq.{r['chittorgarh_id']}"}, {"sub_retail_nse": t})
        stats["filled" if t else "none"] += 1
        if k % 100 == 0:
            print(f"  {k}/{len(todo)} {stats}", flush=True)
        time.sleep(0.7)
    print(f"done: {stats}")


if __name__ == "__main__":
    main()
