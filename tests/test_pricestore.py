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
    a = ps.get_closes("ABC", "2024-01-03", "2024-01-05", cache_dir=tmp_path,
                      today=pd.Timestamp("2024-01-10"))
    b = ps.get_closes("ABC", "2024-01-03", "2024-01-05", cache_dir=tmp_path,
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
    ps.get_closes("ABC", cache_dir=tmp_path, today=pd.Timestamp("2024-01-05"))
    s = ps.get_closes("ABC", cache_dir=tmp_path, today=pd.Timestamp("2024-01-20"))
    assert len(calls) == 2 and len(s) == 20


def test_get_closes_returns_none_when_source_has_nothing(tmp_path, monkeypatch):
    monkeypatch.setitem(ps.FETCHERS, "yf", lambda symbol: pd.Series(dtype="float64"))
    assert ps.get_closes("NOPE", cache_dir=tmp_path, today=pd.Timestamp("2024-01-10")) is None


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
