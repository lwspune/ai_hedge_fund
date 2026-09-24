"""Test-first spec for the OFS (offer for sale) retail-reservation study (candidate #23)."""
from pathlib import Path

import pandas as pd
import pytest

from scanner.ofs import parse_ofs_page, study_events, ofs_returns, ofs_rows_to_events

FIX = Path(__file__).resolve().parent / "fixtures" / "ofs"


def _fx(oid):
    return (FIX / f"{oid}.html").read_text(encoding="utf-8")


def test_parse_hindustan_copper_page():
    r = parse_ofs_page(_fx(62), 62)
    assert r["chittorgarh_id"] == 62 and r["symbol"] == "HINDCOPPER"
    assert r["company"] == "Hindustan Copper Ltd."
    assert r["floor_price"] == 514.0 and r["cutoff_price"] is None
    assert r["seller"] == "The President of India"
    assert r["base_shares"] == 29010721 and r["oversub_shares"] == 29010721 and r["total_shares"] == 58021442
    assert r["retail_shares"] == 5802146 and r["non_retail_shares"] == 52219296
    assert r["non_retail_date"] == "2026-08-25" and r["retail_date"] == "2026-08-26"
    assert r["pct_equity"] == pytest.approx(6.0)
    assert r["listing_at"] == "BSE, NSE"


def test_parse_coal_india_page():
    r = parse_ofs_page(_fx(54), 54)
    assert r["symbol"] == "COALINDIA" and r["floor_price"] == 412.0
    assert r["retail_date"] == "2026-05-29" and r["non_retail_date"] == "2026-05-27"
    assert r["retail_shares"] == 12325458


def test_parse_rejects_pages_without_symbol_or_floor():
    assert parse_ofs_page("<html><title>Offer For Sale 2026</title></html>", 70) is None
    assert parse_ofs_page('"nseCode":"ABC","floor_price":"","offer_open_date_retail":"May 1, 2026"', 1) is None


def test_study_events_need_a_retail_day_far_enough_back():
    rows = [{"symbol": "A", "floor_price": 100, "retail_date": "2026-08-26", "non_retail_date": "2026-08-25"},
            {"symbol": "B", "floor_price": 100, "retail_date": "2026-09-20", "non_retail_date": "2026-09-19"},
            {"symbol": "C", "floor_price": None, "retail_date": "2026-01-05", "non_retail_date": "2026-01-04"}]
    ev = study_events(rows, today=pd.Timestamp("2026-09-24"), min_days=25)
    assert [e["symbol"] for e in ev] == ["A"]


def test_ofs_returns_measured_against_the_floor():
    idx = pd.bdate_range("2026-08-10", "2026-09-30")
    px = pd.Series(100.0, index=idx)
    px[pd.Timestamp("2026-08-24")] = 110.0   # close before the non-retail day (announcement eve)
    px[pd.Timestamp("2026-08-25")] = 104.0   # non-retail day
    px[pd.Timestamp("2026-08-26")] = 103.0   # retail day
    px[pd.Timestamp("2026-08-27")] = 102.0   # T+1: allotment, first day the shares can be sold
    px[pd.Timestamp("2026-09-02")] = 101.0   # T+5
    px[pd.Timestamp("2026-09-23")] = 99.0    # T+20
    r = ofs_returns(px, floor=100.0, retail_date="2026-08-26", non_retail_date="2026-08-25")
    assert r["pre_close"] == 110.0 and r["floor_discount"] == pytest.approx(100 / 110 - 1)
    assert r["retail_close_vs_floor"] == pytest.approx(0.03)
    assert r["t1"] == pytest.approx(0.02) and r["t5"] == pytest.approx(0.01) and r["t20"] == pytest.approx(-0.01)
    assert r["nonretail_day_move"] == pytest.approx(104 / 110 - 1)


def test_ofs_returns_none_when_prices_missing():
    px = pd.Series([100.0], index=[pd.Timestamp("2026-01-01")])
    assert ofs_returns(px, floor=100.0, retail_date="2026-08-26", non_retail_date="2026-08-25") is None


def test_rows_to_events_shape():
    ev = ofs_rows_to_events([{"chittorgarh_id": 62, "symbol": "HINDCOPPER", "floor_price": "514", "retail_date": "2026-08-26",
                              "non_retail_date": "2026-08-25", "retail_shares": 5802146, "total_shares": 58021442,
                              "seller": "The President of India", "pct_equity": "6.0"}])
    assert ev[0]["floor_price"] == 514.0 and ev[0]["retail_share"] == pytest.approx(0.1)
    assert ev[0]["psu"] is True


def test_format_ofs_rows():
    from scanner.ofs import format_ofs_rows
    out = format_ofs_rows([{"symbol": "HINDCOPPER", "floor_price": "514", "non_retail_date": "2026-08-25",
                            "retail_date": "2026-08-26", "retail_shares": 5802146, "total_shares": 58021442,
                            "pct_equity": "6.0", "seller": "The President of India"}])
    assert "HINDCOPPER" in out and "514" in out and "10%" in out and "President" in out
    assert "No OFS" in format_ofs_rows([])
