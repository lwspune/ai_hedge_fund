"""Test-first spec for the NSE filings index (F1)."""
from scanner.filings import keep, parse_announcements


def _raw(**kw):
    base = {"seq_id": "106790313", "symbol": "ANURAS", "sm_isin": "INE930P01018",
            "sm_name": "Anupam Rasayan India Limited", "desc": "Investor Presentation",
            "attchmntText": "Anupam Rasayan India Limited has informed the Exchange about investor presentation",
            "an_dt": "23-Sep-2026 23:55:16",
            "attchmntFile": "https://nsearchives.nseindia.com/corporate/ANURAS_23092026235444_PPT.pdf",
            "attFileSize": "372.97 KB", "hasXbrl": "True"}
    return {**base, **kw}


def test_parse_announcements_normalises_rows():
    rows = parse_announcements([_raw()])
    assert rows == [{
        "seq_id": 106790313, "symbol": "ANURAS", "isin": "INE930P01018",
        "company": "Anupam Rasayan India Limited", "category": "Investor Presentation",
        "subject": "Anupam Rasayan India Limited has informed the Exchange about investor presentation",
        "disclosed_at": "2026-09-23T23:55:16+05:30",
        "attachment_url": "https://nsearchives.nseindia.com/corporate/ANURAS_23092026235444_PPT.pdf",
        "size_kb": 372.97, "has_xbrl": True}]


def test_parse_announcements_guards_and_units():
    rows = parse_announcements([
        _raw(seq_id="1", attFileSize="2.5 MB", attchmntFile="-", hasXbrl="False"),
        _raw(seq_id="x"),                       # no numeric id -> dropped
        _raw(seq_id="2", an_dt="garbage"),       # no timestamp -> dropped
        _raw(seq_id="3", symbol=""),             # no symbol -> dropped
    ])
    assert [r["seq_id"] for r in rows] == [1]
    assert rows[0]["size_kb"] == 2560.0 and rows[0]["attachment_url"] is None and rows[0]["has_xbrl"] is False


def test_keep_material_categories_and_keyword_filtered_catch_alls():
    assert keep({"category": "Investor Presentation", "subject": "x"})
    assert keep({"category": "Bagging/Receiving of orders/contracts", "subject": "x"})
    assert keep({"category": "Analysts/Institutional Investor Meet/Con. Call Updates", "subject": "x"})
    assert not keep({"category": "Shareholders meeting", "subject": "order"})
    assert not keep({"category": "Trading Window", "subject": "x"})
    assert keep({"category": "General Updates", "subject": "Company received Letter of Award worth Rs 120 Cr"})
    assert keep({"category": "Updates", "subject": "Commissioning of new plant capacity"})
    assert not keep({"category": "General Updates", "subject": "Loss of share certificate"})


def test_subject_capped_at_300_chars():
    """WP8: the table's biggest column; the full text lives in the PDF."""
    rows = parse_announcements([_raw(attchmntText="x" * 700)])
    assert len(rows[0]["subject"]) == 300


def test_kpi_extraction_floor_is_2024():
    """WP8: order-win / KPI history back to the category's start (order_wins full n)."""
    import inspect
    import scripts.extract_kpis as ek
    assert '"2024-01-01"' in inspect.getsource(ek.main)


def test_keep_buyback_lifecycle_categories():
    """The buyback lifecycle on NSE: record date -> public announcement -> letter of offer ->
    post-buyback announcement (realized acceptance) -> closure. All kept (2026-09-24)."""
    assert keep({"category": "Post Buyback Public Announcement", "subject": "x"})
    assert keep({"category": "Closure of Buy Back", "subject": "x"})
    assert keep({"category": "Buyback", "subject": "x"})
    assert keep({"category": "Public Announcement - Buyback of Shares", "subject": "x"})
    # generic categories only when the subject is about a buyback
    assert keep({"category": "Record Date", "subject": "Record date for the purpose of Buyback is 21-Aug-2026"})
    assert not keep({"category": "Record Date", "subject": "Record date for the purpose of Dividend"})
    assert keep({"category": "Copy of Newspaper Publication", "subject": "Post Buyback Newspaper advertisement"})
    assert keep({"category": "Copy of Newspaper Publication", "subject": "Post Buy-back Public Announcement"})
    assert not keep({"category": "Copy of Newspaper Publication", "subject": "Notice of AGM"})
    assert keep({"category": "Updates", "subject": "Submission of Letter of Offer for buy back of shares"})
