"""Test-first spec for the index-rebalance leg math.

The new pure logic vs the existing event study:
  * exit on a *specific date* (the effective date), not a fixed horizon, and
  * sign the return by leg: long the additions, short the deletions.
"""
import pandas as pd
import pytest

from scanner.rebalance import (
    RebalanceEvent,
    abnormal_return_between,
    signed_leg_return,
)


def _series(values, start="2025-01-01"):
    idx = pd.bdate_range(start=start, periods=len(values))
    return pd.Series(values, index=idx, dtype="float64")


def test_drop_blocked_removes_events_with_a_corporate_action_inside_the_window():
    # BEL's 2:1 bonus (2022-09-15) sat inside its Sep-2022 Next-50 add window and read as a
    # -66% "return" on unadjusted closes. Any split/bonus/rights/demerger between the
    # announcement and effective+post window disqualifies the event.
    from scanner.rebalance import drop_blocked
    evs = [RebalanceEvent("BEL", "add", "2022-09", "2022-09-01", "2022-09-30", True, "x"),
           RebalanceEvent("ABC", "add", "2022-09", "2022-09-01", "2022-09-30", True, "x"),
           RebalanceEvent("BEL", "drop", "2021-03", "2021-02-23", "2021-03-31", True, "x")]
    acts = [{"symbol": "BEL", "event_type": "bonus", "event_date": "2022-09-15"},
            {"symbol": "ABC", "event_type": "dividend", "event_date": "2022-09-15"},   # not blocking
            {"symbol": "BEL", "event_type": "split", "event_date": "2021-04-05"}]       # inside post +8d
    kept, dropped = drop_blocked(evs, acts, post_days=8)
    assert [e.symbol + e.review for e in kept] == ["ABC2022-09"]
    assert {(e.symbol, e.review) for e in dropped} == {("BEL", "2022-09"), ("BEL", "2021-03")}


def test_abnormal_between_two_dates():
    # bdate idx: 0=Jan1(Wed) 1=Jan2 2=Jan3 3=Jan6 4=Jan7 ...
    # entry = announce(Jan1)+1 = Jan2 (100); exit on/after Jan6 = Jan6 (110) -> +10%
    stock = _series([100, 100, 105, 110] + [110] * 6)
    bench = _series([200, 200, 204, 208] + [208] * 6)  # 200 (Jan2) -> 208 (Jan6) = +4%
    car = abnormal_return_between(stock, bench, "2025-01-01", "2025-01-06", entry_lag=1)
    assert car == pytest.approx(0.10 - 0.04, abs=1e-9)


def test_abnormal_between_uses_first_trading_day_on_or_after_exit():
    # exit_date falls on a weekend (Jan 4 = Sat) -> must roll to Jan 6.
    stock = _series([100, 100, 105, 120] + [120] * 6)
    bench = _series([200, 200, 204, 200] + [200] * 6)  # bench flat 200->200
    car = abnormal_return_between(stock, bench, "2025-01-01", "2025-01-04", entry_lag=1)
    assert car == pytest.approx(0.20, abs=1e-9)  # exit rolled forward to Jan6 = 120


def test_abnormal_between_none_when_exit_past_series():
    stock = _series([100, 101, 102])
    bench = _series([200, 201, 202])
    assert abnormal_return_between(stock, bench, "2025-01-01", "2025-06-01") is None


def test_signed_leg_return_long_for_add():
    stock = _series([100, 100, 110] + [110] * 6)
    bench = _series([200, 200, 200] + [200] * 6)
    ev = RebalanceEvent("X", "add", "2025-09", "2025-01-01", "2025-01-03", True, "src")
    assert signed_leg_return(ev, stock, bench) == pytest.approx(0.10, abs=1e-9)


def test_signed_leg_return_short_for_drop():
    # A dropped stock that FALLS 10% is a +10% gain to the short front-run trade.
    stock = _series([100, 100, 90] + [90] * 6)
    bench = _series([200, 200, 200] + [200] * 6)
    ev = RebalanceEvent("Y", "drop", "2025-09", "2025-01-01", "2025-01-03", True, "src")
    assert signed_leg_return(ev, stock, bench) == pytest.approx(0.10, abs=1e-9)


def test_signed_leg_return_none_propagates():
    stock = _series([100, 101, 102])
    bench = _series([200, 201, 202])
    ev = RebalanceEvent("Z", "add", "2025-09", "2025-01-01", "2025-06-01", True, "src")
    assert signed_leg_return(ev, stock, bench) is None


def test_bad_leg_rejected():
    ev = RebalanceEvent("Q", "sideways", "2025-09", "2025-01-01", "2025-01-03", True, "src")
    stock = _series([100, 100, 110, 110, 110])
    bench = _series([200, 200, 200, 200, 200])
    with pytest.raises(ValueError):
        signed_leg_return(ev, stock, bench)
