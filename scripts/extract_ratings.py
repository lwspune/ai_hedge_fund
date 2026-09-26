"""Extract credit ratings from NSE rating filings (scanner/ratings.py): newest unprocessed
`Credit Rating*` filings first, marking each filing done so runs resume. A filing whose PDF
yields no rating is marked `no_rating` (ESG scores, withdrawals without a grade, image-only
PDFs) — the queue to review by hand.

    python scripts/extract_ratings.py                         # daily: newest 500
    python scripts/extract_ratings.py --limit 20000           # backfill (backfill.yml what=credit-ratings)
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
from scanner.kpis import pdf_text  # noqa: E402
from scanner.ratings import parse_ratings, rating_rows  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
      "Referer": "https://www.nseindia.com/"}
MAX_PAGES = 12   # covering letter + the agency letter; rationale annexures add nothing


def pending(limit: int, since: str) -> list[dict]:
    """Paged: PostgREST caps one response at 1000 rows, whatever `limit` asks for."""
    return db.select_all("filings", {
        "select": "seq_id,symbol,category,disclosed_at,attachment_url",
        "category": "like.Credit Rating*", "extracted_at": "is.null", "disclosed_at": f"gte.{since}",
        "order": "disclosed_at.desc,seq_id.desc"}, max_rows=limit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--since", default="2020-01-01")
    a = ap.parse_args()
    todo = pending(a.limit, a.since)
    print(f"{len(todo)} rating filings to extract", flush=True)
    s, stats, n_rows = requests.Session(), {"ok": 0, "no_rating": 0, "no_pdf": 0, "error": 0}, 0
    for i, f in enumerate(todo, 1):
        status, rows = "no_pdf", []
        if f["attachment_url"]:
            try:
                r = s.get(f["attachment_url"], headers=UA, timeout=60)
                text, _ = pdf_text(r.content, MAX_PAGES) if r.status_code == 200 else (None, 0)
                if text is not None:
                    rows = rating_rows(f, parse_ratings(text))
                    status = "ok" if rows else "no_rating"
            except requests.RequestException as e:
                status = "error"
                print(f"  {f['seq_id']} {f['symbol']}: {e!r}"[:120])
        if rows:
            _, bad = db.upsert_resilient("credit_ratings", rows, "seq_id,agency,term")
            for row, err in bad:
                print(f"  rejected rating {row['symbol']} {row['agency']} {row['rating']}: {err[-120:]}")
            n_rows += len(rows) - len(bad)
        db.update("filings", {"seq_id": f"eq.{f['seq_id']}"},
                  {"extract_status": status, "extracted_at": datetime.now(timezone.utc).isoformat()})
        stats[status] += 1
        if i % 100 == 0:
            print(f"  {i}/{len(todo)} {stats} ratings={n_rows}", flush=True)
        time.sleep(0.3)
    print(f"done: {stats}, {n_rows} rating rows")


if __name__ == "__main__":
    main()
