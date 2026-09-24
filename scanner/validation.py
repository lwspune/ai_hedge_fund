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
from pathlib import Path

import pandas as pd


def parse_args(argv=None, known_only: bool = False):
    ap = argparse.ArgumentParser(add_help=not known_only)
    ap.add_argument("--exclude-results-window", type=int, default=0, metavar="N",
                    help="drop events within N trading days of a results meeting (same symbol)")
    ap.add_argument("--publish", action="store_true",
                    help="store results + report in the evidence bucket and validation_runs (WP7)")
    return ap.parse_known_args(argv) if known_only else ap.parse_args(argv)


class _Tee:
    """Mirror stdout into a buffer (the report as printed is part of the evidence)."""

    def __init__(self, stream):
        self.stream, self.parts = stream, []

    def write(self, s):
        self.parts.append(s)
        return self.stream.write(s)

    def flush(self):
        self.stream.flush()

    @property
    def text(self) -> str:
        return "".join(self.parts)


def run(signal: str, body, argv=None) -> None:
    """Shared entry point for scripts/validate_*.py. body(args) runs the study, prints its report
    and returns {name: DataFrame} (at least "results"). With --publish the frames and the printed
    report go to the evidence bucket + validation_runs; either way they print as before."""
    import inspect
    import sys
    from scanner import evidence
    args, _ = parse_args(sys.argv[1:] if argv is None else argv, known_only=True)
    tee, real = _Tee(sys.stdout), sys.stdout
    sys.stdout = tee
    try:
        frames = body(args) or {}
    finally:
        sys.stdout = real
    if args.publish:
        script = Path(inspect.stack()[1].filename).resolve()
        try:
            script = script.relative_to(Path(__file__).resolve().parent.parent).as_posix()
        except ValueError:
            script = script.name
        path = evidence.publish(signal, str(script), vars(args), frames, tee.text, git_sha=evidence.git_sha())
        print(f"\n[evidence] {path} (bucket `{evidence.BUCKET}`) + validation_runs row")


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
