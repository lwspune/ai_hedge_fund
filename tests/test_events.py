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
    rii="13.9786", qib="168.1944", nii="51.1658", times_subscribed='\\"67.84\\"',
    rii_offered="12057086", market_lot_size="59", total_application="2751564",
)


def test_parse_ipo_page_full():
    ipo = parse_ipo_page(_page(**FULL), 2400)
    assert ipo == {
        "chittorgarh_id": 2400, "symbol": "VIGOR", "company": "Vigor Plast", "board": "sme",
        "listing_at": "NSE SME", "issue_open": "2025-09-04", "issue_close": "2025-09-09",
        "boa_date": "2025-09-10", "listing_date": "2025-09-12", "issue_price": 81.0,
        "listing_close": 85.7, "anchor_shares": 873600, "shares_allotted": 2944000,
        "anchor_lockin_30": "2025-10-09", "anchor_lockin_90": "2025-12-08",
        "sub_retail": 13.9786, "sub_qib": 168.1944, "sub_nii": 51.1658, "sub_total": 67.84,
        "retail_shares_offered": 12057086, "lot_size": 59, "applications": 2751564,
    }


def test_parse_ipo_page_mainboard_without_anchor_and_guards():
    kv = {**FULL, "ipo_listing_at": '\\"BSE, NSE\\"', "timetable_anchor_lockin_end_dt_1": '\\"\\"',
          "timetable_anchor_lockin_end_dt_2": '\\"\\"', "shares_offered_anchor_investor": "0"}
    ipo = parse_ipo_page(_page(**kv), 1)
    assert ipo["board"] == "mainboard"
    assert ipo["anchor_lockin_30"] is None and ipo["anchor_shares"] == 0
    # subscription not published (older pages) -> None, never 0
    bare = {k: v for k, v in FULL.items() if k not in ("rii", "qib", "nii", "times_subscribed", "rii_offered",
                                                       "market_lot_size", "total_application")}
    ipo = parse_ipo_page(_page(**bare), 5)
    assert all(ipo[k] is None for k in ("sub_retail", "sub_qib", "sub_nii", "sub_total",
                                        "retail_shares_offered", "lot_size", "applications"))
    assert parse_ipo_page(_page(**{**FULL, "rii": "0", "market_lot_size": "0"}), 6)["sub_retail"] is None
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


class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class _Session:
    def __init__(self, resp):
        self.resp, self.kwargs = resp, None

    def get(self, url, **kw):
        self.kwargs = kw
        return self.resp


def test_fetch_ipo_treats_redirect_as_missing_page():
    """chittorgarh 307-redirects unknown ids to a listing page containing 'IPO'; following it
    made every id look real, so the frontier probe never gap-stopped."""
    from scanner.events import fetch_ipo
    s = _Session(_Resp(307, "<title>IPO list</title>"))
    assert fetch_ipo(99999, s) == (False, None)
    assert s.kwargs.get("allow_redirects") is False
    assert fetch_ipo(2400, _Session(_Resp(200, _page(**FULL))))[0] is True


def test_recheck_ids_recent_listings_and_missing_lockins():
    """Lock-in dates appear on chittorgarh after the page is first seen, so recent IPOs are
    re-read daily until they age out (or already have both dates)."""
    from datetime import date
    from scanner.events import recheck_ids
    rows = [
        {"chittorgarh_id": 1, "listing_date": "2026-09-01", "anchor_lockin_30": None, "anchor_lockin_90": None},
        {"chittorgarh_id": 2, "listing_date": "2026-09-01", "anchor_lockin_30": "2026-10-01", "anchor_lockin_90": "2026-11-30"},
        {"chittorgarh_id": 3, "listing_date": "2026-01-01", "anchor_lockin_30": None, "anchor_lockin_90": None},
        {"chittorgarh_id": 4, "listing_date": "2026-10-10", "anchor_lockin_30": None, "anchor_lockin_90": None},
    ]
    assert recheck_ids(rows, date(2026, 9, 24), days=120) == [1, 4]


