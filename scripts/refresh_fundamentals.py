"""Refresh fundamentals (infra I4): screener.in company pages -> full statement history in
cache/fundamentals/<SYM>.parquet (+ Storage bucket `fundamentals`) + one `company_snapshot` row per company in Supabase.

    python scripts/refresh_fundamentals.py --limit 50            # smoke test
    python scripts/refresh_fundamentals.py                       # all listed, skip fresh (<7d)
    python scripts/refresh_fundamentals.py --symbols TCS,INFY --stale-days 0

Polite: ~1.5 s between companies, backs off on 429. Full market ~= 1-2 h; run weekly.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.fundamentals import fetch_company_page, save_statements, snapshot_row  # noqa: E402

BATCH = 25


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--stale-days", type=int, default=7)
    ap.add_argument("--sleep", type=float, default=1.5)
    a = ap.parse_args()

    if a.symbols:
        symbols = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        listed = db.select_all("companies", {"select": "symbol", "status": "eq.listed",
                                          "series": "in.(EQ,BE)", "order": "symbol"})
        cutoff = (datetime.now(timezone.utc) - timedelta(days=a.stale_days)).isoformat()
        fresh = {r["symbol"] for r in db.select_all(
            "company_snapshot", {"select": "symbol", "fetched_at": f"gte.{cutoff}"})}
        symbols = [r["symbol"] for r in listed if r["symbol"] not in fresh]
    if a.limit:
        symbols = symbols[:a.limit]
    print(f"{len(symbols)} companies to fetch")

    s, batch, ok, miss = requests.Session(), [], 0, []
    for i, sym in enumerate(symbols, 1):
        try:
            got = fetch_company_page(sym, s)
        except requests.RequestException as e:
            print(f"  {sym}: {e!r}"[:120])
            got = None
        if got:
            page, consol = got
            save_statements(sym, page, upload=True)  # bucket = durable copy (CI has no disk)
            batch.append({**snapshot_row(sym, page, consol),
                          "fetched_at": datetime.now(timezone.utc).isoformat()})
            ok += 1
        else:
            miss.append(sym)
        if len(batch) >= BATCH or (i == len(symbols) and batch):
            db.insert("company_snapshot", batch, on_conflict="symbol", return_rows=False)
            print(f"  {i}/{len(symbols)} saved (ok={ok}, miss={len(miss)})", flush=True)
            batch = []
        time.sleep(a.sleep)
    print(f"done: {ok} snapshots, {len(miss)} not on screener: {miss[:30]}")


if __name__ == "__main__":
    main()
