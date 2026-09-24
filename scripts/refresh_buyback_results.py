"""Realized buyback acceptance -> `buyback_results` (scanner/buyback_results.py).

    python scripts/refresh_buyback_results.py            # daily: tenders closed in the last 120 days
    python scripts/refresh_buyback_results.py --all      # backfill every settled tender without a result
    python scripts/refresh_buyback_results.py --all --retry-manual   # after a parser improvement

For each settled tender without a result row: read the company's NSE announcements from the
close date to +45 days, try the post-buyback announcement PDFs in order (announcement, newspaper
copy, closure), parse the response table, store it. A tender whose PDFs are all newspaper scans
gets a `needs_manual` row pointing at the first PDF (enter via `python -m scanner.track result`).
Nothing is stored while the +45-day window is still open and no announcement has appeared.
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
from scanner.buyback_results import fetch_symbol_announcements, parse_post_buyback, pick_result, results_row  # noqa: E402
from scanner.filings import _HEADERS  # noqa: E402
from scanner.kpis import pdf_text  # noqa: E402

WINDOW_DAYS = 45      # post-buyback announcement lands within ~3 weeks of the close
RECENT_DAYS = 120


def pending(today: date, all_: bool, retry_manual: bool = False) -> list[dict]:
    """Settled tenders with no result row — or, with retry_manual, whose row is still an unparsed
    pointer (a parser improvement can clear it; a hand-entered row is never retried)."""
    stored = db.select_all("buyback_results", {"select": "buyback_id,needs_manual,parsed_by"})
    # retry_manual re-reads every machine-read or unread row; a hand-entered row is never retried
    have = {r["buyback_id"] for r in stored if not (retry_manual and r.get("parsed_by") != "manual")}
    params = {"select": "id,symbol,close_date", "close_date": f"lt.{today - timedelta(days=2)}",
              "order": "close_date.desc"}
    if not all_:
        params["and"] = f"(close_date.gte.{today - timedelta(days=RECENT_DAYS)})"
    rows = db.select_all("buybacks", params)
    return [r for r in rows if r["id"] not in have and r.get("symbol") and r.get("close_date")]


def resolve(bb: dict, today: date, s: requests.Session) -> dict | None:
    close = date.fromisoformat(str(bb["close_date"])[:10])
    anns = fetch_symbol_announcements(bb["symbol"], close, min(close + timedelta(days=WINDOW_DAYS), today), s)
    cands = pick_result(anns)
    if not cands:
        return None
    for a in cands:
        try:
            pdf = s.get(a["attchmntFile"], headers=_HEADERS, timeout=60)
            pdf.raise_for_status()
            text, _ = pdf_text(pdf.content)
        except requests.RequestException:
            continue
        parsed = parse_post_buyback(text or "")
        if parsed:
            return results_row(bb["id"], parsed, url=a["attchmntFile"], seq_id=int(a.get("seq_id") or 0) or None)
        time.sleep(0.3)
    first = cands[0]
    return results_row(bb["id"], None, url=first["attchmntFile"], seq_id=int(first.get("seq_id") or 0) or None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--retry-manual", action="store_true", help="re-read tenders whose PDF did not parse")
    a = ap.parse_args()
    today = date.today()
    todo = pending(today, a.all, a.retry_manual)
    print(f"{len(todo)} settled tenders without a result")
    s = requests.Session()
    s.get("https://www.nseindia.com/", headers=_HEADERS, timeout=30)
    rows, waiting, failed = [], 0, 0
    for bb in todo:
        try:
            row = resolve(bb, today, s)
        except requests.RequestException as e:
            failed += 1
            print(f"  {bb['symbol']} #{bb['id']}: {e!r}"[:120])
            continue
        if row is None:
            waiting += 1
            continue
        rows.append(row)
        acc = row["ss_acceptance"]
        print(f"  {bb['symbol']:<12} close {bb['close_date']}  "
              f"{'MANUAL (scan) ' + row['source_url'] if row['needs_manual'] else f'acceptance {acc:.0%} '
              f'(reserved {row['ss_reserved']:,} / tendered {row['ss_tendered']:,})'}")
        time.sleep(0.5)
    if rows:
        good, bad = db.upsert_resilient("buyback_results", rows, "buyback_id")
        for r, err in bad:
            print(f"  rejected #{r['buyback_id']}: {err[-120:]}")
        print(f"stored {len(good)} results ({sum(r['needs_manual'] for r in rows)} need manual entry), "
              f"{waiting} still waiting for the announcement, {failed} fetch failures")
    else:
        print(f"nothing new ({waiting} waiting, {failed} fetch failures)")
    if todo and failed == len(todo):
        raise SystemExit("every fetch failed")


if __name__ == "__main__":
    main()
