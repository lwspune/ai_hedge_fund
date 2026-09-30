"""Test-first spec for the market regime view (scanner/regime.py, docs/REGIME_VIEW_SPEC.md §2-3): index
drawdown / returns / volatility with a point-in-time percentile, and breadth over liquid mainboard stocks
with break-aware adjustment. Measurements, not a signal. Synthetic data only, no network."""
import json
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from scanner import regime
from scanner.regime import (adjust_segments, breadth, format_table, index_metrics, regime_rows,
                            stock_states, vol_percentile)


def _series(values, start="2024-01-01"):
    return pd.Series(np.asarray(values, dtype=float), index=pd.bdate_range(start, periods=len(values)))


def _bars(closes: pd.Series, turnover=500.0, series="EQ"):
    t = turnover if np.ndim(turnover) else [turnover] * len(closes)
    return pd.DataFrame({"close": closes.values, "turnover_lakh": np.asarray(t, dtype=float),
                         "series": series}, index=closes.index)


DAILY_SESSIONS = 355              # ~ LOOKBACK_DAYS = 520 calendar days of sessions


def _walk(n, seed=3, level=100.0):
    r = np.random.default_rng(seed).normal(0.0003, 0.01, n - 1)
    return _series(level * np.exp(np.concatenate([[0.0], np.cumsum(r)])))


# --- constants ------------------------------------------------------------------

def test_constants_pinned():
    assert regime.START == date(2020, 1, 1)
    assert (regime.DMA_LONG, regime.DMA_SHORT, regime.HIGH_LOW) == (200, 50, 250)
    assert (regime.VOL_WINDOW, regime.VOL_PCT_MIN) == (20, 250)
    assert regime.MAINBOARD == ("EQ", "BE", "BZ")
    assert regime.LOOKBACK_DAYS == 520 and regime.RECOMPUTE_SESSIONS == 10
    assert regime.MAX_GAP_RESET == 20
    assert (regime.REGULAR_SESSIONS, regime.REGULAR_MIN_PRINTS) == (250, 200)   # printed on >= 80% of sessions


# --- index block ------------------------------------------------------------------

def test_index_drawdown_both_indices():
    n500 = _series([100, 120, 90, 110])
    n50 = _series([50, 50, 60, 30])
    m = index_metrics(n500, n50)
    assert list(m["n500_close"]) == [100, 120, 90, 110]
    assert list(m["n500_dd"].round(6)) == [0.0, 0.0, -0.25, round(110 / 120 - 1, 6)]
    assert list(m["n50_dd"]) == [0.0, 0.0, 0.0, -0.5]


def test_index_trailing_returns_and_vol_need_history():
    n500 = _series(np.arange(1, 65, dtype=float))            # 64 prints
    m = index_metrics(n500, n500)
    assert m["n500_ret_1m"].iloc[-1] == pytest.approx(64 / 43 - 1)
    assert m["n500_ret_3m"].iloc[-1] == pytest.approx(64 / 1 - 1)
    assert pd.isna(m["n500_ret_3m"].iloc[-2])                  # 63 prints: no 63-session return yet
    assert m["n500_vol_20"].iloc[:20].isna().all()             # 20 returns need 21 prints
    assert m["n500_vol_20"].iloc[20] > 0


def test_index_metrics_align_nifty50_on_nifty500_dates():
    n500 = _series([100, 101, 102])
    n50 = _series([10, 11])                                    # one day short
    m = index_metrics(n500, n50)
    assert len(m) == 3 and pd.isna(m["n50_dd"].iloc[-1])


def test_vol_percentile_is_point_in_time():
    vol = _series(np.random.default_rng(5).uniform(0.1, 0.3, 300))
    pct = vol_percentile(vol)
    assert pct.iloc[:249].isna().all() and pct.iloc[249:].notna().all()
    later = pd.concat([vol, _series([9.9], start=vol.index[-1] + pd.offsets.BDay())])
    assert vol_percentile(later).iloc[:300].equals(pct)        # a later value never rewrites the past
    up = vol_percentile(_series(np.arange(1, 251, dtype=float)))
    assert up.iloc[-1] == pytest.approx(100.0)                 # the 250th value is the highest of 250
    down = vol_percentile(_series(np.arange(250, 0, -1, dtype=float)))
    assert down.iloc[-1] == pytest.approx(0.0)
    lead = pd.concat([_series([np.nan] * 5), _series(np.arange(1, 251, dtype=float), start="2025-06-02")])
    assert vol_percentile(lead).iloc[-1] == pytest.approx(100.0)   # leading NaNs don't count toward 250


