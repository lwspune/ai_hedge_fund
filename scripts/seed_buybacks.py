"""One-off: seed the buybacks table from the cached historical scrape so the
dashboard has real data to render. Run while RLS is off (anon key can write).

    python scripts/seed_buybacks.py
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402

CSV = Path(__file__).resolve().parent.parent / "cache" / "buybacks.csv"


def main():
    today = date.today().isoformat()
    rows = []
    with open(CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sym = (r.get("symbol") or "").strip()
            if not sym:
                continue  # need a symbol to be useful in the dashboard
            close = (r.get("close_date") or "").strip() or None
            rows.append({
                "chittorgarh_id": int(r["id"]),
                "company": r.get("company"),
                "symbol": sym,
                "buyback_price": float(r["buyback_price"]) if r.get("buyback_price") else None,
                "record_date": (r.get("record_date") or "").strip() or None,
                "close_date": close,
                "entitlement_small": float(r["entitlement_small"]) if r.get("entitlement_small") else None,
                "est_return": None,
                "status": "settled" if close and close < today else "open",
            })
    res = db.insert("buybacks", rows, on_conflict="chittorgarh_id")
    print(f"seeded {len(res)} buybacks (of {len(rows)} with symbols)")


if __name__ == "__main__":
    main()
