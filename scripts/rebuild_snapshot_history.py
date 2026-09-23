"""Rebuild company_snapshot.history from the local statement cache (no re-scrape).

    python scripts/rebuild_snapshot_history.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.fundamentals import STATEMENTS_DIR, history_json, load_statements  # noqa: E402


def main():
    snap = {r["symbol"] for r in db.select_all("company_snapshot", {"select": "symbol"})}
    n = 0
    for fp in sorted(STATEMENTS_DIR.glob("*.parquet")):
        sym = fp.stem.replace("_and_", "&")
        if sym not in snap:
            continue
        df = load_statements(sym)
        hist = history_json({"statements": df.to_dict("records")})
        db.update("company_snapshot", {"symbol": f"eq.{sym}"}, {"history": hist})
        n += 1
    print(f"rebuilt history for {n} companies")


if __name__ == "__main__":
    main()
