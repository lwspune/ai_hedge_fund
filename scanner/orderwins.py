"""Order-win event study (candidate signal #9): does a disclosed order win (SEBI Reg 30
'Bagging/Receiving of orders/contracts') move the stock AFTER disclosure, and does it depend on
the order's size relative to revenue (the surprise)?

Pure logic (tested); runner scripts/validate_order_wins.py.
"""
from __future__ import annotations

from datetime import date, timedelta

from scanner.fundamentals import period_end

REPORTING_LAG_DAYS = 60   # a fiscal year's revenue is public ~2 months after year end (no look-ahead)


def cluster_orders(rows: list[dict], gap_days: int = 5) -> list[dict]:
    """Order filings -> events: same symbol within `gap_days` calendar days of the previous
    filing merge; date = first disclosure; value = sum of disclosed values (None if none known)."""
    out: list[dict] = []
    last: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: (r["symbol"], r["disclosed_at"])):
        d = r["disclosed_at"][:10]
        cur = last.get(r["symbol"])
        if cur and (date.fromisoformat(d) - date.fromisoformat(cur["_last"])).days <= gap_days:
            cur["n"] += 1
            cur["_last"] = d
            if r["value_cr"] is not None:
                cur["value_cr"] = (cur["value_cr"] or 0.0) + r["value_cr"]
            continue
        cur = {"symbol": r["symbol"], "date": d, "n": 1, "value_cr": r["value_cr"], "_last": d}
        last[r["symbol"]] = cur
        out.append(cur)
    for e in out:
        e.pop("_last")
    return sorted(out, key=lambda e: (e["date"], e["symbol"]))


def revenue_before(annual: list[dict], event_date: str) -> float | None:
    """Revenue of the latest fiscal year already PUBLIC on `event_date` (year end + reporting lag);
    TTM rows ignored. None if no such year or revenue isn't positive."""
    cutoff = date.fromisoformat(event_date) - timedelta(days=REPORTING_LAG_DAYS)
    best = None
    for r in annual or []:
        pe = period_end(r.get("period", ""))
        if pe and date.fromisoformat(pe) <= cutoff and (best is None or pe > best[0]):
            best = (pe, r.get("revenue"))
    return best[1] if best and best[1] and best[1] > 0 else None


def size_bucket(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    return "<5%" if ratio < 0.05 else "5-25%" if ratio < 0.25 else ">=25%"
