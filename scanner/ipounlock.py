"""Pure pieces of the 6-month pre-IPO lock-in study (scripts/validate_ipo_unlock.py).

SEBI locks pre-IPO shareholders (PE / VC / early investors) for 6 months from the IPO allotment,
so month 6 is when a block of supply can first be sold. The question: is the unlock a good entry
for a 6-12 month hold, or does post-IPO drift simply continue? Controls: the same stocks entered at
month 3 and month 9. Tested in tests/test_ipounlock.py.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd

from scanner.ipostudy import is_unit_trust, on_nse

LISTING_LAG = 3          # listing is ~3 days after the allotment (median, 2020-26)
MAX_LAG = 10


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def allotment_date(ipo: dict) -> tuple[date, bool]:
    """(allotment date, guessed?) — the basis-of-allotment date when it sits 0-10 days before
    listing, else listing - 3 days (a missing or mistyped BoA)."""
    listing = date.fromisoformat(str(ipo["listing_date"]))
    boa = date.fromisoformat(str(ipo["boa_date"])) if ipo.get("boa_date") else None
    if boa and 0 <= (listing - boa).days <= MAX_LAG:
        return boa, False
    return listing - timedelta(days=LISTING_LAG), True


def unlock_events(ipos: list[dict], today: date) -> list[dict]:
    """NSE company IPOs whose 6-month unlock has passed: dates of the unlock and the month-3 /
    month-9 control entries. BSE-only listings (unpriced) and REITs / InvITs are out of scope."""
    out = []
    for r in ipos:
        if not on_nse(r.get("listing_at")) or is_unit_trust(r.get("company")):
            continue
        allot, guessed = allotment_date(r)
        unlock = add_months(allot, 6)
        if unlock > today:
            continue
        out.append({"symbol": r["symbol"], "board": r["board"], "issue_price": float(r["issue_price"]),
                    "listing_date": date.fromisoformat(str(r["listing_date"])), "allotment": allot,
                    "allot_guessed": guessed, "unlock": unlock,
                    "m3": add_months(allot, 3), "m9": add_months(allot, 9)})
    return out


def span_abnormal(stock: pd.Series | None, bench: pd.Series, d0: date, d1: date) -> float | None:
    """Stock return minus the benchmark's, close on/after d0 -> close on/after d1. None if either
    date has no close on/after it in the series."""
    if stock is None or len(stock) == 0:
        return None
    s = stock.sort_index()
    i, j = s.index.searchsorted(pd.Timestamp(d0)), s.index.searchsorted(pd.Timestamp(d1))
    if i >= len(s) or j >= len(s) or j <= i:
        return None
    b = bench.sort_index()
    b0, b1 = b.asof(s.index[i]), b.asof(s.index[j])
    if pd.isna(b0) or pd.isna(b1) or b0 == 0:
        return None
    return float(s.iloc[j] / s.iloc[i] - 1 - (b1 / b0 - 1))
