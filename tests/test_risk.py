"""Test-first spec for the risk lens (scanner/risk.py, docs/RISK_LENS_SPEC.md §2-3): per-symbol
volatility, beta, drawdown, worst moves, trailing returns and liquidity on corporate-action-adjusted
closes. Measurements, not a signal. Synthetic data only, no network."""
import json
import math

import numpy as np
import pandas as pd
import pytest

from scanner import risk
from scanner.risk import (add_ranks, ann_vol, beta_stats, coverage, days_to_exit, drawdowns,
                          format_table, liquidity, log_returns, risk_row, symbol_metrics,
                          trailing_returns, worst_moves)


def _series(values, start="2025-01-01"):
    return pd.Series(np.asarray(values, dtype=float),
                     index=pd.bdate_range(start, periods=len(values)))


def _mkt(n=270, seed=7):
    """A benchmark close path and its daily log returns."""
    r = np.random.default_rng(seed).normal(0.0004, 0.01, n - 1)
    closes = _series(20000 * np.exp(np.concatenate([[0.0], np.cumsum(r)])))
    return closes


def _bars(closes: pd.Series, turnover=500.0, delivery=45.0):
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                         "volume": 1e5, "turnover_lakh": turnover, "delivery_pct": delivery},
                        index=closes.index)


def _levered(mkt: pd.Series, b=1.5, level=500.0):
    """Stock whose log returns are exactly b x the benchmark's."""
    lr = np.log(mkt / mkt.shift(1)).fillna(0.0)
    return pd.Series(level * np.exp(np.cumsum(b * lr.values)), index=mkt.index)


# --- constants ----------------------------------------------------------------

def test_constants_pinned():
    assert risk.WINDOW_DAYS == 400          # = daily_prices retention (refresh_prices.KEEP_DAYS)
    assert risk.POSITION_INR == 5e5
    assert risk.PARTICIPATION == 0.10
    assert (risk.MIN_SESSIONS_1Y, risk.MIN_SESSIONS_3M, risk.MIN_SESSIONS_LIQ) == (120, 60, 10)
    assert risk.SPARSE_COVERAGE == 0.80 and risk.ILLIQUID_ADV_CR == 1.0


# --- returns and volatility ---------------------------------------------------

def test_log_returns_doubling_then_halving():
    r = log_returns(_series([100, 200, 100]))
    assert list(r.round(12)) == [round(math.log(2), 12), round(-math.log(2), 12)]
    assert r.index[0] == pd.Timestamp("2025-01-02")


def test_ann_vol():
    assert ann_vol(_series([0.01] * 30)) == pytest.approx(0.0)
    r = _series([0.01, -0.02])
    assert ann_vol(r) == pytest.approx(np.std([0.01, -0.02], ddof=1) * math.sqrt(252))
    assert ann_vol(_series([0.01])) is None
    assert ann_vol(_series([])) is None
    # n = the last n returns only
    r = _series([0.5, -0.5] + [0.01, 0.02] * 10)
    assert ann_vol(r, n=20) == pytest.approx(np.std([0.01, 0.02] * 10, ddof=1) * math.sqrt(252))


def test_beta_stats_exact_multiple():
    r_m = _series(np.random.default_rng(1).normal(0, 0.01, 200))
    s = beta_stats(1.5 * r_m, r_m)
    assert s["beta"] == pytest.approx(1.5)
    assert s["corr"] == pytest.approx(1.0)
    assert s["idio_vol"] == pytest.approx(0.0, abs=1e-12)
    assert s["n_aligned"] == 200


def test_beta_stats_aligns_on_shared_dates_and_takes_last_n():
    r_m = _series(np.random.default_rng(2).normal(0, 0.01, 300))
    r_s = (2.0 * r_m).drop(r_m.index[10:40])          # the stock skipped 30 benchmark sessions
    s = beta_stats(r_s, r_m)
    assert s["n_aligned"] == 250 and s["beta"] == pytest.approx(2.0)
    assert beta_stats(r_s, r_m, n=1000)["n_aligned"] == 270


