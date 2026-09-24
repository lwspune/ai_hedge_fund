"""Test-first spec for the company master (I1): NSE static CSV parsers + row building."""
from datetime import date

from scanner.master import (
    parse_equity_list, parse_symbol_changes, parse_delisted, parse_index_list,
    resolve_symbol, build_companies,
)

EQUITY_L = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "20MICRONS,20 Microns Limited,EQ,06-OCT-2008,5,1,INE144J01027,5\n"
    "HDFCBANK,HDFC Bank Limited,EQ,08-NOV-1995,1,1,INE040A01034,1\n"
    "TINYCO,Tiny Co Limited,BE,01-JAN-2020,10,1,INE999Z01011,10\n"
    "BADISIN,Bad Isin Limited,EQ,01-JAN-2020,10,1,NOTANISIN,10\n"
    ",Blank Symbol Limited,EQ,01-JAN-2020,10,1,INE111A01011,10\n"
)

SYMBOL_CHANGES = (
    " NIPPON INDIA MF - Plan E -  GO,RDAXEDG,NDAXEDG,30-OCT-2019\n"
    "iGate Global Solutions Limited,MASCOT,IGS,07-AUG-2003\n"
    "iGate Global Solutions Limited,IGS,IGATE,01-JAN-2010\n"
    ",780LTFL30,799LTFL30,19-FEB-2025\n"
    "Garbage Row,ONLYONE,,01-JAN-2010\n"
    "Bad Date Ltd,AAA,BBB,notadate\n"
)

DELISTED = (
    "Symbol,Company,Delisted Date,Type of Delisting,,,,,\n"
    "CABOTINDIA,Cabot India Ltd,15-Apr-02,Voluntary Delisting ,,,,,\n"
    "HEXAWARE,Hexaware Technologies Limited,09-Nov-20,Voluntary Delisting ,,,,,\n"
    "20MICRONS,Relisted Later Ltd,01-Jan-05,Compulsory,,,,,\n"
)

NIFTY50 = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "HDFC Bank Ltd.,Financial Services,HDFCBANK,EQ,INE040A01034\n"
)
SMALLCAP = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "20 Microns Ltd.,Chemicals,20MICRONS,EQ,INE144J01027\n"
)


def test_parse_equity_list_strips_headers_and_guards_bad_rows():
    rows = parse_equity_list(EQUITY_L)
    by = {r["symbol"]: r for r in rows}
    assert set(by) == {"20MICRONS", "HDFCBANK", "TINYCO"}  # bad ISIN + blank symbol dropped
    assert by["20MICRONS"] == {
        "symbol": "20MICRONS", "name": "20 Microns Limited", "series": "EQ",
        "listing_date": date(2008, 10, 6), "face_value": 5.0, "isin": "INE144J01027",
    }
    assert by["TINYCO"]["series"] == "BE"


def test_parse_symbol_changes_headerless_and_guarded():
    rows = parse_symbol_changes(SYMBOL_CHANGES)
    assert [(r["old_symbol"], r["new_symbol"]) for r in rows] == [
        ("RDAXEDG", "NDAXEDG"), ("MASCOT", "IGS"), ("IGS", "IGATE"), ("780LTFL30", "799LTFL30")]
    assert rows[0]["company"] == "NIPPON INDIA MF - Plan E -  GO"
    assert rows[1]["changed_on"] == date(2003, 8, 7)
    assert rows[3]["company"] is None


def test_parse_delisted_two_digit_years():
    rows = parse_delisted(DELISTED)
    assert rows[0] == {"symbol": "CABOTINDIA", "name": "Cabot India Ltd",
                       "delisted_on": date(2002, 4, 15), "reason": "Voluntary Delisting"}
    assert rows[1]["delisted_on"] == date(2020, 11, 9)


def test_parse_index_list():
    assert parse_index_list(NIFTY50) == [
        {"symbol": "HDFCBANK", "industry": "Financial Services", "isin": "INE040A01034"}]