# --- adjusted segments --------------------------------------------------------------

_SPLIT = {"event_type": "split", "details": {"from_fv": 10.0, "to_fv": 2.0}}   # x0.2
_BONUS = {"event_type": "bonus", "details": {"ratio": "1:1"}}                  # x0.5


def _on(a, d):
    return {**a, "event_date": pd.Timestamp(d).date().isoformat()}


def test_adjust_segments_applies_a_confirmed_split():
    s = _series([1000, 1010, 202, 204])
    adj, breaks = adjust_segments(s, [_on(_SPLIT, s.index[2])])
    assert list(adj.round(2)) == [200.0, 202.0, 202.0, 204.0] and breaks == []


def test_adjust_segments_keeps_the_series_past_an_unconfirmed_action():
    s = _series([300, 300, 301, 299, 300, 60, 61, 62])
    adj, breaks = adjust_segments(s, [_on(_BONUS, s.index[2]), _on(_SPLIT, s.index[5])])
    assert breaks == [s.index[2]]                              # bonus not in the prices: a break, not applied
    assert list(adj.round(2)) == [60.0, 60.0, 60.2, 59.8, 60.0, 60.0, 61.0, 62.0]   # the split still applied


def test_adjust_segments_flags_unexplained_jumps_and_demergers():
    s = _series([100, 101, 50, 51, 52, 53])
    adj, breaks = adjust_segments(s, [])
    assert breaks == [s.index[2]] and list(adj) == list(s)     # a -50% day nothing explains
    dem = {"event_type": "demerger", "event_date": s.index[4].date().isoformat(), "details": {}}
    assert adjust_segments(_series([100, 101, 102, 103, 95, 96]), [dem])[1] == [s.index[4]]


def test_adjust_segments_same_date_split_and_bonus_is_one_jump():
    s = _series([1000, 1010, 101, 102])
    adj, breaks = adjust_segments(s, [_on(_SPLIT, s.index[2]), _on(_BONUS, s.index[2])])
    assert breaks == [] and list(adj.round(2)) == [100.0, 101.0, 101.0, 102.0]


# --- per-stock states ---------------------------------------------------------------

def test_sme_series_is_never_eligible():
    st = stock_states(_bars(_walk(300), series="SM"), [])
    assert not st["eligible"].any() and not st["excluded"].any()


def test_eligible_from_the_200th_print():
    st = stock_states(_bars(_walk(300)), [])
    assert not st["eligible"].iloc[198] and st["eligible"].iloc[199]


def test_liquidity_is_measured_as_of_each_date():
    turnover = [90.0] * 250 + [150.0] * 50                     # becomes liquid late
    st = stock_states(_bars(_walk(300), turnover=turnover), [])
    assert not st["eligible"].iloc[258] and st["eligible"].iloc[259]   # 10 of the last 20 at 150 -> median 120


def test_a_break_excludes_the_next_250_prints_only():
    s = _walk(600)
    s.iloc[300:] = s.iloc[300:] / 2                            # an unrecorded 1:1 bonus at print 300
    st = stock_states(_bars(s), [])
    assert st["excluded"].iloc[300] and st["excluded"].iloc[549]
    assert not st["excluded"].iloc[550] and st["eligible"].iloc[550]
    assert not st["excluded"].iloc[299] and st["eligible"].iloc[299]
    assert not (st["eligible"] & st["excluded"]).any()


