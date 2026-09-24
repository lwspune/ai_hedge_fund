"""Extract KPIs from filing PDFs (F3): newest unprocessed KPI-bearing filings first, marking each
filing done so runs resume. The daily cloud job runs it with a cap, so the historical backlog
clears itself over a couple of weeks while new filings are covered the same day.

    python scripts/extract_kpis.py --limit 1500
    python scripts/extract_kpis.py --since 2025-07-01 --limit 200
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
from scanner.kpis import extract_all, kpi_rows, pdf_text  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
      "Referer": "https://www.nseindia.com/"}
# PostgREST filter: presentations, press releases, order wins, and call transcripts
KPI_FILTER = ("(category.eq.Investor Presentation,category.like.Press Release*,"
              "category.eq.Bagging/Receiving of orders/contracts,"
              "category.eq.Awarding of order(s)/contract(s),"
              "and(category.like.Analysts*,subject.ilike.*transcript*))")


def pending(limit: int, since: str) -> list[dict]:
    return db.select("filings", {
        "select": "seq_id,symbol,category,subject,disclosed_at,attachment_url",
        "extracted_at": "is.null", "disclosed_at": f"gte.{since}", "or": KPI_FILTER,
        "order": "disclosed_at.desc", "limit": str(limit)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1500)
    ap.add_argument("--since", default="2025-07-01")
    a = ap.parse_args()
    todo = pending(a.limit, a.since)
    print(f"{len(todo)} filings to extract", flush=True)
    sector = {r["symbol"]: r["sector"] for r in db.select_all("company_snapshot", {"select": "symbol,sector"})}
    s, stats, n_kpis = requests.Session(), {"ok": 0, "no_pdf": 0, "error": 0}, 0
    for i, f in enumerate(todo, 1):
        status, rows = "no_pdf", []
        if f["attachment_url"]:
            try:
                r = s.get(f["attachment_url"], headers=UA, timeout=60)
                text, _ = pdf_text(r.content) if r.status_code == 200 else (None, 0)
                if text is not None:
                    rows = kpi_rows(f, extract_all(text, f["category"], f["subject"],
                                                   sector.get(f["symbol"])))
                    status = "ok"
            except requests.RequestException as e:
                status = "error"
                print(f"  {f['seq_id']} {f['symbol']}: {e!r}"[:120])
        if rows:
            _, bad = db.upsert_resilient("company_kpis", rows, "seq_id,kpi,quote_hash")
            for row, err in bad:
                print(f"  rejected kpi {row['symbol']} {row['kpi']}: {err[-120:]}")
            n_kpis += len(rows) - len(bad)
        db.update("filings", {"seq_id": f"eq.{f['seq_id']}"},
                  {"extract_status": status, "extracted_at": datetime.now(timezone.utc).isoformat()})
        stats[status] += 1
        if i % 100 == 0:
            print(f"  {i}/{len(todo)} {stats} kpis={n_kpis}", flush=True)
        time.sleep(0.3)
    print(f"done: {stats}, {n_kpis} KPI rows")


if __name__ == "__main__":
    main()