def test_beta_stats_degenerate_inputs_return_none_not_raise():
    s = beta_stats(_series([0.01]), _series([0.01]))
    assert s["beta"] is None and s["corr"] is None and s["idio_vol"] is None and s["n_aligned"] == 1
    flat = beta_stats(_series([0.01] * 10), _series([0.0] * 10))  # zero benchmark variance
    assert flat["beta"] is None


# --- drawdown, worst moves, trailing returns ------------------------------------

def test_drawdowns():
    d = drawdowns(_series([100, 120, 90, 110]))
    assert d["max_dd"] == pytest.approx(-0.25)
    assert d["dd_now"] == pytest.approx(110 / 120 - 1)
    assert drawdowns(_series([100, 101, 102]))["max_dd"] == pytest.approx(0.0)


def test_worst_moves():
    p = _series([100, 101, 102, 103, 104, 105, 95, 96, 97, 98, 99, 100, 101])
    w = worst_moves(p)
    assert w["worst_day"] == pytest.approx(95 / 105 - 1)
    # worst 5-session window: t=6 (95) vs t=1 (101) -> 95/101 - 1
    assert w["worst_week"] == pytest.approx(95 / 101 - 1)


def test_trailing_returns_exact_and_none_when_short():
    p = _series(np.arange(1, 252, dtype=float))          # 251 prints: P_last = 251
    t = trailing_returns(p)
    assert t["ret_1m"] == pytest.approx(251 / 230 - 1)   # k = 21
    assert t["ret_3m"] == pytest.approx(251 / 188 - 1)   # k = 63
    assert t["ret_1y"] == pytest.approx(251 / 1 - 1)     # k = 250
    short = trailing_returns(_series(np.arange(1, 64, dtype=float)))   # 63 prints
    assert short["ret_1m"] is not None and short["ret_3m"] is None and short["ret_1y"] is None


# --- liquidity ----------------------------------------------------------------------

def test_liquidity_and_days_to_exit():
    liq = liquidity(_bars(_series([100.0] * 30), turnover=250.0, delivery=40.0))
    assert liq["adv_20_cr"] == pytest.approx(2.5)
    assert liq["delivery_pct_20"] == pytest.approx(40.0)
    assert liq["days_to_exit_5l"] == 1
    assert days_to_exit(5e5, 2.5) == 1
    assert days_to_exit(5e5, 0.02) == 25
    assert days_to_exit(5e5, None) is None
    assert days_to_exit(5e5, 0.0) is None
    assert days_to_exit(5e6, 2.5, participation=0.05) == 4


def test_liquidity_median_ignores_one_spike_and_needs_ten_sessions():
    turnover = [100.0] * 19 + [1_000_000.0]
    b = _bars(_series([100.0] * 20))
    b["turnover_lakh"] = turnover
    assert liquidity(b)["adv_20_cr"] == pytest.approx(1.0)
    few = liquidity(_bars(_series([100.0] * 9)))
    assert few == {"adv_20_cr": None, "delivery_pct_20": None, "days_to_exit_5l": None}


def test_coverage_inside_the_stocks_own_range():
    mkt = pd.bdate_range("2025-01-01", periods=100)
    stock = mkt[[i for i in range(100) if i % 10 not in (3, 6, 8)]]   # 70 prints incl. first and last
    assert len(stock) == 70
    assert coverage(stock, mkt) == pytest.approx(0.70)
    # a stock listed halfway through is judged on its own span only
    assert coverage(mkt[50:], mkt) == pytest.approx(1.0)
    assert coverage(pd.DatetimeIndex([]), mkt) == 0.0


# --- the orchestrator ------------------------------------------------------------------

SPLIT = {"event_type": "split", "details": {"from_fv": 10, "to_fv": 5}}   # 1:2, factor 0.5


def test_symbol_metrics_adjusts_a_split_the_prices_show():
    mkt = _mkt()
    stock = _levered(mkt)
    ex = stock.index[150]
    shown = stock.copy()
    shown[shown.index >= ex] /= 2                        # the split is in the unadjusted prints
    m = symbol_metrics("ABC", _bars(shown), mkt, [{**SPLIT, "event_date": ex.date().isoformat()}],
                       "EQ", set())
    assert "action_unverified" not in m["flags"]
    assert m["beta_1y"] == pytest.approx(1.5, rel=1e-6)
    assert m["corr_1y"] == pytest.approx(1.0, abs=1e-9)
    assert m["worst_day_1y"] > -0.2                      # no fake -50% day
    assert m["vol_1y"] > 0 and m["vol_3m"] > 0 and m["sessions"] == 270
    assert m["flags"] == []


