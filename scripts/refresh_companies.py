"""Refresh the company master (infra I1): NSE/niftyindices static CSVs -> companies +
symbol_changes. Idempotent upserts; safe to re-run weekly.

    python scripts/refresh_companies.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.master import fetch_all  # noqa: E402

CHUNK = 500


def main():
    companies, changes = fetch_all()
    now = datetime.now(timezone.utc).isoformat()
    for i in range(0, len(companies), CHUNK):
        db.insert("companies", [{**c, "updated_at": now} for c in companies[i:i + CHUNK]],
                  on_conflict="symbol", return_rows=False)
    for i in range(0, len(changes), CHUNK):
        db.insert("symbol_changes", changes[i:i + CHUNK],
                  on_conflict="old_symbol,new_symbol,changed_on", return_rows=False)
    print(f"upserted {len(companies)} companies, {len(changes)} symbol changes")


if __name__ == "__main__":
    main()
