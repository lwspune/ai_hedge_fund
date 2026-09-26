"""Test-first spec for price-consolidation detection (scanner/consolidation.py): a 40-session range
<= 10% of price on a liquid stock, and the first close outside it."""
import numpy as np
import pandas as pd
import pytest

from scanner.consolidation import breakout_events, current_state

N = 40


def _frame(closes, spread=0.01, turnover=500.0, volume=1e5):
    """Daily bars: high/low = close * (1 +/- spread), turnover in lakh."""
    c = np.asarray(closes, dtype=float)
    idx = pd.bdate_range("2024-01-01", periods=len(c))
    return pd.DataFrame({"close": c, "high": c * (1 + spread), "low": c * (1 - spread),
                         "volume": volume, "turnover_lakh": turnover, "delivery_pct": 50.0}, index=idx)


def _base(n=N, level=100.0, wiggle=0.02):
    return [level * (1 + wiggle * np.sin(i)) for i in range(n)]


def test_up_breakout_from_a_tight_range():
    df = _frame(list(np.linspace(60, 98, 60)) + _base() + [110.0])   # a rally, a 40-day base, a close above it
    ev = [e for e in breakout_events(df, "ABC") if e["tight"]]
    assert len(ev) == 1
    e = ev[0]
    assert e["direction"] == "up" and e["tight"] is True and e["date"] == df.index[-1]
    assert e["range_pct"] <= 0.10 and e["days_in_range"] >= N
    assert e["prior_move"] == pytest.approx(100 / 60 - 1)   # base start vs 60 sessions earlier


def test_down_breakout():
    ev = breakout_events(_frame(_base() + [90.0]), "ABC")
    assert [(e["direction"], e["tight"]) for e in ev] == [("down", True)]


def test_illiquid_stocks_are_not_consolidating():
    assert breakout_events(_frame(_base() + [110.0], turnover=50.0), "ABC") == []   # Rs 0.5 cr / day


def test_a_wide_range_breakout_is_the_control_not_an_event():
    wide = [100.0 * (1 + 0.12 * np.sin(i)) for i in range(N)]
    ev = breakout_events(_frame(wide + [120.0]), "ABC")
    assert [(e["direction"], e["tight"]) for e in ev] == [("up", False)]


def test_one_event_per_cooldown():
    closes = _base() + [110.0, 111.0, 112.0] + [111.5] * 10 + [125.0]
    ev = [e for e in breakout_events(_frame(closes), "ABC") if e["tight"]]
    assert len(ev) == 1


def test_breakout_volume_ratio():
    df = _frame(_base() + [110.0])
    df.iloc[-1, df.columns.get_loc("volume")] = 3e5
    assert breakout_events(df, "ABC")[0]["vol_ratio"] == pytest.approx(3.0)


def test_current_state_for_the_scanner():
    s = current_state(_frame(_base()), "ABC")
    assert s["in_range"] is True and s["range_pct"] <= 0.10 and s["days_in_range"] >= 1
    assert 0.0 <= s["position"] <= 1.0
    assert current_state(_frame([100.0 * (1 + 0.2 * np.sin(i)) for i in range(N)]), "ABC")["in_range"] is False
    assert current_state(_frame([100.0] * 10), "ABC") is None                       # too short


def test_scan_now_lists_ranges_and_todays_breakouts():
    from scanner.consolidation import consolidation_candidates, scan_now
    panel = {"RANGE": _frame(_base(60)), "BREAK": _frame(_base(60) + [110.0]),
             "WILD": _frame([100.0 * (1 + 0.2 * np.sin(i)) for i in range(60)]),
             "SHORT": _frame([100.0] * 10), "THIN": _frame(_base(60), turnover=20.0)}
    rows = scan_now(panel)
    kinds = {(r["symbol"], r["status"]) for r in rows}
    assert kinds == {("RANGE", "in range"), ("BREAK", "breakout up")}
    c = {x["symbol"]: x for x in consolidation_candidates(rows)}
    assert c["BREAK"]["payload"]["status"] == "breakout up" and 0 < c["RANGE"]["score"] <= 0.10


def test_scan_now_keeps_to_the_company_universe():
    from scanner.consolidation import scan_now
    # a liquid-fund ETF sits in a sub-1% range forever: not a company, not a consolidation
    panel = {"LIQUIDBEES": _frame([1000.0 + 0.01 * i for i in range(60)], spread=0.001), "RANGE": _frame(_base(60))}
    assert {r["symbol"] for r in scan_now(panel, universe={"RANGE"})} == {"RANGE"}