def test_dma_and_high_low_flags():
    s = _series([100.0] * 200 + [101.0])
    st = stock_states(_bars(s), [])
    assert not st["above_200"].iloc[199] and st["above_200"].iloc[200]   # equal to the mean is not above
    assert st["above_50"].iloc[200]
    up = stock_states(_bars(_series(np.linspace(100, 200, 260))), [])
    assert not up["new_high"].iloc[248] and up["new_high"].iloc[249]     # needs 250 prints
    assert not up["new_low"].iloc[259]
    down = stock_states(_bars(_series(np.linspace(200, 100, 260))), [])
    assert down["new_low"].iloc[259] and not down["new_high"].iloc[259]


def test_move_is_blank_across_a_long_gap():
    s = _series([100.0, 101.0, 100.0, 100.0, 102.0])
    sessions = pd.bdate_range(s.index[0], periods=20)
    gapped = pd.concat([s.iloc[:4], pd.Series([103.0], index=[sessions[12]])])  # 8 sessions unprinted
    st = stock_states(_bars(gapped), [], sessions=sessions)
    assert list(st["move"].iloc[1:4]) == [1.0, -1.0, 0.0]
    assert math.isnan(st["move"].iloc[0]) and math.isnan(st["move"].iloc[4])


def test_stock_states_propagates_a_corrupt_store():
    from scanner.pricestore import BadPriceData
    bad = pd.Series([100.0, 101.0], index=pd.DatetimeIndex(["1970-01-01", "1970-01-02"]))
    with pytest.raises(BadPriceData):
        stock_states(_bars(bad), [])


# --- breadth ------------------------------------------------------------------------

def _state(rows, dates):
    cols = ["eligible", "excluded", "above_200", "above_50", "new_high", "new_low", "move"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows], index=pd.DatetimeIndex(dates))


def test_breadth_aggregates_the_eligible_universe():
    d = ["2026-09-28", "2026-09-29", "2026-09-30"]
    states = {
        "A": _state([(True, False, True, True, True, False, 1.0), (True, False, True, True, False, False, 0.0)], d[:2]),
        "B": _state([(True, False, False, True, False, True, -1.0), (True, False, False, False, False, False, 1.0)], d[:2]),
        "C": _state([(False, True, True, True, True, False, 1.0), (False, True, True, True, True, False, 1.0),
                     (False, False, True, True, True, False, 1.0)], d),
    }
    b = breadth(states)
    r1, r2, r3 = (b.loc[pd.Timestamp(x)] for x in d)
    assert (r1["n_universe"], r1["n_excluded"]) == (2, 1)
    assert (r1["pct_above_200"], r1["pct_above_50"], r1["up_share"]) == (0.5, 1.0, 0.5)
    assert (r1["new_highs"], r1["new_lows"]) == (1, 1)
    assert r2["up_share"] == 1.0                               # unchanged counts as neither
    assert r3["n_universe"] == 0 and r3["n_excluded"] == 0
    assert pd.isna(r3["pct_above_200"]) and pd.isna(r3["up_share"]) and r3["new_highs"] == 0


# --- DB boundary and print -----------------------------------------------------------

def test_regime_rows_are_db_safe_and_filtered():
    idx = pd.DatetimeIndex(["2026-09-29", "2026-09-30"])
    index_df = pd.DataFrame({"n500_close": [24000.123, 24100.0], "n500_dd": [-0.05, float("nan")],
                             "n50_dd": [-0.04, -0.03], "n500_ret_1m": [0.01, float("inf")],
                             "n500_ret_3m": [0.02, 0.03], "n500_vol_20": [0.15, 0.16],
                             "n500_vol_pct": [np.nan, 72.456]}, index=idx)
    breadth_df = pd.DataFrame({"pct_above_200": [0.38, 0.4], "pct_above_50": [0.5, 0.52],
                               "new_highs": [np.int64(12), 13], "new_lows": [45, 40], "up_share": [0.6, None],
                               "n_universe": [1400, 1401], "n_excluded": [20, 21]}, index=idx[1:2].append(idx[:1]))
    rows = regime_rows(index_df, breadth_df)
    json.dumps(rows)
    assert [r["trade_date"] for r in rows] == ["2026-09-29", "2026-09-30"]
    r = rows[1]
    assert r["n500_dd"] is None and r["n500_ret_1m"] is None and r["n500_vol_pct"] == pytest.approx(72.456, abs=1e-3)
    assert r["new_highs"] == 12 and type(r["new_highs"]) is int and r["pct_above_200"] == pytest.approx(0.38)
    assert rows[0]["up_share"] is None
    assert [x["trade_date"] for x in regime_rows(index_df, breadth_df, since=date(2026, 9, 30))] == ["2026-09-30"]


