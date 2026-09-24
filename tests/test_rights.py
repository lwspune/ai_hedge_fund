"""Test-first spec for the rights-entitlement (RE) mispricing study (candidate signal #4)."""
import pandas as pd
import pytest

from scanner.rights import re_gap, re_symbol, gap_series, events_from_issues, re_symbols


def test_re_gap_positive_when_entitlement_is_cheap():
    # stock 100, issue 60 -> fair RE 40; RE at 36 -> 4% of the share price cheap
    assert re_gap(100.0, 36.0, 60.0) == pytest.approx(0.04)
    assert re_gap(100.0, 44.0, 60.0) == pytest.approx(-0.04)   # RE rich
    assert re_gap(0, 1, 1) is None and re_gap(100, None, 60) is None


def test_re_symbol():
    assert re_symbol("GENESYS") == "GENESYS-RE"


def test_gap_series_aligns_dates_and_drops_nonsense():
    idx = pd.to_datetime(["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"])
    stock = pd.Series([100.0, 102.0, 101.0, 99.0], index=idx)
    re_px = pd.Series([38.0, 0.0, 400.0], index=idx[1:])          # 0 and absurd prints dropped
    g = gap_series(stock, re_px, issue=60.0, bound=0.5)
    assert list(g.index) == [idx[1]]
    assert g.iloc[0] == pytest.approx((102 - 60 - 38) / 102)


def test_format_open_res_ranks_by_gap_and_flags_hurdle():
    from scanner.rights import format_open_res
    rows = [
        {"symbol": "LOWGAP", "ratio": "1:5", "issue_price": 100.0, "stock": 150.0, "re": 49.0,
         "gap": 0.0067, "turnover": 900000.0, "re_date": "2026-09-23"},
        {"symbol": "BIGGAP", "ratio": "3:4", "issue_price": 82.0, "stock": 200.0, "re": 110.0,
         "gap": 0.04, "turnover": 7000000.0, "re_date": "2026-09-23"},
        {"symbol": "RICH", "ratio": "1:2", "issue_price": 50.0, "stock": 100.0, "re": 52.0,
         "gap": -0.02, "turnover": 100000.0, "re_date": "2026-09-23"},
    ]
    lines = format_open_res(rows).splitlines()
    assert "BIGGAP" in lines[1] and "4.00%" in lines[1] and "BUY RE" in lines[1]
    assert "LOWGAP" in lines[2] and "BUY RE" in lines[2]
    assert "RICH" in lines[3] and "illiquid" in lines[3]
    assert format_open_res([]).startswith("No rights entitlements")


def test_format_open_res_flags_penny_issues():
    """The edge was verified on non-penny issues only (issue >= Rs 10 and stock >= Rs 20)."""
    from scanner.rights import format_open_res
    rows = [{"symbol": "CENTEXT", "ratio": "3:8", "issue_price": 15.0, "stock": 18.79, "re": 2.19,
             "gap": 0.0852, "turnover": 1140000.0, "re_date": "2026-09-23"}]
    line = format_open_res(rows).splitlines()[1]
    assert "penny" in line and "BUY RE" not in line


def test_events_from_issues_use_exact_prices_and_skip_partly_paid_or_withdrawn():
    rows = [
        {"symbol": "NDTV", "issue_price": 82.0, "ratio_rights": 3, "ratio_held": 4,
         "record_date": "2025-09-12", "re_credit_date": "2025-09-16", "issue_open": "2025-09-22",
         "renunciation_date": "2025-10-03", "issue_close": "2025-10-08", "re_symbol": "NDTVR",
         "partly_paid": False, "withdrawn": False},
        {"symbol": "TIL", "issue_price": 165.0, "ratio_rights": 11, "ratio_held": 64,
         "record_date": "2026-03-20", "re_credit_date": None, "issue_open": "2026-03-30",
         "renunciation_date": "2026-04-01", "issue_close": "2026-04-08", "re_symbol": "TILRR",
         "partly_paid": True, "withdrawn": False},
        {"symbol": "GONE", "issue_price": 10.0, "ratio_rights": 1, "ratio_held": 1,
         "record_date": "2025-01-01", "re_credit_date": None, "issue_open": "2025-01-10",
         "renunciation_date": None, "issue_close": "2025-01-20", "re_symbol": None,
         "partly_paid": False, "withdrawn": True},
    ]
    ev = events_from_issues(rows)
    assert [e["symbol"] for e in ev] == ["NDTV"]
    e = ev[0]
    assert e["issue_price"] == 82.0 and e["ratio"] == "3:4"
    assert e["re_from"] == "2025-09-16" and e["re_to"] == "2025-10-03" and e["issue_close"] == "2025-10-08"


def test_re_symbols_try_stored_symbol_then_dash_re():
    assert re_symbols("NDTV", "NDTVR") == ["NDTVR", "NDTV-RE"]
    assert re_symbols("SATIN", "SATIN-RE") == ["SATIN-RE"]
    assert re_symbols("ABC", None) == ["ABC-RE"]
