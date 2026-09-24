"""Anchor lock-in expiry study (candidate signal #2): does the release of anchor-investor
shares 30 / 90 days after an IPO allotment push the price down (a supply overhang a short
could harvest, or a long should avoid)?

Pure event math (tested) — the runner is scripts/validate_lockin.py. Windows are fixed
BEFORE looking at results (see WINDOWS); T = first trading day on/after the expiry date.
"""
from __future__ import annotations

import pandas as pd

# Pre-specified windows, (from, to) in trading days relative to T.
WINDOWS = {"pre": (-10, -1), "event": (-1, 2), "post": (2, 10), "full": (-10, 10)}
# SEBI split anchor lock-in into 50% @30d + 50% @90d for issues opening from 1-Apr-2022.
ERA_CUTOFF = "2022-04-01"
# Corporate actions that break a price window (share count / nominal price changes).
BLOCKING = {"split", "bonus", "consolidation", "rights", "demerger"}


def lockin_events(ipos: list[dict]) -> list[dict]:
    """One event per anchor lock-in expiry (30d and 90d) with the segment attributes the
    study cuts on. Expiries on/before the listing date are data errors and dropped."""
    out = []
    for r in ipos:
        listing = r.get("listing_date")
        frac = None
        if r.get("anchor_shares") and r.get("shares_allotted"):
            frac = round(r["anchor_shares"] / r["shares_allotted"], 4)
        for kind, key in (("30d", "anchor_lockin_30"), ("90d", "anchor_lockin_90")):
            exp = r.get(key)
            if not exp or not listing or exp <= listing:
                continue
            out.append({"symbol": r["symbol"], "kind": kind, "expiry": exp, "listing_date": listing,
                        "board": r.get("board"), "issue_price": r.get("issue_price"),
                        "anchor_frac": frac,
                        "era": "post_apr2022" if listing >= ERA_CUTOFF else "pre_apr2022"})
    return out


def window_return(stock: pd.Series | None, bench: pd.Series, event_date, a: int, b: int):
    """Benchmark-adjusted return from close T+a to close T+b (T = first trading day >=
    event_date). None if either end falls outside the series."""
    if stock is None or len(stock) == 0:
        return None
    stock = stock.sort_index()
    t = stock.index.searchsorted(pd.Timestamp(event_date))
    i, j = t + a, t + b
    if i < 0 or j >= len(stock) or t >= len(stock) or j <= i:
        return None
    d_i, d_j = stock.index[i], stock.index[j]
    bb = bench.sort_index()
    b_i, b_j = bb.asof(d_i), bb.asof(d_j)
    if pd.isna(b_i) or pd.isna(b_j) or b_i == 0 or stock.iloc[i] == 0:
        return None
    return float(stock.iloc[j] / stock.iloc[i] - 1 - (b_j / b_i - 1))


def blocking_action(actions: list[dict], symbol: str, lo, hi) -> bool:
    """True if `symbol` had a share-count-changing corporate action with ex-date in [lo, hi]."""
    lo, hi = str(pd.Timestamp(lo).date()), str(pd.Timestamp(hi).date())
    return any(a["symbol"] == symbol and a["event_type"] in BLOCKING and lo <= a["event_date"] <= hi
               for a in actions)


def _inr(n) -> str:
    """Indian digit grouping: 1200000 -> '12,00,000'."""
    if n is None:
        return "—"
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups) + "," + tail


def format_unlocks(rows: list[dict]) -> str:
    """Upcoming anchor lock-in expiries (corporate_events rows) as a date-ordered table."""
    if not rows:
        return "No anchor lock-in expiries in the window."
    out = [f"{'date':<11} {'symbol':<14} {'unlock':<6} {'board':<9} {'anchor shares':>14}"]
    for r in sorted(rows, key=lambda r: (r["event_date"], r["symbol"])):
        d = r.get("details") or {}
        kind = "30d" if r["event_type"] == "anchor_lockin_30" else "90d"
        out.append(f"{r['event_date']:<11} {r['symbol']:<14} {kind:<6} {d.get('board') or '—':<9} "
                   f"{_inr(d.get('anchor_shares')):>14}")
    return "\n".join(out)
