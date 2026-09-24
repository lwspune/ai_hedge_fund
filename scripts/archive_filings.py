"""Filings retention (DATA_INFRA_SPEC WP8): archive old months to the bucket, trim the table.

    python scripts/archive_filings.py                  # weekly: months older than 24
    python scripts/archive_filings.py --older-than 24

For each whole month older than the cutoff: every filings row of that month (all columns) is
merged into bucket `filings` / YYYY-MM.parquet — a stored subject is never replaced by a null,
so re-runs are idempotent — and only after the upload succeeds is `subject` nulled in the table,
one update per month. Rows are never deleted (company_kpis FKs + dashboard counts), and a
subject is kept while KPI extraction may still need it (not yet extracted and KPI-bearing:
extract_kpis selects call transcripts by subject).
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BUCKET = "filings"
KEEP_MONTHS = 24


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def archive_months(oldest: date, today: date, keep_months: int = KEEP_MONTHS) -> list[tuple[date, date]]:
    """[(month_start, next_month_start)] for whole months that end before today - keep_months."""
    cutoff = _add_months(date(today.year, today.month, 1), -keep_months)
    out, m = [], date(oldest.year, oldest.month, 1)
    while _add_months(m, 1) <= cutoff:
        out.append((m, _add_months(m, 1)))
        m = _add_months(m, 1)
    return out


def merge_archive(stored: pd.DataFrame | None, fresh: pd.DataFrame) -> pd.DataFrame:
    """fresh rows + any stored rows, one per seq_id; a stored subject wins over a null one."""
    if stored is None or stored.empty:
        return fresh
    kept = stored.set_index("seq_id")["subject"].dropna()
    out = pd.concat([fresh, stored[~stored["seq_id"].isin(fresh["seq_id"])]], ignore_index=True)
    out["subject"] = out["subject"].where(out["subject"].notna(), out["seq_id"].map(kept))
    return out.sort_values("seq_id").reset_index(drop=True)


def main():
    from scanner import db
    from scripts.extract_kpis import KPI_FILTER
    ap = argparse.ArgumentParser()
    ap.add_argument("--older-than", type=int, default=KEEP_MONTHS, help="months to keep in the table")
    a = ap.parse_args()
    first = db.select("filings", {"select": "disclosed_at", "order": "disclosed_at", "limit": "1"})
    if not first:
        return
    months = archive_months(date.fromisoformat(first[0]["disclosed_at"][:10]), date.today(), a.older_than)
    total = 0
    for lo, hi in months:
        span = f"(disclosed_at.gte.{lo},disclosed_at.lt.{hi})"
        rows = db.select_all("filings", {"select": "*", "and": span, "order": "seq_id"})
        if not rows:
            continue
        key = f"{lo:%Y-%m}.parquet"
        blob = db.storage_get(BUCKET, key)
        month = merge_archive(pd.read_parquet(io.BytesIO(blob)) if blob else None, pd.DataFrame(rows))
        buf = io.BytesIO()
        month.to_parquet(buf, index=False, compression="zstd")
        db.storage_put(BUCKET, key, buf.getvalue(), "application/vnd.apache.parquet")
        # only after the month is safely in the bucket: trim what extraction no longer needs
        db.update("filings", {"and": span, "subject": "not.is.null", "extracted_at": "not.is.null"},
                  {"subject": None})
        db.update("filings", {"and": span, "subject": "not.is.null", "extracted_at": "is.null",
                              "not.or": KPI_FILTER}, {"subject": None})
        total += len(rows)
        print(f"  {lo:%Y-%m}: {len(rows)} filings archived to {BUCKET}/{key}", flush=True)
    print(f"archived {len(months)} months ({total} rows); subjects trimmed where extraction is done")


if __name__ == "__main__":
    main()
