"""Test-first spec for NSE IPO bid details (scanner/ipobids.py): the retail category's
times-subscribed as bid on NSE — the only free source of retail subscription for older issues."""
import json
from pathlib import Path

import pytest

from scanner.ipobids import NSE_SHARE, final_retail_from_nse, parse_bid_details

FX = Path(__file__).parent / "fixtures" / "nse" / "ipo_bid_details_AETHER.json"


def test_parse_retail_times_from_the_saved_response():
    assert parse_bid_details(json.loads(FX.read_text(encoding="utf-8"))) == pytest.approx(0.5870, abs=1e-4)


@pytest.mark.parametrize("payload", [
    {"data": []}, {}, None,
    {"data": [{"category": "Retail Individual Investors(RIIs)", "noOfTime": "", "srNo": "3"}]},
    {"data": [{"category": "Retail Individual Investors(RIIs)", "noOfTime": "0.00", "srNo": "3"}]},   # SME: no offer size
])
def test_parse_returns_none_without_a_usable_retail_row(payload):
    assert parse_bid_details(payload) is None


def test_nse_figure_scales_to_the_consolidated_one():
    # calibrated on 32 mainboard IPOs (Aug-Sep 2026): NSE carries ~65% of retail bids
    assert NSE_SHARE == pytest.approx(0.647)
    assert final_retail_from_nse(8.99) == pytest.approx(8.99 / 0.647)
    assert final_retail_from_nse(None) is None
