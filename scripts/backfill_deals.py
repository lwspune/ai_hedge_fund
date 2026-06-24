"""One-off: backfill the cached 2-year bulk/block deal history into market_deals.

Run once (table is truncated first elsewhere / freshly created). Service-role
key required in .env (RLS blocks anon writes).

    python scripts/backfill_deals.py
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402

CSV = Path(__file__).resolve().parent.parent / "cache" / "deals_01-01-2024_31-12-2025.csv"
BATCH = 2000


def _date(s: str) -> str:
    return datetime.strptime(s.strip(), "%d-%b-%Y").date().isoformat()


def main():
    rows = []
    with open(CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                qty = int(str(r["QuantityTraded"]).replace(",", "")) if r.get("QuantityTraded") else None
                price = float(r["TradePrice/Wght.Avg.Price"]) if r.get("TradePrice/Wght.Avg.Price") else None
                d = _date(r["Date"])
            except (ValueError, KeyError):
                continue
            rows.append({
                "deal_date": d,
                "symbol": (r.get("Symbol") or "").strip(),
                "security": r.get("SecurityName"),
                "client": (r.get("ClientName") or "").strip(),
                "side": (r.get("Buy/Sell") or "").strip().upper(),
                "qty": qty, "price": price,
                "value": (qty * price) if (qty and price) else None,
                "kind": (r.get("kind") or "").strip(),
            })
    print(f"parsed {len(rows)} deal rows; inserting in batches of {BATCH}...")
    for i in range(0, len(rows), BATCH):
        db.insert("market_deals", rows[i:i + BATCH], return_rows=False)
        print(f"  {min(i + BATCH, len(rows))}/{len(rows)}")
    print("done.")


if __name__ == "__main__":
    main()
