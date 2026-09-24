"""Test-first spec for SEBI PIT insider disclosures (NSE `api/corporates-pit-gg` + per-filing XBRL).

The list endpoint carries only filing metadata; the XBRL holds the transactions (one Disclosure
context per insider named). `api/corporates-pit` (no -gg) is dead and always empty."""
from pathlib import Path

from scanner.insider import insider_rows, parse_pit_filings, parse_pit_xml

FIX = Path(__file__).parent / "fixtures"

FILINGS = {"data": [
    {"appId": "3187", "broadcastDateTime": "10-Sep-2026 20:46:52", "companyName": "KARUR VYSYA BANK LIMITED",
     "regulation": "Regulation 7 (2)", "symbol": "KARURVYSYA", "typeOfSubmission": "Original",
     "xmlFileName": "https://nsearchives.nseindia.com/corporate/xbrl/IT_539_WebXMLFile_20260910_204652277.xml"},
    {"appId": "3188", "broadcastDateTime": "garbage", "symbol": "X", "xmlFileName": "https://x/a.xml"},
    {"appId": "3189", "broadcastDateTime": "10-Sep-2026 21:00:00", "symbol": "Y", "xmlFileName": None},
]}


def test_parse_pit_filings_normalises_and_drops_unusable():
    rows = parse_pit_filings(FILINGS)
    assert rows == [{"app_id": 3187, "symbol": "KARURVYSYA", "broadcast_at": "2026-09-10T20:46:52",
                     "regulation": "Regulation 7 (2)", "submission": "Original",
                     "xml_url": FILINGS["data"][0]["xmlFileName"]}]


def test_parse_pit_xml_one_row_per_disclosure_with_typed_fields():
    ds = parse_pit_xml((FIX / "pit.xml").read_text(encoding="utf-8"))
    assert len(ds) == 1
    d = ds[0]
    assert d == {"seq": 1, "person": "M K Srinivasan", "category": "Promoter Group", "instrument": "Equity",
                 "txn_type": "Pledge Revoke", "mode": "Pledge Release", "n_securities": 60490, "value": 0.0,
                 "pre_pct": 0.0006, "post_pct": 0.0006, "txn_from": "2026-09-05", "txn_to": "2026-09-05",
                 "exchange": "NSE"}


def test_parse_pit_xml_handles_two_disclosures_and_missing_values():
    xml = (FIX / "pit.xml").read_text(encoding="utf-8")
    marker = '<xbrli:context id="Disclosure1">'
    second = (marker + xml.split(marker, 1)[1]).replace("</xbrli:xbrl>", "")
    second = (second.replace("Disclosure1", "Disclosure2").replace("M K Srinivasan", "Someone Else")
              .replace(">Pledge Revoke<", ">Sell<").replace(">Pledge Release<", ">Market Sale<")
              .replace("<in-bse-co:SecuritiesAcquiredOrDisposedValueOfSecurity", "<in-bse-co:Nope"))
    two = xml.replace("</xbrli:xbrl>", "") + second + "</xbrli:xbrl>"
    ds = parse_pit_xml(two)
    assert [d["seq"] for d in ds] == [1, 2]
    assert ds[1]["person"] == "Someone Else" and ds[1]["txn_type"] == "Sell" and ds[1]["mode"] == "Market Sale"
    assert ds[1]["value"] is None
    assert parse_pit_xml("<xbrli:xbrl xmlns:xbrli='http://www.xbrl.org/2003/instance'/>") == []


def test_insider_rows_join_filing_and_disclosures_on_app_id():
    filing = parse_pit_filings(FILINGS)[0]
    rows = insider_rows(filing, parse_pit_xml((FIX / "pit.xml").read_text(encoding="utf-8")))
    assert len(rows) == 1
    r = rows[0]
    assert (r["app_id"], r["seq"], r["symbol"], r["broadcast_at"]) == (3187, 1, "KARURVYSYA", "2026-09-10T20:46:52")
    assert r["category"] == "Promoter Group" and r["mode"] == "Pledge Release" and r["xml_url"] == filing["xml_url"]
    assert r["regulation"] == "Regulation 7 (2)"
