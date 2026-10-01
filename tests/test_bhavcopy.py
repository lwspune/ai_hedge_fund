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


def test_decode_handles_xlsx_served_as_csv():
    """NSE served 2022-08-08 as an Excel workbook under the .csv name."""
    import io
    from scanner.bhavcopy import decode_bhavcopy
    raw = parse_raw(_text())
    xl = raw.assign(DATE1=raw["DATE1"].dt.strftime("%d-%b-%Y"))
    xl.columns = [xl.columns[0]] + [f" {c}" for c in xl.columns[1:]]     # NSE pads headers here too
    buf = io.BytesIO()
    xl.to_excel(buf, index=False)
    text = decode_bhavcopy(buf.getvalue())
    rows = {r["symbol"]: r for r in parse_bhavcopy(text, min_eq=10)}
    assert rows["21STCENMGM"]["close"] == 39.92 and rows["21STCENMGM"]["trade_date"] == "2026-09-23"


def test_decode_passes_csv_through():
    from scanner.bhavcopy import decode_bhavcopy
    assert decode_bhavcopy(_text().encode("utf-8")) == _text()


# --- NSE daily index closes (fallback for the sessions Yahoo misses) -------------------------------

IDX = Path(__file__).resolve().parent / "fixtures" / "indices" / "ind_close_all_01012026_head.csv"


def test_index_url():
    from scanner.bhavcopy import index_url
    assert index_url(date(2026, 1, 1)) == \
        "https://nsearchives.nseindia.com/content/indices/ind_close_all_01012026.csv"


def test_parse_index_closes_matches_names_exactly():
    from scanner.bhavcopy import parse_index_closes
    got = parse_index_closes(IDX.read_text(encoding="utf-8"))
    assert got == {"^NSEI": {"date": date(2026, 1, 1), "close": 26146.55, "change": 16.95},
                   "^CRSLDX": {"date": date(2026, 1, 1), "close": 23909.55, "change": 38.0}}
    # "Nifty Next 50" / "Nifty500 Multicap 50:25:25" are other indices, never a benchmark
    assert parse_index_closes("Index Name,Index Date,Closing Index Value\n") == {}
    assert parse_index_closes("") == {}


def test_parse_index_closes_skips_unreadable_rows():
    from scanner.bhavcopy import parse_index_closes
    head = IDX.read_text(encoding="utf-8").splitlines()[0]
    bad = head + "\nNifty 50,01-01-2026,1,1,1,-,-,-,0,0,0,0,0\nNifty 500,garbage,1,1,1,23909.55,38.0,.16,0,0,0,0,0\n"
    assert parse_index_closes(bad) == {}


def test_confirm_close_against_the_previous_close():
    from scanner.bhavcopy import confirm_close
    assert confirm_close(23871.6, 23909.55, 38.0)            # stored prev (real) + NSE change = NSE close
    assert not confirm_close(23500.0, 23909.55, 38.0)        # a different day's file / wrong index
    assert not confirm_close(None, 23909.55, 38.0)           # nothing to check against
    assert not confirm_close(23871.6, 23909.55, None)


def test_parse_index_closes_with_a_sector_name_map():
    from scanner.bhavcopy import parse_index_closes
    text = IDX.read_text(encoding="utf-8")
    got = parse_index_closes(text, {"nifty bank": "Nifty Bank", "nifty it": "Nifty IT"})
    assert got == {"Nifty Bank": {"date": date(2026, 1, 1), "close": 59711.55, "change": 129.7},
                   "Nifty IT": {"date": date(2026, 1, 1), "close": 38171.5, "change": 287.45}}
    assert set(parse_index_closes(text)) == {"^NSEI", "^CRSLDX"}            # default: the two benchmarks



def test_parse_index_closes_keeps_the_month_first_reading():
    from scanner.bhavcopy import parse_index_closes
    head = IDX.read_text(encoding="utf-8").splitlines()[0]
    text = "\n".join([head, "Nifty Bank,04-06-2023,40940.7,41274.7,40820.55,41041,41.85,0.1,1,1,1,1,1",
                      "Nifty IT,13-04-2023,1,1,1,28000,10,0.1,1,1,1,1,1"]) + "\n"
    got = parse_index_closes(text, {"nifty bank": "Nifty Bank", "nifty it": "Nifty IT"})
    assert got["Nifty Bank"]["date"] == date(2023, 6, 4) and got["Nifty Bank"]["date_alt"] == date(2023, 4, 6)
    assert "date_alt" not in got["Nifty IT"]                                    # 13 can't be a month
