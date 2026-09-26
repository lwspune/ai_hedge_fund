"""Pure math for the IPO study (scripts/validate_ipo.py): what one retail application is worth.

Retail gets a reserved slice (35% of a mainboard issue) that institutions can't bid into; when it
is oversubscribed, SEBI allots by lottery, one minimum lot per winning applicant. So an
application's value is P(allotment) x the listing gain. Tested in tests/test_ipostudy.py.
"""
from __future__ import annotations

import re

SELL_COST = 0.002        # brokerage + STT + charges on the listing-day sale
# REITs / InvITs list units of a trust, not company shares ("Trust Fintech" is a company)
_UNIT_TRUST = re.compile(r"\bREIT\b|\bInvIT\b|\b(?:Investment|Infra|Highways|Realty|Select) Trust\b", re.I)


def is_unit_trust(company: str | None) -> bool:
    return bool(company and _UNIT_TRUST.search(company))


def on_nse(listing_at: str | None) -> bool:
    """The study's scope: NSE listings (the bhavcopy prices them; BSE is unreachable from runners)."""
    return bool(listing_at and "NSE" in listing_at.upper())


def allot_prob(board: str, retail_shares: int | None, lot_size: int | None, applications: int | None,
               sub_retail: float | None) -> float | None:
    """P(one retail application is allotted). Mainboard: minimum lots available / applications —
    many retail bids are for the Rs 2 lakh maximum, so 1/times-subscribed would understate the
    odds (applications counts every category: a slight underestimate). SME: retail bids are the
    minimum application, so 1/times-subscribed is the lottery's odds. Undersubscribed: 1."""
    if sub_retail is not None and sub_retail <= 1:
        return 1.0
    if board == "mainboard" and retail_shares and lot_size and applications:
        return min(1.0, (retail_shares // lot_size) / applications)
    if sub_retail:
        return min(1.0, 1 / sub_retail)
    return None


def listing_gain(issue_price: float | None, sell_price: float | None) -> float | None:
    """Return on an allotted lot sold at `sell_price` (listing open or close), after the sale's costs."""
    if not issue_price or not sell_price:
        return None
    return sell_price / issue_price - 1 - SELL_COST


def gmp_pct(gmp: float | None, issue_price: float | None) -> float | None:
    return gmp / issue_price if gmp is not None and issue_price else None
