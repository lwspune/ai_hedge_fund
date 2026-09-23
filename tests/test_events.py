"""Test-first spec for the corporate-events calendar (infra I3)."""
from datetime import date

from scanner.events import (
    classify_action, corp_action_events, parse_fo_ban, parse_ipo_page, ipo_events, dedupe_events,
)


# --- NSE corporate actions ---------------------------------------------------

def test_classify_bonus_split_rights_consolidation():
    assert classify_action("Bonus 3:1") == ("bonus", {"ratio": "3:1"})
    assert classify_action("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share") == \
        ("split", {"from_fv": 10.0, "to_fv": 1.0})
    assert classify_action("Rights 1:5 @ Premium Rs 245/-") == ("rights", {"ratio": "1:5", "premium": 245.0})
    assert classify_action("Rights 2: 7 @ Premium Rs 10/-") == ("rights", {"ratio": "2:7", "premium": 10.0})
    assert classify_action("Consolidation Of Equity Shares From Re 1 Per Share To Rs 10 Per Share") == \
        ("consolidation", {"from_fv": 1.0, "to_fv": 10.0})


def test_classify_dividends_sum_amounts_and_flag_special():
    assert classify_action("Dividend - Rs 5 Per Share") == \
        ("dividend", {"amount": 5.0, "interim": False, "special": False})
    assert classify_action("Interim Dividend - Re 0.50 Per Share") == \
        ("dividend", {"amount": 0.5, "interim": True, "special": False})
    assert classify_action("Dividend - Rs 10 Per Share & Special Dividend - Rs 2.5 Per Share") == \
        ("dividend", {"amount": 12.5, "interim": False, "special": True})
    assert classify_action("Annual General Meeting/Dividend - Rs 3 Per Share")[1]["amount"] == 3.0


def test_classify_other_types_and_ignored_subjects():
    assert classify_action("Buy Back") == ("buyback", {})
    assert classify_action("Demerger") == ("demerger", {})
    assert classify_action("Annual General Meeting") is None
    assert classify_action("Extra Ordinary General Meeting") is None
    assert classify_action("Scheme Of Arrangement - Bonus NCRPS 1:1") is None  # preference, not equity
    assert classify_action("Interest Payment") is None


def test_corp_action_events_filters_series_and_parses_dates():
    recs = [
        {"symbol": "ALLCARGO", "series": "EQ", "subject": "Bonus 3:1",
         "exDate": "02-Jan-2024", "recDate": "02-Jan-2024"},
        {"symbol": "83GS2040", "series": "GS", "subject": "Interest Payment",
         "exDate": "01-Jan-2024", "recDate": "01-Jan-2024"},
        {"symbol": "REGENCERAM", "series": "EQ", "subject": "Extra Ordinary General Meeting",
         "exDate": "02-Jan-2024", "recDate": "-"},
        {"symbol": "BADDATE", "series": "EQ", "subject": "Bonus 1:1", "exDate": "-", "recDate": "-"},
    ]
    assert corp_action_events(recs) == [{
        "symbol": "ALLCARGO", "event_type": "bonus", "event_date": "2024-01-02",
        "record_date": "2024-01-02", "details": {"ratio": "3:1"}, "source": "nse_ca"}]


def test_dedupe_events_sums_same_day_dividends_and_keeps_last_otherwise():
    ev = [
        {"symbol": "X", "event_type": "dividend", "event_date": "2025-01-01", "record_date": None,
         "details": {"amount": 2.0, "interim": True, "special": False}, "source": "nse_ca"},
        {"symbol": "X", "event_type": "dividend", "event_date": "2025-01-01", "record_date": None,
         "details": {"amount": 3.0, "interim": False, "special": True}, "source": "nse_ca"},
        {"symbol": "Y", "event_type": "bonus", "event_date": "2025-01-01", "record_date": None,
         "details": {"ratio": "1:1"}, "source": "nse_ca"},
        {"symbol": "Y", "event_type": "bonus", "event_date": "2025-01-01", "record_date": None,
         "details": {"ratio": "2:1"}, "source": "nse_ca"},
    ]
    out = {(e["symbol"], e["event_type"]): e for e in dedupe_events(ev)}
    assert len(out) == 2
    assert out[("X", "dividend")]["details"] == {"amount": 5.0, "interim": True, "special": True}
    assert out[("Y", "bonus")]["details"] == {"ratio": "2:1"}