# --- chittorgarh rights issues ------------------------------------------------------

RI = dict(
    company_name='\\"New Delhi Television Limited\\"', nse_symbol='\\"NDTV\\"', isin='\\"INE155G01029\\"',
    face_value='\\"u0026#8377;4 per share\\"', issue_price='\\"u0026#8377;82 per share\\"',
    entitlement_rights_equity_share="3", entitlement_fully_paid_equity_share="4",
    issue_size_in_shares_number="48353450",
    record_dt='\\"September 12, 2025\\"', rights_entitlements_credit_dt='\\"September 16, 2025\\"',
    issue_open_date='\\"September 22, 2025\\"', timetable_renunciation_dt='\\"October 3, 2025\\"',
    issue_close_date='\\"October 8, 2025\\"', timetable_allotment_dt='\\"October 9, 2025\\"',
    timetable_listing_dt='\\"October 13, 2025\\"', re_nse_symbol='\\"NDTVR\\"',
    amount_of_payment='\\"\\"', issue_withdraw_status="0",
)


def test_parse_rights_page_full():
    from scanner.events import parse_rights_page
    assert parse_rights_page(_page(**RI), 454) == {
        "chittorgarh_id": 454, "symbol": "NDTV", "company": "New Delhi Television Limited",
        "isin": "INE155G01029", "face_value": 4.0, "issue_price": 82.0,
        "ratio_rights": 3, "ratio_held": 4, "issue_size_shares": 48353450,
        "record_date": "2025-09-12", "re_credit_date": "2025-09-16", "issue_open": "2025-09-22",
        "renunciation_date": "2025-10-03", "issue_close": "2025-10-08",
        "allotment_date": "2025-10-09", "listing_date": "2025-10-13",
        "re_symbol": "NDTVR", "payment_terms": None, "application_amount": None,
        "partly_paid": False, "withdrawn": False,
    }


def test_parse_rights_page_partly_paid_withdrawn_and_guards():
    from scanner.events import parse_rights_page
    pp = parse_rights_page(_page(**{**RI, "amount_of_payment": '\\"u0026#8377;20.50 on application, balance in one or more calls\\"',
                                    "issue_withdraw_status": "1"}), 1)
    assert pp["partly_paid"] is True and pp["withdrawn"] is True
    assert pp["payment_terms"].startswith("₹20.50 on application")
    assert parse_rights_page(_page(**{**RI, "nse_symbol": '\\"\\"'}), 2) is None        # BSE-only
    assert parse_rights_page(_page(**{**RI, "issue_price": '\\"\\"'}), 3) is None
    assert parse_rights_page("<html>404</html>", 4) is None


def test_parse_rights_page_numeric_application_amount_means_partly_paid():
    from scanner.events import parse_rights_page
    r = parse_rights_page(_page(**{**RI, "amount_of_payment": '\\"124\\"', "issue_price": '\\"u0026#8377;165 per share\\"'}), 540)
    assert r["partly_paid"] is True and r["application_amount"] == 124.0
    full = parse_rights_page(_page(**{**RI, "amount_of_payment": '\\"82\\"'}), 541)
    assert full["partly_paid"] is False and full["application_amount"] == 82.0
    assert parse_rights_page(_page(**RI), 454)["application_amount"] is None


def test_parse_rights_page_re_symbol_in_symbol_field():
    """Older pages put the RE symbol (SATIN-RE) where the stock symbol belongs."""
    from scanner.events import parse_rights_page
    r = parse_rights_page(_page(**{**RI, "nse_symbol": '\\"SATIN-RE\\"', "re_nse_symbol": '\\"\\"'}), 1)
    assert r["symbol"] == "SATIN" and r["re_symbol"] == "SATIN-RE"


