"""Test-first spec for the rights-entitlement (RE) mispricing study (candidate signal #4)."""
import pandas as pd
import pytest

from scanner.rights import issue_price, re_gap, re_symbol, gap_series, rights_events


def test_issue_price_is_face_value_plus_premium():
    assert issue_price(10, 14) == 24.0
    assert issue_price(1, 0.63) == pytest.approx(1.63)
    assert issue_price(None, 5) is None and issue_price(10, None) is None


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


def test_rights_events_need_face_value_and_skip_later_splits():
    rights = [{"symbol": "ABC", "event_date": "2024-05-01", "record_date": "2024-05-01",
               "details": {"ratio": "1:5", "premium": 90}},
              {"symbol": "SPL", "event_date": "2023-01-01", "record_date": None,
               "details": {"ratio": "1:2", "premium": 5}},
              {"symbol": "NOFV", "event_date": "2024-01-01", "record_date": None,
               "details": {"ratio": "1:2", "premium": 5}}]
    fv = {"ABC": 10.0, "SPL": 2.0}
    splits = [{"symbol": "SPL", "event_type": "split", "event_date": "2024-06-01"}]
    ev = rights_events(rights, fv, splits)
    assert ev == [{"symbol": "ABC", "ex_date": "2024-05-01", "ratio": "1:5", "premium": 90.0,
                   "face_value": 10.0, "issue_price": 100.0}]


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