# --- F&O ban -----------------------------------------------------------------

def test_parse_fo_ban():
    text = "Securities in Ban For Trade Date 22-SEP-2026:\n1,BANDHANBNK\n2,SAIL\n\n"
    assert parse_fo_ban(text) == (date(2026, 9, 22), ["BANDHANBNK", "SAIL"])
    assert parse_fo_ban("Securities in Ban For Trade Date 02-JAN-2024:\nNIL\n") == (date(2024, 1, 2), [])
    assert parse_fo_ban("<html>not found</html>") == (None, [])


# --- chittorgarh IPO pages -----------------------------------------------------

def _page(**kv):
    """Mimic chittorgarh's Next.js payload: JSON keys escaped with backslashes."""
    body = ",".join(f'\\"{k}\\":{v}' for k, v in kv.items())
    return f"<html><title>Vigor Plast IPO Date, Price, GMP</title><script>{{{body}}}</script></html>"


FULL = dict(
    nse_symbol='\\"VIGOR\\"', ipo_listing_at='\\"NSE SME\\"',
    issue_open_date='\\"September 4, 2025\\"', issue_close_date='\\"September 9, 2025\\"',
    timetable_boa_dt='\\"Wednesday, September 10, 2025\\"',
    timetable_listing_dt='\\"Friday, September 12, 2025\\"',
    timetable_anchor_lockin_end_dt_1='\\"October 9, 2025\\"',
    timetable_anchor_lockin_end_dt_2='\\"December 8, 2025\\"',
    issue_price_final="81", listing_day_closing_price="85.7",
    shares_offered_anchor_investor="873600", no_of_shares_allotted="2944000",
)


def test_parse_ipo_page_full():
    ipo = parse_ipo_page(_page(**FULL), 2400)
    assert ipo == {
        "chittorgarh_id": 2400, "symbol": "VIGOR", "company": "Vigor Plast", "board": "sme",
        "listing_at": "NSE SME", "issue_open": "2025-09-04", "issue_close": "2025-09-09",
        "boa_date": "2025-09-10", "listing_date": "2025-09-12", "issue_price": 81.0,
        "listing_close": 85.7, "anchor_shares": 873600, "shares_allotted": 2944000,
        "anchor_lockin_30": "2025-10-09", "anchor_lockin_90": "2025-12-08",
    }


def test_parse_ipo_page_mainboard_without_anchor_and_guards():
    kv = {**FULL, "ipo_listing_at": '\\"BSE, NSE\\"', "timetable_anchor_lockin_end_dt_1": '\\"\\"',
          "timetable_anchor_lockin_end_dt_2": '\\"\\"', "shares_offered_anchor_investor": "0"}
    ipo = parse_ipo_page(_page(**kv), 1)
    assert ipo["board"] == "mainboard"
    assert ipo["anchor_lockin_30"] is None and ipo["anchor_shares"] == 0
    # no symbol (BSE-only / not yet listed) or no price -> not stored
    assert parse_ipo_page(_page(**{**FULL, "nse_symbol": '\\"\\"'}), 2) is None
    assert parse_ipo_page(_page(**{**FULL, "issue_price_final": "0"}), 3) is None
    assert parse_ipo_page("<html>404</html>", 4) is None


def test_ipo_events_listing_and_lockins():
    ipo = parse_ipo_page(_page(**FULL), 2400)
    ev = ipo_events(ipo)
    assert [(e["event_type"], e["event_date"]) for e in ev] == [
        ("ipo_listing", "2025-09-12"), ("anchor_lockin_30", "2025-10-09"),
        ("anchor_lockin_90", "2025-12-08")]
    assert all(e["symbol"] == "VIGOR" and e["source"] == "chittorgarh" for e in ev)
    assert ev[1]["details"] == {"chittorgarh_id": 2400, "anchor_shares": 873600, "board": "sme"}
