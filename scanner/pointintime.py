"""As-of lookups (DATA_INFRA_SPEC WP5): values as they were on a past date, not today's.

Validation segmentation and the buyback acceptance prior bucket on market cap; using today's
cap for a 2021 event is lookahead (a stock that has since 10x'd looks large-cap in 2021).
`mcap_bucket_at` reads the weekly `company_snapshot_history` when the date is covered, else
derives the cap from statements + unadjusted closes (`fundamentals.historical_market_cap`).
"""
from __future__ import annotations

from datetime import date, timedelta


def mcap_at(d: date, history: list[dict], derive) -> float | None:
    """Market cap on date d: the latest snapshot-history row on/before d, else derive(d)."""
    known = [h for h in history if h["as_of"] <= d.isoformat() and h.get("market_cap_cr") is not None]
    if known:
        return float(max(known, key=lambda h: h["as_of"])["market_cap_cr"])
    return derive(d)


def _derived(symbol: str, d: date) -> float | None:
    import pandas as pd
    from scanner import db
    from scanner.fundamentals import historical_market_cap, load_statements
    from scanner.pricestore import get_closes
    st = load_statements(symbol)
    snap = db.select("company_snapshot", {"select": "face_value", "symbol": f"eq.{symbol}"})
    fv = snap[0]["face_value"] if snap else None
    closes = get_closes(symbol, d - timedelta(days=10), d, source="db")
    if st is None or not fv or closes is None:
        return None
    acts = db.select_all("corporate_events", {"select": "event_type,event_date,details",
                                              "symbol": f"eq.{symbol}",
                                              "event_type": "in.(bonus,split,consolidation)"})
    m = historical_market_cap(st, closes.tail(1), float(fv), acts)
    v = m.iloc[-1] if len(m) else float("nan")
    return None if pd.isna(v) else float(v)


def mcap_at_symbol(symbol: str, d: date) -> float | None:
    from scanner import db
    hist = db.select_all("company_snapshot_history", {"select": "as_of,market_cap_cr",
                                                      "symbol": f"eq.{symbol}", "order": "as_of"})
    return mcap_at(d, hist, lambda day: _derived(symbol, day))


def mcap_bucket_at(symbol: str, d: date) -> str:
    """The buyback prior's market-cap bucket as of date d (no lookahead)."""
    from scanner.buyback import mcap_bucket
    return mcap_bucket(mcap_at_symbol(symbol, d))
