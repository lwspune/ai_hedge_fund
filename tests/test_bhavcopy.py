"""NSE sec_bhavdata_full parsing (DATA_INFRA_SPEC WP3): the daily price store's only input."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scanner.bhavcopy import BadBhavcopy, bhav_url, parse_bhavcopy, parse_raw, to_month_frame

FX = (Path(__file__).resolve().parent / "fixtures" / "bhav" / "sec_bhavdata_full_23092026_head.csv")


def _text():
    return FX.read_text(encoding="utf-8")


def test_bhav_url():
    assert bhav_url(date(2026, 9, 3)) == \
        "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_03092026.csv"


def test_parse_strips_padding_and_types_fields():
    rows = {r["symbol"]: r for r in parse_bhavcopy(_text(), min_eq=10)}
    r = rows["21STCENMGM"]
    assert r == {"symbol": "21STCENMGM", "trade_date": "2026-09-23", "series": "EQ", "close": 39.92,
                 "prev_close": 39.62, "volume": 6072, "turnover_lakh": 2.42, "delivery_pct": 66.68}


def test_parse_keeps_only_equity_series():
    rows = parse_bhavcopy(_text(), min_eq=10)
    assert {r["series"] for r in rows} <= {"EQ", "BE", "BZ", "SM", "ST", "SZ"}
    assert {"EQ", "BE", "SM"} <= {r["series"] for r in rows}


def test_parse_dedupes_symbol_keeping_eq():
    rows = [r for r in parse_bhavcopy(_text(), min_eq=10) if r["symbol"] == "20MICRONS"]
    assert len(rows) == 1 and rows[0]["series"] == "EQ" and rows[0]["close"] == 219.21


def test_parse_dash_delivery_is_none():
    be = [r for r in parse_bhavcopy(_text(), min_eq=10) if r["series"] == "BE"]
    assert be and all(r["delivery_pct"] is None for r in be)


def test_parse_guards_truncated_file():
    with pytest.raises(BadBhavcopy):
        parse_bhavcopy(_text())               # 40 EQ rows < the 1,000 a real day has


def test_parse_guards_non_positive_close():
    bad = _text().replace("39.62, 39.94, 39.95, 39.01, 39.90, 39.92", "39.62, 39.94, 39.95, 39.01, 39.90, 0.00")
    with pytest.raises(BadBhavcopy):
        parse_bhavcopy(bad, min_eq=10)


def test_parse_guards_mixed_dates():
    bad = _text().replace("21STCENMGM, EQ, 23-Sep-2026", "21STCENMGM, EQ, 22-Sep-2026")
    with pytest.raises(BadBhavcopy):
        parse_bhavcopy(bad, min_eq=10)


def test_parse_raw_keeps_every_series_and_column():
    df = parse_raw(_text())
    assert len(df) == 54 and {"GS", "GB", "IV"} <= set(df["SERIES"])
    assert list(df.columns)[:3] == ["SYMBOL", "SERIES", "DATE1"]
    assert df["DATE1"].iloc[0] == pd.Timestamp("2026-09-23")


def test_to_month_frame_replaces_a_reloaded_date():
    day = parse_raw(_text())
    month = to_month_frame(None, day)
    again = to_month_frame(month, day)                     # same date reloaded: no duplicates
    assert len(again) == len(day)
    other = day.assign(DATE1=pd.Timestamp("2026-09-24"))
    both = to_month_frame(again, other)
    assert len(both) == 2 * len(day) and both["DATE1"].is_monotonic_increasing
