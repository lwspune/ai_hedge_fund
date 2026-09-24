"""Shared validation-runner helpers (DATA_INFRA_SPEC WP6 results-window control)."""
from datetime import date

import pandas as pd

from scanner.validation import drop_near_results, parse_args

HOL = {date(2026, 10, 2)}


def _df():
    return pd.DataFrame({"symbol": ["A", "A", "B", "C"],
                         "date": ["2026-10-01", "2026-10-20", "2026-10-05", "2026-10-05"]})


def test_drop_near_results_trading_day_window_both_sides():
    results = {"A": [date(2026, 10, 5)], "B": [date(2026, 9, 28)]}
    # A 10-01 -> results 10-05 is 1 trading day later (Fri 2nd holiday): dropped at n=2
    # A 10-20 far; B 10-05 vs 09-28: 5 trading days before -> kept at n=2, dropped at n=5
    out = drop_near_results(_df(), "date", 2, results, HOL)
    assert list(zip(out.symbol, out.date)) == [("A", "2026-10-20"), ("B", "2026-10-05"), ("C", "2026-10-05")]
    out5 = drop_near_results(_df(), "date", 5, results, HOL)
    assert ("B", "2026-10-05") not in list(zip(out5.symbol, out5.date))


def test_drop_near_results_zero_window_is_noop():
    df = _df()
    assert drop_near_results(df, "date", 0, {"A": [date(2026, 10, 1)]}, HOL) is df


def test_drop_near_results_accepts_timestamps():
    df = pd.DataFrame({"symbol": ["A"], "d": [pd.Timestamp("2026-10-05")]})
    assert drop_near_results(df, "d", 1, {"A": [date(2026, 10, 5)]}, HOL).empty


def test_parse_args_results_window():
    assert parse_args([]).exclude_results_window == 0
    assert parse_args(["--exclude-results-window", "3"]).exclude_results_window == 3
    ns, rest = parse_args(["--nifty50", "--exclude-results-window", "2"], known_only=True)
    assert ns.exclude_results_window == 2 and rest == ["--nifty50"]
