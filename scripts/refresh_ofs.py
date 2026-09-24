"""OFS events -> `ofs_events` (scanner/ofs.py). chittorgarh ids probed upward from the highest
stored one (minus a few, so recently edited pages are re-read); stops after `--gap` misses.

    python scripts/refresh_ofs.py             # daily
    python scripts/refresh_ofs.py --from 1    # backfill (chittorgarh's OFS pages start Jan-2025)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.ofs import fetch_ofs  # noqa: E402

RECHECK = 4   # ids below the frontier re-read each run (cut-off / date edits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", type=int)
    ap.add_argument("--gap", type=int, default=8)
    ap.add_argument("--cap", type=int, default=150)
    a = ap.parse_args()
    if a.frm is None:
        rows = db.select("ofs_events", {"select": "chittorgarh_id", "order": "chittorgarh_id.desc", "limit": "1"})
        a.frm = max(1, (rows[0]["chittorgarh_id"] if rows else 1) - RECHECK)
    s, now = requests.Session(), datetime.now(timezone.utc).isoformat()
    out, gap, oid, fetched, seen = [], 0, a.frm, 0, 0
    while gap < a.gap and fetched < a.cap:
        exists, row = fetch_ofs(oid, s)
        fetched += 1
        oid += 1
        time.sleep(0.2)
        if not exists:
            gap += 1
            continue
        gap, seen = 0, seen + 1
        if row:
            row["updated_at"] = now
            out.append(row)
    if out:
        good, bad = db.upsert_resilient("ofs_events", out, "chittorgarh_id")
        for r, err in bad:
            print(f"  rejected {r['chittorgarh_id']} {r['symbol']}: {err[-120:]}")
        print(f"upserted {len(good)} OFS events (ids {out[0]['chittorgarh_id']}..{out[-1]['chittorgarh_id']}; "
              f"{seen} pages seen, {fetched} fetched)")
    else:
        print(f"no OFS pages parsed ({seen} pages seen from id {a.frm}, {fetched} fetched)")
    if seen and not out:
        raise SystemExit("pages exist but none parsed — chittorgarh format change?")


if __name__ == "__main__":
    main()