def test_format_table_handles_blanks():
    out = format_table([{"trade_date": "2026-09-30", "n500_dd": None, "n500_vol_20": 0.16, "n500_vol_pct": None,
                         "pct_above_200": 0.38, "pct_above_50": None, "new_highs": 12, "new_lows": None,
                         "up_share": 0.6, "n_universe": 1400, "n_excluded": 20}])
    assert "2026-09-30" in out and "38" in out



# --- suspensions: a long gap starts a new segment ------------------------------------------

def _suspended(pre=300, gap=40, post=260, jump=0.4):
    """`pre` prints, a `gap`-session suspension, `post` prints resuming at (1 - jump) x the last price."""
    sessions = pd.bdate_range("2023-01-02", periods=pre + gap + post)
    a = _walk(pre, seed=11).to_numpy()
    b = _walk(post, seed=12).to_numpy() / 100 * a[-1] * (1 - jump)
    idx = sessions[:pre].append(sessions[pre + gap:])
    return pd.Series(np.concatenate([a, b]), index=idx), sessions


def test_a_suspension_restarts_the_print_count():
    s, sessions = _suspended()
    st = stock_states(_bars(s), [], sessions=sessions)
    assert st["eligible"].iloc[299]                            # eligible before the suspension
    assert not st["eligible"].iloc[300] and not st["excluded"].iloc[300]   # resumption: history restarts
    assert not st["eligible"].iloc[300 + 198] and st["eligible"].iloc[300 + 199]
    assert not st["excluded"].any()                            # the jump across the gap is not a break


def test_daily_window_agrees_with_the_full_history():
    """The daily run recomputes the last sessions from a ~285-print panel; the rebuild from 2020. Same answer."""
    s, sessions = _suspended(pre=500, gap=100, post=230)       # the suspension starts before the daily window
    full = stock_states(_bars(s), [], sessions=sessions)
    tail_sessions = sessions[-DAILY_SESSIONS:]
    short = stock_states(_bars(s[s.index >= tail_sessions[0]]), [], sessions=tail_sessions)
    cols = ["eligible", "excluded", "above_200", "above_50", "new_high", "new_low"]
    assert full[cols].iloc[-10:].equals(short[cols].iloc[-10:])



def _intermittent(every, skip, n_sessions=900, seed=21):
    """A stock that skips `skip` of every `every` sessions (trade-for-trade / call auction pattern)."""
    sessions = pd.bdate_range("2023-01-02", periods=n_sessions)
    keep = [i for i in range(n_sessions) if i % every >= skip]
    c = _walk(len(keep), seed=seed)
    return pd.Series(c.to_numpy(), index=sessions[keep]), sessions


def test_intermittently_traded_stocks_are_out_of_the_universe():
    s, sessions = _intermittent(every=4, skip=1)               # prints on 75% of sessions
    st = stock_states(_bars(s), [], sessions=sessions)
    assert not st["eligible"].any() and not st["excluded"].any()
    s, sessions = _intermittent(every=10, skip=1)              # 90%: regular enough
    assert stock_states(_bars(s), [], sessions=sessions)["eligible"].iloc[-1]


def test_daily_window_agrees_for_a_regular_but_gappy_stock():
    s, sessions = _intermittent(every=6, skip=1)               # 83%: in the universe, 250 prints ~ 300 sessions
    s.iloc[-200:] = s.iloc[-200:] / 2                          # an unrecorded bonus 200 prints back
    full = stock_states(_bars(s), [], sessions=sessions)
    tail = sessions[-DAILY_SESSIONS:]
    short = stock_states(_bars(s[s.index >= tail[0]]), [], sessions=tail)
    cols = ["eligible", "excluded", "above_200", "above_50", "new_high", "new_low"]
    assert full[cols].iloc[-10:].equals(short[cols].iloc[-10:])
    assert full["excluded"].iloc[-1]
