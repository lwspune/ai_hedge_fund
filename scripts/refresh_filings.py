"""Refresh the NSE filings index (F1). Idempotent upserts on seq_id.

    python scripts/refresh_filings.py                         # last 5 days (daily cloud job)
    python scripts/refresh_filings.py --from 2024-01-01       # backfill, 14-day windows
    python scripts/refresh_filings.py --from 2021-01-01 --to 2023-12-31 --orders-only
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.filings import fetch_range, keep, parse_announcements  # noqa: E402

ORDER_CATEGORIES = {"Bagging/Receiving of orders/contracts", "Awarding of order(s)/contract(s)"}
CHUNK = 500


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", type=date.fromisoformat)
    ap.add_argument("--to", type=date.fromisoformat, default=date.today())
    ap.add_argument("--orders-only", action="store_true")
    a = ap.parse_args()
    frm = a.frm or a.to - timedelta(days=5)
    total = 0
    for f, t, raw in fetch_range(frm, a.to):
        rows = [r for r in parse_announcements(raw) if keep(r)]
        if a.orders_only:
            rows = [r for r in rows if r["category"] in ORDER_CATEGORIES]
        rows = list({r["seq_id"]: r for r in rows}.values())  # one upsert batch = unique keys
        for i in range(0, len(rows), CHUNK):
            _, bad = db.upsert_resilient("filings", rows[i:i + CHUNK], "seq_id")
            for r, err in bad:
                print(f"  rejected {r['seq_id']} {r['symbol']}: {err[-120:]}")
        total += len(rows)
        print(f"  {f}..{t}: {len(raw)} announcements, {len(rows)} kept", flush=True)
        time.sleep(0.5)
    print(f"upserted {total} filings")


if __name__ == "__main__":
    main()
