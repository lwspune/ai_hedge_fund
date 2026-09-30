"""The market-regime loader's run guards (scripts/refresh_regime.py): a stale benchmark, a thin
universe, a mass of break exclusions or a blank breadth on the last date fail the daily job."""
from datetime import date

from scripts.refresh_regime import MAX_EXCLUDED, MIN_UNIVERSE, run_failures


def _row(**k):
    r = {"trade_date": "2026-09-30", "n_universe": 1400, "n_excluded": 30, "pct_above_200": 0.4}
    return {**r, **k}


def test_guard_constants():
    assert MIN_UNIVERSE == 800 and MAX_EXCLUDED == 0.10


def test_run_failures():
    bench = date(2026, 9, 30)
    assert run_failures([_row()], bench) == []
    assert any("benchmark" in f for f in run_failures([_row(trade_date="2026-09-29")], bench))
    assert any("benchmark" in f for f in run_failures([_row()], None))
    assert any("universe" in f for f in run_failures([_row(n_universe=799)], bench))
    assert any("excluded" in f for f in run_failures([_row(n_universe=900, n_excluded=101)], bench))
    assert run_failures([_row(n_universe=900, n_excluded=100)], bench) == []     # exactly 10%: ok
    assert any("pct_above_200" in f for f in run_failures([_row(pct_above_200=None)], bench))
    assert run_failures([], bench) == ["no rows computed"]
