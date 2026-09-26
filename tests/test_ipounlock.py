"""Test-first spec for the 6-month pre-IPO lock-in study's pure pieces (scanner/ipounlock.py)."""
from datetime import date

import pandas as pd
import pytest

from scanner.ipounlock import add_months, allotment_date, span_abnormal, unlock_events


def test_add_months_clamps_to_month_end():
    assert add_months(date(2025, 3, 10), 6) == date(2025, 9, 10)
    assert add_months(date(2025, 8, 31), 6) == date(2026, 2, 28)
    assert add_months(date(2023, 8, 31), 6) == date(2024, 2, 29)
    assert add_months(date(2025, 11, 15), 3) == date(2026, 2, 15)


def test_allotment_date_trusts_the_boa_only_when_it_fits():
    assert allotment_date({"boa_date": "2025-03-10", "listing_date": "2025-03-13"}) == (date(2025, 3, 10), False)
    # missing, after listing, or implausibly early -> listing - 3 days, flagged
    assert allotment_date({"boa_date": None, "listing_date": "2025-03-13"}) == (date(2025, 3, 10), True)
    assert allotment_date({"boa_date": "2025-03-14", "listing_date": "2025-03-13"}) == (date(2025, 3, 10), True)
    assert allotment_date({"boa_date": "2025-02-01", "listing_date": "2025-03-13"}) == (date(2025, 3, 10), True)


def _ipo(**kw):
    base = {"symbol": "NEWCO", "company": "New Co", "board": "mainboard", "listing_at": "BSE, NSE",
            "boa_date": "2025-03-10", "listing_date": "2025-03-13", "issue_price": 100.0}
    return {**base, **kw}


def test_unlock_events_dates_and_controls():
    ev = unlock_events([_ipo()], today=date(2026, 9, 26))
    assert len(ev) == 1
    e = ev[0]
    assert (e["unlock"], e["m3"], e["m9"]) == (date(2025, 9, 10), date(2025, 6, 10), date(2025, 12, 10))
    assert e["listing_date"] == date(2025, 3, 13) and e["allot_guessed"] is False


def test_unlock_events_scope_and_timing():
    rows = [_ipo(symbol="BSEONLY", listing_at="BSE SME"), _ipo(symbol="REIT1", company="Some REIT Date"),
            _ipo(symbol="FRESH", boa_date="2026-06-01", listing_date="2026-06-04"),   # unlock still ahead
            _ipo(symbol="OK")]
    assert [e["symbol"] for e in unlock_events(rows, today=date(2026, 9, 26))] == ["OK"]


def _s(dates, vals):
    return pd.Series(vals, index=pd.to_datetime(dates), dtype="float64")


def test_span_abnormal_between_two_dates():
    stock = _s(["2025-03-13", "2025-03-14", "2025-09-10", "2025-09-11"], [100, 101, 90, 91])
    bench = _s(["2025-03-13", "2025-09-10", "2025-09-11"], [1000, 1100, 1100])
    # close on/after d0 -> close on/after d1: -10% vs +10%
    assert span_abnormal(stock, bench, date(2025, 3, 13), date(2025, 9, 10)) == pytest.approx(-0.20)
    assert span_abnormal(stock, bench, date(2025, 3, 13), date(2025, 9, 13)) is None     # d1 past the data
    assert span_abnormal(None, bench, date(2025, 3, 13), date(2025, 9, 10)) is None
