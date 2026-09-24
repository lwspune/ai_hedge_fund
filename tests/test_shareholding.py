"""Test-first spec for quarterly shareholding + promoter pledge (NSE share-holdings master + SHP XBRL).

The small-shareholder (nominal capital <= Rs 2 lakh) percentage is the denominator of the buyback
15% reservation; the promoter pledge % feeds backlog signal #8. Percentages are stored in 0-100
units (the XBRL carries fractions)."""
from pathlib import Path

from scanner.shareholding import (
    parse_shp_master, parse_shp_xbrl, quarters_to_fetch, shareholding_row,
)

FIX = Path(__file__).parent / "fixtures"

MASTER = [
    {"broadcastDate": "17-JUL-2026 16:55:08", "date": "30-JUN-2026", "desc": "NEW_1", "isin": "IN9095A01010",
     "name": "IndusInd Bank Limited", "pr_and_prgrp": "15.82", "public_val": "84.18", "recordId": "211767",
     "revisedData": "N", "revisedDate": None, "symbol": "INDUSINDBK",
     "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1695339_17072026045502_WEB.xml"},
    {"broadcastDate": "20-APR-2026 10:00:00", "date": "31-MAR-2026", "pr_and_prgrp": "15.83", "public_val": "84.17",
     "revisedData": "Y", "symbol": "INDUSINDBK", "xbrl": "https://x/SHP_MAR.xml"},
    # an interim (event-triggered) filing is not a quarter end -> skipped
    {"broadcastDate": "05-FEB-2026 10:00:00", "date": "31-JAN-2026", "pr_and_prgrp": "15.83", "public_val": "84.17",
     "symbol": "INDUSINDBK", "xbrl": "https://x/SHP_JAN.xml"},
    # no XBRL link -> nothing to parse, skipped
    {"broadcastDate": "15-JAN-2021 10:00:00", "date": "31-DEC-2020", "pr_and_prgrp": "-", "public_val": "-",
     "symbol": "INDUSINDBK", "xbrl": None},
]


def test_parse_shp_master_keeps_quarter_ends_with_xbrl_newest_first():
    rows = parse_shp_master(MASTER)
    assert [r["quarter_end"] for r in rows] == ["2026-06-30", "2026-03-31"]
    assert rows[0] == {"symbol": "INDUSINDBK", "quarter_end": "2026-06-30",
                       "broadcast_at": "2026-07-17T16:55:08", "promoter_pct": 15.82, "public_pct": 84.18,
                       "revised": False, "xbrl_url": MASTER[0]["xbrl"]}
    assert rows[1]["revised"] is True


def test_parse_shp_xbrl_extracts_category_percentages_in_percent_units():
    d = parse_shp_xbrl((FIX / "shp.xml").read_text(encoding="utf-8"))
    assert d["promoter_pct"] == 15.82
    assert d["public_pct"] == 84.18
    assert d["small_holder_pct"] == 6.49          # resident individuals <= Rs 2 lakh nominal
    assert d["mf_pct"] == 30.26
    assert d["dii_pct"] == 42.25
    assert d["fpi_pct"] == 29.16
    assert d["pledge_pct_of_promoter"] == 42.78   # promoter context: share of the promoter holding
    assert d["pledge_pct_of_total"] == 6.45       # whole-pattern context: share of all shares
    assert d["n_shareholders"] == 568147
    assert d["n_small_holders"] == 547134


def test_parse_shp_xbrl_pledge_absent_is_zero_when_flag_is_false_else_none():
    xml = (FIX / "shp.xml").read_text(encoding="utf-8")
    no_tags = xml.replace(
        '<in-bse-shp:EncumberedSharesHeldAsPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI" decimals="INF" unitRef="pure">0.4278</in-bse-shp:EncumberedSharesHeldAsPercentageOfTotalNumberOfShares>', "")
    clean = no_tags.replace(">true</in-bse-shp:WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged>",
                            ">false</in-bse-shp:WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged>")
    assert parse_shp_xbrl(clean)["pledge_pct_of_promoter"] == 0.0
    assert parse_shp_xbrl(no_tags)["pledge_pct_of_promoter"] is None   # flagged pledged, value unreadable


def test_parse_shp_xbrl_unknown_taxonomy_returns_nones_not_garbage():
    d = parse_shp_xbrl("<xbrli:xbrl xmlns:xbrli='http://www.xbrl.org/2003/instance'/>")
    assert d["small_holder_pct"] is None and d["promoter_pct"] is None


def test_shareholding_row_merges_master_and_xbrl():
    master = parse_shp_master(MASTER)[0]
    xb = parse_shp_xbrl((FIX / "shp.xml").read_text(encoding="utf-8"))
    row = shareholding_row(master, xb)
    assert row["symbol"] == "INDUSINDBK" and row["quarter_end"] == "2026-06-30"
    assert row["small_holder_pct"] == 6.49 and row["pledge_pct_of_promoter"] == 42.78
    assert row["promoter_pct"] == 15.82 and row["source"] == "nse_shp"
    assert row["xbrl_url"] == MASTER[0]["xbrl"]
    # the master's headline promoter % wins when the XBRL is unreadable
    row2 = shareholding_row(master, parse_shp_xbrl("<x/>"))
    assert row2["promoter_pct"] == 15.82 and row2["small_holder_pct"] is None


def test_quarters_to_fetch_is_missing_quarters_newest_first_within_limit():
    rows = parse_shp_master(MASTER)
    assert [r["quarter_end"] for r in quarters_to_fetch(rows, stored={"2026-03-31"}, limit=5)] == ["2026-06-30"]
    assert [r["quarter_end"] for r in quarters_to_fetch(rows, stored=set(), limit=1)] == ["2026-06-30"]
    assert quarters_to_fetch(rows, stored={"2026-06-30", "2026-03-31"}, limit=5) == []
    assert [r["quarter_end"] for r in quarters_to_fetch(rows, stored=set(), floor="2026-04-01")] == ["2026-06-30"]
