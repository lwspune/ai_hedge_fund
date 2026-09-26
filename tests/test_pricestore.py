"""Test-first spec for the unified price store (infra I2)."""
import numpy as np
import pandas as pd
import pytest

from scanner import pricestore as ps


def _s(dates, vals):
    return pd.Series(vals, index=pd.to_datetime(dates), dtype="float64")


def test_clean_sorts_dedupes_and_drops_nonpositive():
    raw = _s(["2024-01-03", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
             [101.0, 100.0, 102.0, 0.0, np.nan])
    out = ps.clean_series(raw)
    assert list(out.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert out.iloc[-1] == 102.0  # duplicate date keeps the last print


def test_clean_drops_isolated_bad_tick_but_keeps_real_moves():
    # 100 -> 400 -> 101 is a bad print (spike that fully reverts); 100 -> 40 -> 40 is a real crash
    spike = _s(pd.date_range("2024-01-01", periods=4), [100, 400, 101, 102])
    assert 400 not in ps.clean_series(spike).values
    crash = _s(pd.date_range("2024-01-01", periods=4), [100, 40, 40, 41])
    assert len(ps.clean_series(crash)) == 4


def test_clean_rejects_corrupt_epoch_dates():
    bad = _s(["1970-01-01 00:25:10", "1970-01-01 00:25:11"], [1.0, 2.0])
    with pytest.raises(ps.BadPriceData):
        ps.clean_series(bad)


def test_cache_roundtrip_preserves_dates(tmp_path):
    s = _s(["2018-01-02", "2018-01-03", "2026-09-23"], [1.0, 2.0, 3.0])
    fp = tmp_path / "X.parquet"
    ps.write_cache(fp, s)
    back = ps.read_cache(fp)
    assert list(back.index) == list(s.index)  # Timestamp equality is unit-agnostic
    assert list(back.values) == [1.0, 2.0, 3.0]


def test_get_closes_fetches_once_then_serves_cache_and_slices(tmp_path, monkeypatch):
    calls = []
    full = _s(pd.date_range("2024-01-01", periods=10, freq="D"), np.arange(100.0, 110.0))

    def fake(symbol):
        calls.append(symbol)
        return full

    monkeypatch.setitem(ps.FETCHERS, "yf", fake)
    a = ps.get_closes("ABC", "2024-01-03", "2024-01-05", source="yf", cache_dir=tmp_path,
                      today=pd.Timestamp("2024-01-10"))
    b = ps.get_closes("ABC", "2024-01-03", "2024-01-05", source="yf", cache_dir=tmp_path,
                      today=pd.Timestamp("2024-01-10"))
    assert calls == ["ABC"]
    assert list(a.values) == [102.0, 103.0, 104.0]
    pd.testing.assert_series_equal(a, b)


def test_get_closes_refetches_when_cache_is_behind_requested_end(tmp_path, monkeypatch):
    calls = []
    old = _s(pd.date_range("2024-01-01", periods=5, freq="D"), np.arange(1.0, 6.0))
    new = _s(pd.date_range("2024-01-01", periods=20, freq="D"), np.arange(1.0, 21.0))
    seq = iter([old, new])

    def fake(symbol):
        calls.append(symbol)
        return next(seq)

    monkeypatch.setitem(ps.FETCHERS, "yf", fake)
    ps.get_closes("ABC", source="yf", cache_dir=tmp_path, today=pd.Timestamp("2024-01-05"))
    s = ps.get_closes("ABC", source="yf", cache_dir=tmp_path, today=pd.Timestamp("2024-01-20"))
    assert len(calls) == 2 and len(s) == 20


def test_get_closes_returns_none_when_source_has_nothing(tmp_path, monkeypatch):
    monkeypatch.setitem(ps.FETCHERS, "yf", lambda symbol: pd.Series(dtype="float64"))
    assert ps.get_closes("NOPE", source="yf", cache_dir=tmp_path, today=pd.Timestamp("2024-01-10")) is None


def test_nse_frame_keeps_equity_series_and_prefers_eq():
    df = pd.DataFrame({
        "Date": ["02-Jan-2024", "02-Jan-2024", "03-Jan-2024", "04-Jan-2024", "05-Jan-2024"],
        "Series": ["SM", "EQ", "ST", "W1", "BE"],
        "ClosePrice": ["10", "11", "1,012.5", "999", "12"],
    })
    s = ps.nse_frame_to_series(df)
    assert list(s.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-05"]))
    assert list(s.values) == [11.0, 1012.5, 12.0]  # EQ wins the 2nd; warrant (W1) dropped


def test_get_closes_refetches_when_request_starts_before_cached_coverage(tmp_path, monkeypatch):
    calls = []
    full = _s(pd.date_range("2020-01-01", "2024-01-10", freq="D"), 1.0)

    def fake(symbol, start="2010-01-01", end=None):
        calls.append(start)
        return full[full.index >= pd.Timestamp(start)]

    monkeypatch.setitem(ps.FETCHERS, "nse", fake)
    today = pd.Timestamp("2024-01-10")
    a = ps.get_closes("X", "2023-06-01", source="nse", cache_dir=tmp_path, today=today)
    ps.get_closes("X", "2023-07-01", source="nse", cache_dir=tmp_path, today=today)  # covered
    b = ps.get_closes("X", "2021-01-01", source="nse", cache_dir=tmp_path, today=today)  # earlier
    assert calls == ["2023-06-01", "2021-01-01"]
    assert a.index.min() == pd.Timestamp("2023-06-01") and b.index.min() == pd.Timestamp("2021-01-01")


def test_get_closes_nse_fetch_is_bounded_by_requested_end(tmp_path, monkeypatch):
    """Old IPOs only need a window; fetching to today costs one nselib call per year."""
    calls = []
    full = _s(pd.date_range("2010-01-01", "2024-01-10", freq="D"), 1.0)

    def fake(symbol, start="2010-01-01", end=None):
        calls.append((start, end))
        s = full[full.index >= pd.Timestamp(start)]
        return s[s.index <= pd.Timestamp(end)] if end else s

    monkeypatch.setitem(ps.FETCHERS, "nse", fake)
    today = pd.Timestamp("2024-01-10")
    ps.get_closes("OLD", "2010-06-01", "2010-12-31", source="nse", cache_dir=tmp_path, today=today)
    assert calls == [("2010-06-01", "2010-12-31")]
    ps.get_closes("OLD", "2010-06-01", "2010-11-30", source="nse", cache_dir=tmp_path, today=today)
    assert len(calls) == 1                     # inside cached window
    s = ps.get_closes("OLD", "2010-06-01", source="nse", cache_dir=tmp_path, today=today)
    assert len(calls) == 2 and s.index.max() == pd.Timestamp("2024-01-10")  # extended to today


# --- source="db": Supabase daily_prices (recent) + prices bucket months (older) — WP3 ---------

def _raw_month(rows):
    """A bhav/YYYY-MM.parquet frame: raw columns, every series."""
    return pd.DataFrame([{"SYMBOL": s, "SERIES": ser, "DATE1": pd.Timestamp(d), "CLOSE_PRICE": c,
                          "TTL_TRD_QNTY": 100, "TURNOVER_LACS": 1.0, "DELIV_PER": 50.0}
                         for s, ser, d, c in rows])


@pytest.fixture
def db_source(monkeypatch):
    months = {
        "2024-05": _raw_month([("X", "EQ", "2024-05-30", 10.0), ("X", "BE", "2024-05-30", 99.0),
                               ("X", "EQ", "2024-05-31", 11.0), ("Y", "EQ", "2024-05-31", 5.0),
                               ("X", "GB", "2024-05-31", 77.0)]),
        "2024-06": _raw_month([("X", "EQ", "2024-06-03", 12.0)]),
    }
    table = [{"trade_date": "2024-06-04", "close": 13.0, "volume": 7, "turnover_lakh": 2.0, "delivery_pct": 40.0},
             {"trade_date": "2024-06-05", "close": 14.0, "volume": 8, "turnover_lakh": 2.5, "delivery_pct": None}]
    calls = {"months": [], "table": []}

    def month(ym):
        calls["months"].append(ym)
        return months.get(ym)

    def rows(symbol, lo, hi):
        calls["table"].append((symbol, lo, hi))
        return [r for r in table if lo <= r["trade_date"] <= hi] if symbol == "X" else []

    monkeypatch.setattr(ps, "_bhav_month", month)
    monkeypatch.setattr(ps, "_db_rows", rows)
    monkeypatch.setattr(ps, "_table_floor", lambda: pd.Timestamp("2024-06-04"))
    return calls


def test_db_source_splits_table_and_bucket(db_source):
    s = ps.get_closes("X", "2024-05-30", "2024-06-05", source="db")
    assert list(s.index) == list(pd.to_datetime(["2024-05-30", "2024-05-31", "2024-06-03",
                                                 "2024-06-04", "2024-06-05"]))
    assert list(s.values) == [10.0, 11.0, 12.0, 13.0, 14.0]   # EQ beats BE; GB ignored
    assert db_source["months"] == ["2024-05", "2024-06"]        # only months before the table floor
    assert db_source["table"] == [("X", "2024-06-04", "2024-06-05")]


def test_db_source_recent_window_never_touches_bucket(db_source):
    s = ps.get_closes("X", "2024-06-05", "2024-06-05", source="db")
    assert list(s.values) == [14.0] and db_source["months"] == []


def test_db_source_old_window_never_touches_table(db_source):
    s = ps.get_closes("X", "2024-05-31", "2024-05-31", source="db")
    assert list(s.values) == [11.0] and db_source["table"] == []


def test_db_source_none_when_empty(db_source):
    assert ps.get_closes("NOPE", "2024-05-01", "2024-06-05", source="db") is None


def test_get_bars_has_volume_turnover_delivery(db_source):
    b = ps.get_bars("X", "2024-05-31", "2024-06-05")
    assert list(b.columns) == ["close", "volume", "turnover_lakh", "delivery_pct"]
    assert b.loc["2024-06-04", "volume"] == 7 and b.loc["2024-05-31", "delivery_pct"] == 50.0


def test_db_source_benchmark_reads_index_prices(monkeypatch):
    seen = []

    def rows(symbol, lo, hi):
        seen.append(symbol)
        return [{"trade_date": "2024-06-04", "close": 22000.0}]

    monkeypatch.setattr(ps, "_db_rows", rows)
    monkeypatch.setattr(ps, "_bhav_month", lambda ym: pytest.fail("benchmarks never read bhav months"))
    s = ps.get_closes("^NSEI", "2020-01-01", "2024-06-05", source="db")
    assert seen == ["^NSEI"] and list(s.values) == [22000.0]


def test_get_closes_requires_explicit_source():
    """Adjusted Yahoo closes silently used for a nominal-price premium was a real bug class."""
    with pytest.raises(TypeError):
        ps.get_closes("X", "2024-01-01", "2024-02-01")


def test_first_bar_gives_the_listing_session_open_and_close(monkeypatch):
    months = {"2026-09": pd.DataFrame([
        {"SYMBOL": "NEWCO", "SERIES": "BE", "DATE1": pd.Timestamp("2026-09-29"), "OPEN_PRICE": 99.0, "CLOSE_PRICE": 98.0},
        {"SYMBOL": "NEWCO", "SERIES": "EQ", "DATE1": pd.Timestamp("2026-09-29"), "OPEN_PRICE": 120.0, "CLOSE_PRICE": 131.5},
        {"SYMBOL": "OTHER", "SERIES": "EQ", "DATE1": pd.Timestamp("2026-09-28"), "OPEN_PRICE": 10.0, "CLOSE_PRICE": 11.0}]),
        "2026-10": pd.DataFrame([
        {"SYMBOL": "LATE", "SERIES": "SM", "DATE1": pd.Timestamp("2026-10-01"), "OPEN_PRICE": 55.0, "CLOSE_PRICE": 52.0}])}
    monkeypatch.setattr(ps, "_bhav_month", lambda ym: months.get(ym))
    assert ps.first_bar("NEWCO", "2026-09-26") == {"date": pd.Timestamp("2026-09-29"), "open": 120.0, "close": 131.5}
    assert ps.first_bar("LATE", "2026-09-30") == {"date": pd.Timestamp("2026-10-01"), "open": 55.0, "close": 52.0}
    assert ps.first_bar("NEWCO", "2026-09-30") is None          # nothing on/after within the window
    assert ps.first_bar("GHOST", "2026-09-26") is None