def test_symbol_metrics_unverified_action_blanks_price_metrics_keeps_liquidity():
    mkt = _mkt()
    stock = _levered(mkt)                                  # no jump at the "ex-date"
    m = symbol_metrics("ABC", _bars(stock), mkt,
                       [{**SPLIT, "event_date": stock.index[150].date().isoformat()}], "EQ", set())
    assert "action_unverified" in m["flags"]
    for k in ("vol_1y", "vol_3m", "beta_1y", "corr_1y", "idio_vol_1y", "max_dd_1y", "dd_now",
              "worst_day_1y", "worst_week_1y", "ret_1m", "ret_3m", "ret_1y"):
        assert m[k] is None, k
    assert m["adv_20_cr"] == pytest.approx(5.0) and m["days_to_exit_5l"] == 1


def test_symbol_metrics_short_history():
    mkt = _mkt()
    stock = _levered(mkt).iloc[-80:]                     # listed 80 sessions ago
    m = symbol_metrics("NEW", _bars(stock), mkt, [], "EQ", set())
    assert "short_history" in m["flags"] and "sparse" not in m["flags"]
    assert m["vol_1y"] is None and m["beta_1y"] is None and m["ret_1y"] is None
    assert m["vol_3m"] is not None and m["max_dd_1y"] is not None
    tiny = symbol_metrics("NEW", _bars(stock.iloc[-8:]), mkt, [], "EQ", set())
    assert "short_history" in tiny["flags"] and tiny["vol_3m"] is None and tiny["max_dd_1y"] is None
    assert tiny["sessions"] == 8


def test_symbol_metrics_sparse_nulls_beta_only():
    mkt = _mkt()
    stock = _levered(mkt)
    stock = stock[(np.arange(len(stock)) % 3 != 1)]      # prints on ~2/3 of sessions
    m = symbol_metrics("THIN", _bars(stock), mkt, [], "EQ", set())
    assert "sparse" in m["flags"]
    assert m["beta_1y"] is None and m["corr_1y"] is None and m["idio_vol_1y"] is None
    assert m["vol_1y"] is not None


def test_symbol_metrics_flags_sme_surveillance_illiquid():
    mkt = _mkt()
    b = _bars(_levered(mkt), turnover=40.0)              # Rs 0.4 crore/day
    m = symbol_metrics("SMOL", b, mkt, [], "SM", {"asm_lt", "gsm"})
    assert set(m["flags"]) == {"sme", "asm", "gsm", "illiquid"}
    assert "asm" in symbol_metrics("X", _bars(_levered(mkt)), mkt, [], "EQ", {"asm_st"})["flags"]
    assert symbol_metrics("X", _bars(_levered(mkt)), mkt, [], None, set())["flags"] == []


PRICE_KEYS = ("vol_1y", "vol_3m", "beta_1y", "corr_1y", "idio_vol_1y", "max_dd_1y", "dd_now",
              "worst_day_1y", "worst_week_1y", "ret_1m", "ret_3m", "ret_1y")


def test_symbol_metrics_price_break_blanks_price_metrics():
    """A one-session move no NSE price band allows, with no action to explain it, is a missing
    split / bonus / demerger in corporate_events — never a real -50% day."""
    mkt = _mkt()
    stock = _levered(mkt)
    stock[stock.index >= stock.index[150]] /= 2           # a 1:1 bonus the events table never recorded
    m = symbol_metrics("ABC", _bars(stock), mkt, [], "SM", set())
    assert "price_break" in m["flags"] and "action_unverified" not in m["flags"]
    assert all(m[k] is None for k in PRICE_KEYS)
    assert m["adv_20_cr"] == pytest.approx(5.0)


def test_symbol_metrics_real_crash_is_not_a_break():
    mkt = _mkt()
    stock = _levered(mkt)
    stock[stock.index >= stock.index[150]] *= 0.75        # -25%: an F&O stock can do that
    m = symbol_metrics("ABC", _bars(stock), mkt, [], "EQ", set())
    assert "price_break" not in m["flags"]
    assert m["worst_day_1y"] == pytest.approx(-0.25, abs=0.05)