def test_rights_recheck_ids_recent_or_undated():
    from datetime import date
    from scanner.events import rights_recheck_ids
    rows = [{"chittorgarh_id": 1, "issue_close": "2026-09-01"},
            {"chittorgarh_id": 2, "issue_close": "2026-01-01"},
            {"chittorgarh_id": 3, "issue_close": None},
            {"chittorgarh_id": 4, "issue_close": "2026-10-15"}]
    assert rights_recheck_ids(rows, date(2026, 9, 24), days=45) == [1, 3, 4]


# --- WP6: trading holidays, board meetings / results, price-band changes -----------------

import json
from pathlib import Path

NSE_FX = Path(__file__).resolve().parent / "fixtures" / "nse"


def test_parse_holiday_master_cm_segment_only():
    from scanner.events import parse_holiday_master
    raw = json.loads((NSE_FX / "holidays.json").read_text(encoding="utf-8"))
    hol = parse_holiday_master(raw)
    assert date(2026, 1, 26) in hol and date(2026, 12, 25) in hol
    assert len(hol) == len(raw["CM"])
    assert parse_holiday_master({"FO": [{"tradingDate": "26-Jan-2026"}]}) == []


def test_calendar_rows_mark_holidays_and_skip_weekends():
    from scanner.events import calendar_rows
    rows = calendar_rows({date(2026, 1, 26): "Republic Day"}, 2026)
    by = {r["trade_date"]: r for r in rows}
    assert by["2026-01-26"]["is_trading"] is False and by["2026-01-26"]["description"] == "Republic Day"
    assert by["2026-01-27"]["is_trading"] is True
    assert "2026-01-24" not in by                      # Saturday: not a row
    assert len(rows) == 261                            # weekdays in 2026


def test_parse_board_meetings_one_event_per_meeting_results_win():
    from scanner.events import parse_board_meetings
    raw = json.loads((NSE_FX / "board_meetings.json").read_text(encoding="utf-8"))
    ev = {(e["symbol"], e["event_date"]): e for e in parse_board_meetings(raw)}
    mm = ev[("M&M", "2026-11-05")]
    assert mm["event_type"] == "results" and mm["source"] == "nse_bm"
    assert "Financial Results/Other business matters" in mm["details"]["purpose"]
    assert ev[("BAJFINANCE", "2026-10-01")]["event_type"] == "board_meeting"
    assert ev[("GANESHCP", "2026-09-28")]["event_type"] == "board_meeting"
    assert ev[("DEEPA", "2026-09-28")]["event_type"] == "results"
    assert len(ev) == len({(r["bm_symbol"], r["bm_date"]) for r in raw})


def test_parse_board_meetings_skips_junk_dates():
    from scanner.events import parse_board_meetings
    assert parse_board_meetings([{"bm_symbol": "X", "bm_date": "-", "bm_purpose": "Financial Results"}]) == []


def test_parse_band_changes():
    from scanner.events import parse_band_changes
    text = (NSE_FX / "eq_band_changes.csv").read_text(encoding="utf-8")
    ev = parse_band_changes(text, date(2026, 9, 24))
    assert ev[0] == {"symbol": "EIMCOELECO", "event_type": "band_change", "event_date": "2026-09-24",
                     "record_date": None, "details": {"from": 10.0, "to": 5.0, "series": "EQ"},
                     "source": "nse_band"}
    assert len(ev) == 4


def test_recheck_ids_also_waits_for_subscription():
    """Subscription figures appear after the issue closes: a recent IPO with lock-ins but no
    retail subscription is re-read too; one with both is left alone."""
    from datetime import date
    from scanner.events import recheck_ids
    both = {"anchor_lockin_30": "2026-10-01", "anchor_lockin_90": "2026-11-30"}
    rows = [{"chittorgarh_id": 5, "listing_date": "2026-09-01", **both, "sub_retail": None},
            {"chittorgarh_id": 6, "listing_date": "2026-09-01", **both, "sub_retail": 13.9}]
    assert recheck_ids(rows, date(2026, 9, 24), days=120) == [5]
