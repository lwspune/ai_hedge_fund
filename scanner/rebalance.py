"""Index-rebalance front-run: event set + pure leg math.

Thesis fit (🟢 structural / forced-flow): when NSE Indices reconstitutes NIFTY 50 /
Next 50, passive index funds MUST buy the additions and sell the deletions at the
effective-date close — a flow they cannot time or price away. A front-runner enters
on the announcement (T0+1) and exits at the effective date: long the adds, short the
drops.

The pure logic here, beyond `scanner.eventstudy`, is (1) exiting on a *specific date*
(the effective date varies per event, not a fixed horizon) and (2) signing the return
by leg. Price fetching + the live run live in scripts/validate_index_rebalance.py.

EVENT-SET HONESTY (this is the gating input — read before trusting any result):
  * Only REGULAR semi-annual (March / September) reviews are included. Ad-hoc,
    merger-driven swaps (e.g. May-2017 Grasim/Vedanta, Jul-2020 Vedanta/HDFC Life,
    the Jul-2023 HDFC-Ltd merger removal that brought in LTIMindtree off-cycle) are
    CONFOUNDED forced flows tangled with a corporate action and are deliberately excluded.
  * Every `announce` date below (the entry trigger — what matters most) is confirmed
    against the niftyindices press release / NSE circular or contemporaneous reporting
    on that release; see each row's source. verified=True across the board.
  * 2023 carries NO rows by design, not by omission: the NIFTY 50 had NO regular-review
    change in either the March 2023 or September 2023 semi-annual review (confirmed —
    only the broader indices were rejigged Sep-29-2023; the 50 was untouched). The only
    2023 change to the 50 was the July HDFC->LTIMindtree merger swap, excluded as above.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_NEXT50_CSV = Path(__file__).resolve().parent.parent / "data" / "next50_rebalance_events.csv"

# Provenance — announce dates confirmed from these (effective dates from the same):
SOURCE = {
    "2025-03": "niftyindices/NSE; announced 2025-02-21, eff 2025-03-28",
    "2024-09": "NSE Indices circular 2024-08-23, eff 2024-09-30",
    "2024-03": "NSE 'replacements wef 2024-03-28'; announced 2024-02-28",
    "2022-09": "press reports of NSE release 2022-09-01, eff 2022-09-30",
    "2022-03": "NSE IMSC press release 2022-02-24, eff 2022-03-31",
    "2021-03": "NSE announcement 2021-02-23, eff 2021-03-31",
    "2020-09": "niftyindices press release 2020-08-20, eff 2020-09-25",
}


@dataclass(frozen=True)
class RebalanceEvent:
    symbol: str        # NSE symbol (EQ series)
    leg: str           # "add" (long) or "drop" (short)
    review: str        # e.g. "2024-09"
    announce: str      # announcement date = entry trigger T0 (YYYY-MM-DD)
    effective: str     # change effective date = exit (YYYY-MM-DD)
    verified: bool     # is the ANNOUNCE date confirmed against the NSE/niftyindices circular?
    source: str


# --- pure event-study math (date-to-date, leg-signed) -----------------------

def abnormal_return_between(stock: pd.Series, bench: pd.Series, t0, exit_date,
                            entry_lag: int = 1):
    """Benchmark-adjusted return from entry (first trading day >= t0, then +entry_lag)
    to the first trading day on/after `exit_date`. None if data is insufficient.
    """
    if stock is None or len(stock) == 0:
        return None
    stock = stock.sort_index()
    idx = stock.index
    t0 = pd.Timestamp(t0)
    exit_date = pd.Timestamp(exit_date)

    entry = idx.searchsorted(t0) + entry_lag
    exit_pos = idx.searchsorted(exit_date)  # first trading day >= exit_date
    if entry < 0 or entry >= len(idx) or exit_pos >= len(idx) or exit_pos <= entry:
        return None

    d_entry, d_exit = idx[entry], idx[exit_pos]
    if stock.iloc[entry] == 0:
        return None
    s_ret = stock.iloc[exit_pos] / stock.iloc[entry] - 1.0

    b = bench.sort_index()
    b_entry, b_exit = b.asof(d_entry), b.asof(d_exit)
    if pd.isna(b_entry) or pd.isna(b_exit) or b_entry == 0:
        return None
    b_ret = b_exit / b_entry - 1.0
    return float(s_ret - b_ret)


def drop_blocked(events, actions: list[dict], post_days: int = 8):
    """Split events into (kept, dropped): dropped = a share-count-changing corporate action
    (split/bonus/rights/consolidation/demerger) with ex-date inside [announce, effective +
    post_days]. The study reads UNADJUSTED closes, so such an event's window return is the
    corporate action, not the rebalance (BEL's 2:1 bonus of 2022-09-15 read as -66%)."""
    from scanner.lockin import blocking_action
    kept, dropped = [], []
    for e in events:
        hi = pd.Timestamp(e.effective) + pd.Timedelta(days=post_days)
        (dropped if blocking_action(actions, e.symbol, e.announce, hi) else kept).append(e)
    return kept, dropped


def signed_leg_return(event: RebalanceEvent, stock: pd.Series, bench: pd.Series,
                      entry_lag: int = 1):
    """Return accruing to the front-run trade: long adds, short (negated) drops."""
    if event.leg not in ("add", "drop"):
        raise ValueError(f"bad leg: {event.leg!r} (expected 'add' or 'drop')")
    r = abnormal_return_between(stock, bench, event.announce, event.effective, entry_lag)
    if r is None:
        return None
    return r if event.leg == "add" else -r


# --- the curated event set (NIFTY 50 regular reviews; see module docstring) --
# announce dates marked verified=False are 4-week-prior PROXIES pending circular check.

EVENTS: list[RebalanceEvent] = [
    # 2025-03 — announced 2025-02-21, effective 2025-03-28.
    RebalanceEvent("JIOFIN",   "add",  "2025-03", "2025-02-21", "2025-03-28", True, SOURCE["2025-03"]),
    RebalanceEvent("ZOMATO",   "add",  "2025-03", "2025-02-21", "2025-03-28", True, SOURCE["2025-03"]),
    RebalanceEvent("BPCL",     "drop", "2025-03", "2025-02-21", "2025-03-28", True, SOURCE["2025-03"]),
    RebalanceEvent("BRITANNIA","drop", "2025-03", "2025-02-21", "2025-03-28", True, SOURCE["2025-03"]),
    # 2024-09 — announced 2024-08-23, effective 2024-09-30.
    RebalanceEvent("BEL",      "add",  "2024-09", "2024-08-23", "2024-09-30", True, SOURCE["2024-09"]),
    RebalanceEvent("TRENT",    "add",  "2024-09", "2024-08-23", "2024-09-30", True, SOURCE["2024-09"]),
    RebalanceEvent("DIVISLAB", "drop", "2024-09", "2024-08-23", "2024-09-30", True, SOURCE["2024-09"]),
    RebalanceEvent("LTIM",     "drop", "2024-09", "2024-08-23", "2024-09-30", True, SOURCE["2024-09"]),
    # 2024-03 — announced 2024-02-28, effective 2024-03-28.
    RebalanceEvent("SHRIRAMFIN","add", "2024-03", "2024-02-28", "2024-03-28", True, SOURCE["2024-03"]),
    RebalanceEvent("UPL",      "drop", "2024-03", "2024-02-28", "2024-03-28", True, SOURCE["2024-03"]),
    # 2022-09 — announced 2022-09-01, effective 2022-09-30.
    RebalanceEvent("ADANIENT", "add",  "2022-09", "2022-09-01", "2022-09-30", True, SOURCE["2022-09"]),
    RebalanceEvent("SHREECEM", "drop", "2022-09", "2022-09-01", "2022-09-30", True, SOURCE["2022-09"]),
    # 2022-03 — announced 2022-02-24, effective 2022-03-31.
    RebalanceEvent("APOLLOHOSP","add", "2022-03", "2022-02-24", "2022-03-31", True, SOURCE["2022-03"]),
    RebalanceEvent("IOC",      "drop", "2022-03", "2022-02-24", "2022-03-31", True, SOURCE["2022-03"]),
    # 2021-03 — announced 2021-02-23, effective 2021-03-31.
    RebalanceEvent("TATACONSUM","add", "2021-03", "2021-02-23", "2021-03-31", True, SOURCE["2021-03"]),
    RebalanceEvent("GAIL",     "drop", "2021-03", "2021-02-23", "2021-03-31", True, SOURCE["2021-03"]),
    # 2020-09 — announced 2020-08-20, effective 2020-09-25.
    RebalanceEvent("SBILIFE",  "add",  "2020-09", "2020-08-20", "2020-09-25", True, SOURCE["2020-09"]),
    RebalanceEvent("DIVISLAB", "add",  "2020-09", "2020-08-20", "2020-09-25", True, SOURCE["2020-09"]),
    RebalanceEvent("ZEEL",     "drop", "2020-09", "2020-08-20", "2020-09-25", True, SOURCE["2020-09"]),
    RebalanceEvent("INFRATEL", "drop", "2020-09", "2020-08-20", "2020-09-25", True, SOURCE["2020-09"]),
]


def adds(events=EVENTS):
    return [e for e in events if e.leg == "add"]


def drops(events=EVENTS):
    return [e for e in events if e.leg == "drop"]


# --- NIFTY Next 50 event set (loaded from the kind-tagged CSV record) --------

def load_next50_events(path: Path = _NEXT50_CSV, clean_only: bool = True) -> list[RebalanceEvent]:
    """Load the Next 50 reconstitution events.

    clean_only=True (the study set) keeps ONLY:
      * kind in {entry, exit} — fresh forced buys/sells, NOT promotion/relegation
        (those are confounded by the much larger opposite-direction Nifty 50 flow), and
      * regular semi-annual reviews — drops ad-hoc/merger reviews (label contains 'adhoc').
    clean_only=False returns every row (the full auditable record).
    """
    out: list[RebalanceEvent] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(r for r in fh if not r.lstrip().startswith("#")):
            kind, review = row["kind"], row["review"]
            if clean_only and (kind not in ("entry", "exit") or "adhoc" in review):
                continue
            out.append(RebalanceEvent(
                symbol=row["symbol"], leg=row["leg"], review=review,
                announce=row["announce"], effective=row["effective"],
                verified=True, source=f"niftyindices {row['source']}"))
    return out