def test_resolve_symbol_follows_chain_and_survives_cycles():
    changes = parse_symbol_changes(SYMBOL_CHANGES)
    assert resolve_symbol("MASCOT", changes) == "IGATE"
    assert resolve_symbol("IGS", changes) == "IGATE"
    assert resolve_symbol("RELIANCE", changes) == "RELIANCE"
    cyc = [{"old_symbol": "A", "new_symbol": "B", "changed_on": date(2020, 1, 1)},
           {"old_symbol": "B", "new_symbol": "A", "changed_on": date(2021, 1, 1)}]
    assert resolve_symbol("A", cyc) in {"A", "B"}  # terminates


def test_build_companies_merges_indices_industry_and_delisted():
    rows = build_companies(
        parse_equity_list(EQUITY_L),
        {"nifty50": parse_index_list(NIFTY50), "smallcap250": parse_index_list(SMALLCAP)},
        parse_delisted(DELISTED),
    )
    by = {r["symbol"]: r for r in rows}
    hdfc = by["HDFCBANK"]
    assert hdfc["industry"] == "Financial Services"
    assert hdfc["indices"] == ["nifty50"]
    assert hdfc["is_financial"] is True
    assert hdfc["status"] == "listed" and hdfc["delisted_on"] is None
    assert hdfc["listing_date"] == "1995-11-08"  # JSON-ready ISO string
    assert by["20MICRONS"]["is_financial"] is False
    assert by["20MICRONS"]["status"] == "listed"  # currently listed wins over old delisting
    assert by["TINYCO"]["industry"] is None and by["TINYCO"]["is_financial"] is None
    hex_ = by["HEXAWARE"]
    assert hex_["status"] == "delisted" and hex_["delisted_on"] == "2020-11-09"
    assert hex_["isin"] is None and hex_["indices"] == []


SME_L = (
    "SYMBOL,NAME_OF_COMPANY,SERIES,DATE_OF_LISTING,PAID_UP_VALUE,ISIN_NUMBER,FACE_VALUE,\n"
    "VIGOR,Vigor Plast India Limited,ST,12-Sep-25,10,INE0XYZ01011,10,\n"
    "20MICRONS,Migrated Duplicate,SM,01-Jan-08,10,INE144J01027,5,\n"
)


def test_parse_equity_list_handles_sme_file_format():
    rows = parse_equity_list(SME_L)
    assert rows[0] == {"symbol": "VIGOR", "name": "Vigor Plast India Limited", "series": "ST",
                       "listing_date": date(2025, 9, 12), "face_value": 10.0, "isin": "INE0XYZ01011"}


def test_build_companies_includes_sme_and_mainboard_wins_duplicates():
    eq = parse_equity_list(EQUITY_L) + parse_equity_list(SME_L)
    rows = build_companies(eq, {}, [])
    by = {r["symbol"]: r for r in rows}
    assert by["VIGOR"]["series"] == "ST"
    assert by["20MICRONS"]["name"] == "20 Microns Limited"      # mainboard row kept
    assert sum(r["symbol"] == "20MICRONS" for r in rows) == 1


def test_build_companies_dedupes_isin_across_lists():
    """A stock that migrated SME -> mainboard under a new symbol shares its ISIN (unique in DB)."""
    sme = ("SYMBOL,NAME_OF_COMPANY,SERIES,DATE_OF_LISTING,PAID_UP_VALUE,ISIN_NUMBER,FACE_VALUE,\n"
           "OLDSME,Old Sme Name,SM,01-Jan-18,10,INE144J01027,5,\n")
    rows = build_companies(parse_equity_list(EQUITY_L) + parse_equity_list(sme), {}, [])
    assert [r["symbol"] for r in rows if r["isin"] == "INE144J01027"] == ["20MICRONS"]


# --- WP4: industry fallback, delisting by diff, renames, truncation guard -----------------

TODAY = date(2026, 9, 27)


def _prev(symbol, isin, name="Old Name"):
    return {"symbol": symbol, "name": name, "series": "EQ", "listing_date": "2010-01-01",
            "face_value": 10.0, "isin": isin, "industry": None, "industry_source": None,
            "indices": [], "is_financial": None, "status": "listed", "delisted_on": None,
            "delist_source": None, "last_seen_listed": "2026-09-20"}


