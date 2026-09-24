"""Demerger listing-flow study (candidate signal #10): when a demerged child lists, index
funds and benchmark-bound institutions must sell what they received (the child is in no
index), and nobody can front-run it because the child cannot be bought before it lists. Does
the forced selling of the first sessions leave a dip a retail buyer can capture?

Pure logic (tested) — the runner is scripts/validate_demerger.py. Windows are fixed BEFORE
looking at results (WINDOWS); T = the child's first trading day. NSE keeps a scheme listing in
the trade-for-trade (BE) series with a 5% band for its first 10 sessions, so the selling is
spread over days rather than a single print — hence a 5-session "sell" window.

Event set: data/demerger_listings.csv, curated by hand (the corporate-action feed gives only
the parent's ex-date; no free source names the child). Every row was verified against the
company master's listing date or, for delisted children, the first bhavcopy close in the
price store. 27 of the 90 demerger records since 2019 have no newly listed child (hive-offs
into listed companies, renamed parents, the child's own record) and are excluded, not guessed.
`parent_index` (nifty50 / next50 / blank) is curated too: index_membership history starts in
2026, so only memberships known with certainty are marked.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from scanner.eventstudy import window_return  # noqa: F401  (re-exported; generic)

LISTINGS_CSV = Path(__file__).resolve().parent.parent / "data" / "demerger_listings.csv"

# Pre-specified windows in trading days relative to T = the child's first close.
WINDOWS = {"sell": (0, 5), "recovery": (5, 20), "late": (10, 30), "full": (0, 30)}
# Same-length (5-session) windows on the same child, well clear of the listing.
PLACEBO = {"placebo_a": (60, 65), "placebo_b": (120, 125)}
MIN_GAP_DAYS, MAX_GAP_DAYS = 10, 400   # ex-date -> listing: a scheme listing, not an unrelated one
SETTLE_DAYS = 45                        # calendar days after listing for T+30 to exist


def load_listings(path: Path = LISTINGS_CSV) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def era_of(d: str) -> str:
    y = int(d[:4])
    return "2019-21" if y <= 2021 else "2022-23" if y <= 2023 else "2024-26"


def study_events(rows: list[dict], companies: dict, today: date) -> list[dict]:
    """One event per listed child, with guards: the child must exist in the company master
    (delisted rows count), the listing must fall MIN..MAX gap days after the parent's ex-date,
    and T+30 must have had time to happen. `scheme` groups children of one demerger (they
    share every date) for cluster-robust statistics."""
    out = []
    for r in rows:
        child, ex, lst = r["child"], r["ex_date"], r["listing_date"]
        if child not in companies:
            continue
        gap = (date.fromisoformat(lst) - date.fromisoformat(ex)).days
        if not MIN_GAP_DAYS <= gap <= MAX_GAP_DAYS:
            continue
        if date.fromisoformat(lst) > today - timedelta(days=SETTLE_DAYS):
            continue
        out.append({"parent": r["parent"], "child": child, "ex_date": ex, "listing_date": lst,
                    "gap_days": gap, "scheme": f"{r['parent']}|{ex}", "era": era_of(lst),
                    "parent_index": r.get("parent_index") or "", "note": r.get("note") or ""})
    return sorted(out, key=lambda e: (e["listing_date"], e["child"]))


def index_at(symbol: str, d: date, membership: list[dict]) -> str | None:
    """Index key (nifty50 / next50 / ...) the symbol belonged to on date d per interval rows
    {symbol, index_key, from_date, to_date|None}; None when not a member of anything."""
    ds = d.isoformat()
    keys = sorted({m["index_key"] for m in membership
                   if m["symbol"] == symbol and m["from_date"] <= ds
                   and (m.get("to_date") is None or m["to_date"] >= ds)})
    if not keys:
        return None
    for pref in ("nifty50", "next50", "niftynext50"):
        if pref in keys:
            return "next50" if pref == "niftynext50" else pref
    return keys[0]


def first_sessions(closes: pd.Series, n: int = 10) -> pd.Series:
    """The child's first n closes (for the day-by-day path table)."""
    return closes.sort_index().iloc[:n]
