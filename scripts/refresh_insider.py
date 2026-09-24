"""SEBI PIT insider disclosures -> `insider_trades` (scanner/insider.py, `api/corporates-pit-gg`).

    python scripts/refresh_insider.py                     # daily: filings broadcast in the last 10 days
    python scripts/refresh_insider.py --from 2026-05-01   # a window (the endpoint reaches back ~5 months)
    python scripts/refresh_insider.py --all               # whatever the undated list returns (initial load)

Filings already stored (app_id) are skipped; each new filing's XBRL is fetched and its
disclosures upserted on (app_id, seq).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.insider import fetch_pit_filings, fetch_xml, insider_rows, parse_pit_xml  # noqa: E402

CHUNK = 300


def stored_app_ids(since: str | None) -> set[int]:
    params = {"select": "app_id"}
    if since:
        params["broadcast_at"] = f"gte.{since}"
    return {r["app_id"] for r in db.select_all("insider_trades", params)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", type=date.fromisoformat)
    ap.add_argument("--to", type=date.fromisoformat, default=date.today())
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    s = requests.Session()
    if a.all:
        filings, since = fetch_pit_filings(session=s), None
    else:
        frm = a.frm or a.to - timedelta(days=10)
        filings, since = fetch_pit_filings(frm, a.to, s), (frm - timedelta(days=1)).isoformat()
    known = stored_app_ids(since)
    todo = [f for f in filings if f["app_id"] not in known]
    print(f"{len(filings)} filings listed, {len(todo)} new", flush=True)
    rows, n, failed = [], 0, 0
    for k, f in enumerate(todo, 1):
        try:
            rows += insider_rows(f, parse_pit_xml(fetch_xml(f["xml_url"], s)))
        except requests.RequestException as e:
            failed += 1
            print(f"  {f['app_id']} {f['symbol']}: {e!r}"[:120])
        if len(rows) >= CHUNK:
            good, bad = db.upsert_resilient("insider_trades", rows, "app_id,seq")
            for r, err in bad:
                print(f"  rejected {r['app_id']}/{r['seq']} {r['symbol']}: {err[-120:]}")
            n += len(good)
            rows = []
        if k % 200 == 0:
            print(f"  {k}/{len(todo)}", flush=True)
        time.sleep(0.15)
    if rows:
        good, bad = db.upsert_resilient("insider_trades", rows, "app_id,seq")
        for r, err in bad:
            print(f"  rejected {r['app_id']}/{r['seq']} {r['symbol']}: {err[-120:]}")
        n += len(good)
    print(f"upserted {n} insider disclosures from {len(todo) - failed} filings ({failed} fetch failures)")
    if todo and failed == len(todo):
        raise SystemExit("every XBRL fetch failed")


if __name__ == "__main__":
    main()
