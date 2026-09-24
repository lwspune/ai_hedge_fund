"""Shared plumbing for `scripts/validate_*.py` (DATA_INFRA_SPEC WP6/WP7).

Every validation accepts `--exclude-results-window N`: drop events within N trading days
(either side) of a quarterly-results board meeting for the same symbol — a contamination
control, since results days move prices for reasons unrelated to the signal. Results dates
come from `corporate_events` (event_type 'results', source nse_bm; 2020->).

    python scripts/validate_fno_ban.py --exclude-results-window 2
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd


def parse_args(argv=None, known_only: bool = False):
    ap = argparse.ArgumentParser(add_help=not known_only)
    ap.add_argument("--exclude-results-window", type=int, default=0, metavar="N",
                    help="drop events within N trading days of a results meeting (same symbol)")
    return ap.parse_known_args(argv) if known_only else ap.parse_args(argv)


def drop_near_results(df: pd.DataFrame, date_col: str, n: int, results: dict, hol) -> pd.DataFrame:
    """Rows of `df` whose event date is more than `n` trading days from every results date of
    the same symbol. results: {symbol: [date, ...]}. n <= 0 returns df unchanged."""
    if n <= 0 or df.empty:
        return df
    from scanner.trading_calendar import trading_days_between

    def near(row) -> bool:
        d = pd.Timestamp(row[date_col]).date()
        return any(abs(trading_days_between(d, r, hol)) <= n for r in results.get(row["symbol"], ()))

    keep = ~df.apply(near, axis=1)
    return df[keep.astype(bool)]


def load_results() -> dict:
    """{symbol: [results dates]} from corporate_events."""
    from scanner import db
    rows = db.select_all("corporate_events", {"select": "symbol,event_date",
                                              "event_type": "eq.results", "order": "event_date"})
    out: dict = {}
    for r in rows:
        out.setdefault(r["symbol"], []).append(date.fromisoformat(r["event_date"]))
    return out


def exclude_results(df: pd.DataFrame, date_col: str, n: int) -> pd.DataFrame:
    """drop_near_results with results + holidays loaded from Supabase; prints what it dropped."""
    if n <= 0 or df.empty:
        return df
    from scanner.trading_calendar import holidays
    out = drop_near_results(df, date_col, n, load_results(), holidays())
    print(f"results-window control: dropped {len(df) - len(out)} of {len(df)} events "
          f"within {n} trading days of a results meeting", flush=True)
    return out
