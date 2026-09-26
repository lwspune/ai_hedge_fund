"""Refresh the IPO grey-market premium series (scanner/gmp.py) into `ipo_gmp`.

    python scripts/refresh_gmp.py                      # daily: issues listed in the last 10 days or upcoming
    python scripts/refresh_gmp.py --since 2017-01-01   # backfill (backfill.yml what=ipo-gmp)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.gmp import fetch_gmp, gmp_rows, gmp_targets  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, help="backfill every IPO listed on/after this date")
    ap.add_argument("--days", type=int, default=10)
    a = ap.parse_args()
    ipos = db.select_all("ipos", {"select": "chittorgarh_id,listing_date"})
    listing = {r["chittorgarh_id"]: date.fromisoformat(r["listing_date"]) for r in ipos}
    ids = gmp_targets(ipos, date.today(), a.days, a.since)
    print(f"{len(ids)} IPOs to read", flush=True)
    s, stats, now = requests.Session(), {"quoted": 0, "none": 0, "error": 0, "rows": 0}, datetime.now(timezone.utc)
    for k, cid in enumerate(ids, 1):
        try:
            ig_id, series = fetch_gmp(cid, s)
        except requests.RequestException as e:
            stats["error"] += 1
            print(f"  {cid}: {e!r}"[:120])
            continue
        rows = gmp_rows(cid, ig_id, listing[cid], series) if ig_id else []
        if rows:
            _, bad = db.upsert_resilient("ipo_gmp", [{**r, "updated_at": now.isoformat()} for r in rows],
                                         "chittorgarh_id,gmp_date")
            for row, err in bad:
                print(f"  rejected gmp {cid} {row['gmp_date']}: {err[-120:]}")
            stats["rows"] += len(rows) - len(bad)
        stats["quoted" if rows else "none"] += 1
        if k % 100 == 0:
            print(f"  {k}/{len(ids)} {stats}", flush=True)
        time.sleep(0.4)
    print(f"done: {stats}")


if __name__ == "__main__":
    main()
