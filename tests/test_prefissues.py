"""Test-first spec for preferential allotments + their lock-in expiries (NSE further-issues API).

Listing-stage rows carry the allotment date, price and shares; the listing XBRL carries the exact
lock-in period per tranche (ICDR: 6 months non-promoter, 18 months promoter). Expiry = a
forced-supply date, the same mechanism as the validated anchor unlock (`lockin_expiry`)."""
from pathlib import Path

from scanner.prefissues import (
    add_months, lockin_expiry_events, lockin_months, parse_pref_list, parse_pref_ls_xbrl,
)

FIX = Path(__file__).parent / "fixtures"

IP = {"data": [
    {"appId": "71073", "boardResDate": "22-SEP-2026", "categoryOfAllottee": "Promoter & Non Promoter",
     "considerationBy": "Cash", "dateBrdResoln": "07-AUG-2026", "dateOfSubmission": "14-AUG-2026",
     "isin": "INE914E01040", "issueType": "Preferential", "nameOfTheCompany": "ALANKIT LIMITED",
     "nseSymbol": "ALANKIT", "stage": "In-Principle", "totalAmtRaised": "860000000",
     "xmlFileName": "https://nsearchives.nseindia.com/corporate/xbrl/PREF_ISSUE_IP_1714861_14082026063815_WEB.xml"},
    {"appId": "71074", "nseSymbol": "", "isin": "INE0", "stage": "In-Principle", "dateOfSubmission": "14-AUG-2026"},
]}
LS = {"data": [
    {"amountRaised": "3004835000", "appId": "72050", "boardResDate": "23-SEP-2026",
     "dateOfAllotmentOfShares": "10-SEP-2026", "dateOfListing": None, "dateOfSubmission": "21-SEP-2026",
     "dateOfTradingApproval": None, "isin": "INE900L01028", "issueType": "Preferential",
     "nameOfTheCompany": "MADHYA BHARAT AGRO PRODUCTS LIMITED", "nseSymbol": "MBAPL",
     "numberOfEquitySharesListed": "438134700", "offerPricePerSecurity": "145", "stage": "Listing Stage",
     "totalNumOfSharesAllotted": "20723000",
     "xmlFileName": "https://nsearchives.nseindia.com/corporate/xbrl/PREF_ISSUE_LS_1725934_21092026033812_WEB.xml"},
]}


def test_parse_pref_list_in_principle_rows():
    rows = parse_pref_list(IP, stage="in_principle")
    assert rows == [{"app_id": 71073, "symbol": "ALANKIT", "isin": "INE914E01040", "stage": "in_principle",
                     "board_res_date": "2026-08-07", "submission_date": "2026-08-14", "allotment_date": None,
                     "offer_price": None, "shares_allotted": None, "amount": 860000000.0,
                     "allottee_category": "Promoter & Non Promoter", "xml_url": IP["data"][0]["xmlFileName"]}]


def test_parse_pref_list_listing_rows():
    r = parse_pref_list(LS, stage="listing")[0]
    assert (r["app_id"], r["symbol"], r["stage"]) == (72050, "MBAPL", "listing")
    assert r["allotment_date"] == "2026-09-10" and r["offer_price"] == 145.0
    assert r["shares_allotted"] == 20723000 and r["amount"] == 3004835000.0
    assert r["board_res_date"] == "2026-09-23" and r["allottee_category"] is None


def test_parse_pref_ls_xbrl_reads_lockin_tranches():
    d = parse_pref_ls_xbrl((FIX / "prefls.xml").read_text(encoding="utf-8"))
    assert d == {"symbol": "MBAPL", "allotment_date": "2026-09-10", "offer_price": 145.0,
                 "shares_allotted": 20723000, "shares_listed": 438134700,
                 "lockins": [{"period": "Equity shares for 6 months", "months": 6, "shares": 20723000}]}


def test_lockin_months_parses_common_phrasings():
    assert lockin_months("Equity shares for 6 months") == 6
    assert lockin_months("Equity shares for 18 months") == 18
    assert lockin_months("1 year") == 12
    assert lockin_months("Three years") == 36
    assert lockin_months("Not applicable") is None


def test_add_months_clamps_to_month_end():
    assert add_months("2026-09-10", 6) == "2027-03-10"
    assert add_months("2026-08-31", 6) == "2027-02-28"
    assert add_months("2025-12-15", 18) == "2027-06-15"


def test_lockin_expiry_events_one_per_tranche_with_defaults():
    rows = [
        {"app_id": 72050, "symbol": "MBAPL", "stage": "listing", "allotment_date": "2026-09-10", "offer_price": 145.0,
         "shares_allotted": 20723000, "shares_listed": 438134700,
         "lockins": [{"period": "Equity shares for 6 months", "months": 6, "shares": 15000000},
                     {"period": "Equity shares for 18 months", "months": 18, "shares": 5723000}]},
        {"app_id": 1, "symbol": "NOXBRL", "stage": "listing", "allotment_date": "2026-01-31", "offer_price": 10.0,
         "shares_allotted": 100, "shares_listed": 1000, "lockins": []},            # no XBRL -> ICDR default 6m
        {"app_id": 2, "symbol": "IPONLY", "stage": "in_principle", "allotment_date": None, "lockins": []},
        {"app_id": 3, "symbol": "NA", "stage": "listing", "allotment_date": "2026-02-01", "shares_allotted": 5,
         "shares_listed": 100, "lockins": [{"period": "Not applicable", "months": None, "shares": 5}]},
    ]
    ev = lockin_expiry_events(rows)
    assert [(e["symbol"], e["event_date"], e["details"]["months"]) for e in ev] == [
        ("MBAPL", "2027-03-10", 6), ("MBAPL", "2028-03-10", 18), ("NOXBRL", "2026-07-31", 6)]
    e = ev[0]
    assert e["event_type"] == "pref_lockin_expiry" and e["source"] == "nse_pref" and e["record_date"] is None
    assert e["details"] == {"months": 6, "shares": 15000000, "allotment_date": "2026-09-10", "offer_price": 145.0,
                            "share_of_listed": 0.0342, "app_id": 72050, "default": False}
    assert ev[2]["details"]["default"] is True and ev[2]["details"]["shares"] == 100


def test_study_events_from_corporate_events_rows():
    from scanner.prefissues import study_events
    rows = [
        {"symbol": "MBAPL", "event_type": "pref_lockin_expiry", "event_date": "2027-03-10", "source": "nse_pref",
         "details": {"months": 6, "shares": 15000000, "allotment_date": "2026-09-10", "offer_price": 145.0,
                     "share_of_listed": 0.0342, "app_id": 72050, "default": False}},
        {"symbol": "NOXBRL", "event_type": "pref_lockin_expiry", "event_date": "2024-07-31", "source": "nse_pref",
         "details": {"months": 6, "shares": 100, "allotment_date": "2024-01-31", "offer_price": 10.0,
                     "share_of_listed": None, "app_id": 1, "default": True}},
        {"symbol": "OTHER", "event_type": "anchor_lockin_90", "event_date": "2024-07-31", "source": "chittorgarh",
         "details": {}},
    ]
    ev = study_events(rows)
    assert [e["symbol"] for e in ev] == ["MBAPL", "NOXBRL"]
    assert ev[0] == {"symbol": "MBAPL", "expiry": "2027-03-10", "months": 6, "shares": 15000000,
                     "allotment_date": "2026-09-10", "offer_price": 145.0, "share_of_listed": 0.0342,
                     "app_id": 72050, "default": False, "era": "2026-27"}
    assert ev[1]["era"] == "2024-25" and ev[1]["default"] is True
