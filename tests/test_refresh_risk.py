"""The risk-lens loader's run guards (scripts/refresh_risk.py): a thin run, a mass of unverified
corporate actions or a stale benchmark fails the daily job rather than writing wrong numbers."""
from datetime import date

from scripts.refresh_risk import MAX_UNVERIFIED, MIN_ROWS, benchmark_stale, missing_sessions, run_failures


def _rows(n, unverified=0):
    return [{"symbol": f"S{i}", "flags": ["action_unverified"] if i < unverified else []} for i in range(n)]


def test_guard_constants():
    assert MIN_ROWS == 1500 and MAX_UNVERIFIED == 0.20


def test_run_failures():
    assert run_failures(_rows(2000, unverified=100)) == []
    assert any("rows" in f for f in run_failures(_rows(1499)))
    assert any("action_unverified" in f for f in run_failures(_rows(2000, unverified=401)))
    assert run_failures(_rows(2000, unverified=400)) == []          # exactly 20%: ok
    breaks = [{"symbol": f"B{i}", "flags": ["price_break"]} for i in range(300)]
    assert any("price_break" in f for f in run_failures(_rows(1800, unverified=200) + breaks))


def test_benchmark_stale_counts_trading_days():
    hol = frozenset()
    today = date(2026, 9, 30)                                       # Wednesday
    assert benchmark_stale(None, today, hol)
    assert not benchmark_stale(date(2026, 9, 30), today, hol)
    assert not benchmark_stale(date(2026, 9, 25), today, hol)       # Fri -> Wed = 3 trading days
    assert benchmark_stale(date(2026, 9, 24), today, hol)           # 4 trading days


def test_missing_sessions_lists_trading_days_the_benchmark_lacks():
    """The 2026-09-01..09 store hole: a multi-day move would read as one session."""
    hol = frozenset({date(2026, 9, 14)})                            # Ganesh Chaturthi
    have = [date(2026, 8, 31), date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 15)]
    gap = missing_sessions(have, date(2026, 8, 31), date(2026, 9, 15), hol)
    assert gap == [date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8, 9)]
    assert missing_sessions(have[1:], date(2026, 9, 10), date(2026, 9, 15), hol) == []