def test_industry_falls_back_to_screener_sector():
    rows = build_companies(parse_equity_list(EQUITY_L), {"nifty50": parse_index_list(NIFTY50)}, [],
                           screener_sectors={"TINYCO": "Financial Services", "20MICRONS": "Commodities",
                                             "HDFCBANK": "Banks??"}, today=TODAY)
    by = {r["symbol"]: r for r in rows}
    assert by["HDFCBANK"]["industry"] == "Financial Services"          # niftyindices wins
    assert by["HDFCBANK"]["industry_source"] == "niftyindices"
    assert by["TINYCO"]["industry"] == "Financial Services" and by["TINYCO"]["is_financial"] is True
    assert by["TINYCO"]["industry_source"] == "screener"
    assert by["20MICRONS"]["industry"] == "Commodities" and by["20MICRONS"]["is_financial"] is False
    assert by["20MICRONS"]["last_seen_listed"] == "2026-09-27"


def test_listed_rows_clear_delist_fields_and_tag_csv_delistings():
    rows = build_companies(parse_equity_list(EQUITY_L), {}, parse_delisted(DELISTED), today=TODAY)
    by = {r["symbol"]: r for r in rows}
    assert by["HDFCBANK"]["delist_source"] is None
    assert by["HEXAWARE"]["delist_source"] == "nse_delisted_csv"


def test_symbol_missing_from_today_lists_is_delisted_by_diff():
    prev = [_prev("GONECO", "INE555G01011", "Gone Co Ltd"), _prev("HDFCBANK", "INE040A01034")]
    rows = build_companies(parse_equity_list(EQUITY_L), {}, [], previous_listed=prev, today=TODAY)
    by = {r["symbol"]: r for r in rows}
    g = by["GONECO"]
    assert (g["status"], g["delisted_on"], g["delist_source"]) == ("delisted", "2026-09-27", "equity_l_diff")
    assert g["name"] == "Gone Co Ltd" and g["isin"] == "INE555G01011"   # history kept, row never deleted
    assert g["last_seen_listed"] == "2026-09-20"
    assert by["HDFCBANK"]["status"] == "listed"


def test_renamed_symbol_old_row_delisted_and_releases_isin_first():
    """The new symbol carries the same ISIN (unique in DB): the old row must give it up, and be
    written before the new one."""
    prev = [_prev("OLDMICRO", "INE144J01027", "20 Microns (old name)")]
    changes = [{"old_symbol": "OLDMICRO", "new_symbol": "20MICRONS", "changed_on": date(2026, 9, 25)}]
    rows = build_companies(parse_equity_list(EQUITY_L), {}, [], previous_listed=prev, changes=changes,
                           today=TODAY)
    old = next(r for r in rows if r["symbol"] == "OLDMICRO")
    assert old["status"] == "delisted" and old["delist_source"] == "equity_l_diff"
    assert old["isin"] is None and old["name"] == "20 Microns (old name)"
    assert resolve_symbol("OLDMICRO", changes) == "20MICRONS"
    order = [r["symbol"] for r in rows]
    assert order.index("OLDMICRO") < order.index("20MICRONS")


def test_previously_delisted_by_diff_relists_cleanly():
    prev = []  # not listed last week
    rows = build_companies(parse_equity_list(EQUITY_L), {}, [], previous_listed=prev, today=TODAY)
    h = next(r for r in rows if r["symbol"] == "TINYCO")
    assert (h["status"], h["delisted_on"], h["delist_source"]) == ("listed", None, None)


def test_list_size_guard():
    import pytest
    from scanner.master import TruncatedList, check_list_sizes
    check_list_sizes(2400, 650)
    with pytest.raises(TruncatedList):
        check_list_sizes(1700, 650)
    with pytest.raises(TruncatedList):
        check_list_sizes(2400, 250)


def test_delisting_sanity_cap():
    import pytest
    from scanner.master import TooManyDelistings, check_delistings
    rows = [{"status": "delisted", "delist_source": "equity_l_diff", "delisted_on": "2026-09-27"}] * 51
    with pytest.raises(TooManyDelistings):
        check_delistings(rows, TODAY)
    check_delistings(rows[:50], TODAY)
