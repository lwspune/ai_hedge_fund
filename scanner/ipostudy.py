"""Pure math for the IPO study (scripts/validate_ipo.py): what one retail application is worth.

Retail gets a reserved slice (35% of a mainboard issue) that institutions can't bid into; when it
is oversubscribed, SEBI allots by lottery, one minimum lot per winning applicant. So an
application's value is P(allotment) x the listing gain. Tested in tests/test_ipostudy.py.
"""
from __future__ import annotations

import re

from scanner.ipobids import final_retail_from_nse

SELL_COST = 0.002        # brokerage + STT + charges on the listing-day sale
LOTS_PER_APPLICANT = 1.10    # P x retail times, median of 32 mainboard IPOs with exact counts (1.01-1.54)
# REITs / InvITs list units of a trust, not company shares ("Trust Fintech" is a company)
_UNIT_TRUST = re.compile(r"\bREIT\b|\bInvIT\b|\b(?:Investment|Infra|Highways|Realty|Select) Trust\b", re.I)


def is_unit_trust(company: str | None) -> bool:
    return bool(company and _UNIT_TRUST.search(company))


def on_nse(listing_at: str | None) -> bool:
    """The study's scope: NSE listings (the bhavcopy prices them; BSE is unreachable from runners)."""
    return bool(listing_at and "NSE" in listing_at.upper())


def allot_prob(board: str, retail_shares: int | None, lot_size: int | None, applications: int | None,
               sub_retail: float | None, sub_retail_nse: float | None = None) -> float | None:
    """P(one retail application is allotted). Mainboard, best to worst: minimum lots available /
    applications (applications counts every category: a slight underestimate); else
    LOTS_PER_APPLICANT / consolidated retail times (applicants bid ~1.1 lots on average, so
    1/times alone would understate the odds); else the same from NSE's retail figure scaled by
    NSE's share of retail bids. SME: retail bids are the minimum application, so 1/times is the
    lottery's odds — and without the retail figure it is unknown (overall times is no proxy:
    retail / overall ranges 0.2-10x on SME issues). Undersubscribed: 1."""
    if board == "mainboard" and not sub_retail:
        sub_retail = final_retail_from_nse(sub_retail_nse)
    if sub_retail is not None and sub_retail <= 1:
        return 1.0
    if board == "mainboard" and retail_shares and lot_size and applications:
        return min(1.0, (retail_shares // lot_size) / applications)
    if sub_retail:
        return min(1.0, (LOTS_PER_APPLICANT if board == "mainboard" else 1.0) / sub_retail)
    return None


def listing_gain(issue_price: float | None, sell_price: float | None) -> float | None:
    """Return on an allotted lot sold at `sell_price` (listing open or close), after the sale's costs."""
    if not issue_price or not sell_price:
        return None
    return sell_price / issue_price - 1 - SELL_COST


def gmp_pct(gmp: float | None, issue_price: float | None) -> float | None:
    return gmp / issue_price if gmp is not None and issue_price else None