def test_symbol_metrics_demerger_inside_window_is_a_break():
    mkt = _mkt()
    stock = _levered(mkt)
    ex = stock.index[200]
    stock[stock.index >= ex] *= 0.9                       # the child's value leaves the parent
    dem = [{"event_type": "demerger", "event_date": ex.date().isoformat(), "details": {}}]
    m = symbol_metrics("PARENT", _bars(stock), mkt, dem, "EQ", set())
    assert "price_break" in m["flags"] and all(m[k] is None for k in PRICE_KEYS)
    old = [{"event_type": "demerger", "event_date": "2020-01-01", "details": {}}]
    assert "price_break" not in symbol_metrics("P", _bars(stock), mkt, old, "EQ", set())["flags"]


def test_symbol_metrics_propagates_a_corrupt_store():
    from scanner.pricestore import BadPriceData
    bad = pd.Series([100.0, 101.0], index=pd.DatetimeIndex(["1970-01-01", "1970-01-02"]))
    with pytest.raises(BadPriceData):
        symbol_metrics("BAD", _bars(bad), _mkt(), [], "EQ", set())


# --- ranks and the DB boundary ------------------------------------------------------------

def test_add_ranks():
    rows = [{"symbol": "A", "vol_1y": 0.2, "adv_20_cr": 10.0},
            {"symbol": "B", "vol_1y": 0.6, "adv_20_cr": None},
            {"symbol": "C", "vol_1y": 0.4, "adv_20_cr": 1.0},
            {"symbol": "D", "vol_1y": None, "adv_20_cr": 5.0}]
    out = {r["symbol"]: r for r in add_ranks(rows)}
    assert [out[s]["vol_rank"] for s in "ABCD"] == [0.0, 100.0, 50.0, None]
    assert [out[s]["liq_rank"] for s in "ABCD"] == [100.0, None, 0.0, 50.0]


def test_risk_row_is_db_safe():
    from datetime import date
    m = {"symbol": "ABC", "sessions": 270, "last_date": pd.Timestamp("2026-09-29"),
         "vol_1y": float("nan"), "vol_3m": float("inf"), "beta_1y": np.float64(1.234567),
         "corr_1y": pd.NaT, "idio_vol_1y": None, "max_dd_1y": -0.25, "dd_now": -0.1,
         "worst_day_1y": -0.05, "worst_week_1y": -0.1, "ret_1m": 0.01, "ret_3m": 0.02, "ret_1y": 0.3,
         "adv_20_cr": 2.5, "days_to_exit_5l": np.int64(1), "delivery_pct_20": 45.0,
         "vol_rank": 50.0, "liq_rank": None, "flags": ["sparse"]}
    r = risk_row(m, date(2026, 9, 30))
    json.dumps(r)                                         # every value serialisable
    assert r["as_of"] == "2026-09-29"                     # the symbol's last session in the window
    assert r["vol_1y"] is None and r["vol_3m"] is None and r["corr_1y"] is None
    assert r["beta_1y"] == pytest.approx(1.2346, abs=1e-4)
    assert r["days_to_exit_5l"] == 1 and type(r["days_to_exit_5l"]) is int
    assert r["flags"] == ["sparse"] and r["sessions"] == 270
    assert "last_date" not in r
    no_date = risk_row({**m, "last_date": None}, date(2026, 9, 30))
    assert no_date["as_of"] == "2026-09-30"


def test_format_table_handles_blanks_and_flags():
    rows = [{"symbol": "ABC", "vol_1y": None, "beta_1y": None, "max_dd_1y": None, "dd_now": None,
             "adv_20_cr": None, "days_to_exit_5l": None, "flags": ["action_unverified"]},
            {"symbol": "XYZ", "vol_1y": 0.25, "beta_1y": 1.1, "max_dd_1y": -0.2, "dd_now": -0.05,
             "adv_20_cr": 120.0, "days_to_exit_5l": 1, "flags": []}]
    out = format_table(rows)
    assert "ABC" in out and "action_unverified" in out and "XYZ" in out and "25" in out
