"""Test-first spec for realized buyback acceptance (post-buyback public announcements)."""
import pytest

from scanner.buyback_results import (
    is_result_announcement, parse_post_buyback, ss_acceptance, results_row, pick_result)

# SEBI-format response table, as PyMuPDF flattens it (IITL, Sep 2026; real text)
IITL = ("... considered a total of 21 valid bids for 16,22,822 Equity Shares in response to the Buyback, "
        "which is approximately 0.9737 times the maximum number of Equity Shares proposed to be bought back. "
        "Category of Shareholders No. of Equity Shares reserved in Buyback No. of Valid Bids Total Valid Equity "
        "Shares Validly Tendered % Response Reserved category for Small Shareholders 2,50,001 17 401 0.16 "
        "General category of other Eligible Shareholders 14,16,666 4 16,22,421 114.52 Total 16,66,667 21 "
        "16,22,822 97.37 2.4. All valid bids were considered ...")

# Gandhi Special Tubes (from the scanned page, typed): oversubscribed general category
GANDHI = ("Category of Shareholders No. of Equity Shares reserved in the Buyback No. of Valid Bids Total No. of "
          "Equity Shares Validly Tendered % Response Reserved Category for Small Shareholders 1,30,215 235 16,520 "
          "12.69% General Category for other Shareholders 7,37,885 38 15,52,595 210.41% Total 8,68,100 273 "
          "15,69,115 180.75%")

# Older wording without the bids column
NOBIDS = ("Category of Shareholders No. of Equity Shares reserved Total Equity Shares Validly Tendered % Response "
          "Reserved category for Small Shareholders 4,50,000 9,00,000 200.00 General Category for other Eligible "
          "Shareholders 25,50,000 30,00,000 117.65 Total 30,00,000 39,00,000 130.00")


def test_parse_iitl_four_columns():
    r = parse_post_buyback(IITL)
    assert r["ss_reserved"] == 250001 and r["ss_bids"] == 17 and r["ss_tendered"] == 401
    assert r["ss_response_pct"] == pytest.approx(0.16)
    assert r["gen_reserved"] == 1416666 and r["gen_tendered"] == 1622421
    assert r["total_reserved"] == 1666667 and r["total_tendered"] == 1622822
    assert r["times_subscribed"] == pytest.approx(0.9737)


def test_parse_gandhi_percent_signs_and_wording():
    r = parse_post_buyback(GANDHI)
    assert r["ss_reserved"] == 130215 and r["ss_bids"] == 235 and r["ss_tendered"] == 16520
    assert r["ss_response_pct"] == pytest.approx(12.69)
    assert r["gen_tendered"] == 1552595
    assert r["total_reserved"] == 868100 and r["total_tendered"] == 1569115
    assert r["times_subscribed"] == pytest.approx(1.8075, abs=1e-3)   # derived: total tendered / reserved


def test_parse_without_bids_column():
    r = parse_post_buyback(NOBIDS)
    assert r["ss_reserved"] == 450000 and r["ss_tendered"] == 900000 and r["ss_bids"] is None
    assert r["ss_response_pct"] == pytest.approx(200.0)
    assert r["total_tendered"] == 3900000


def test_parse_none_on_scanned_or_unrelated_text():
    assert parse_post_buyback("") is None
    assert parse_post_buyback("Gandhi Special Tubes Limited CIN L27104MH1985PLC036004 To BSE Limited") is None


def test_parse_rejects_inconsistent_table():
    # response % must agree with tendered / reserved (guards a mis-aligned column pick)
    bad = ("Reserved category for Small Shareholders 2,50,001 17 401 55.00 General category 14,16,666 4 "
           "16,22,421 114.52 Total 16,66,667 21 16,22,822 97.37")
    assert parse_post_buyback(bad) is None


def test_small_shareholder_acceptance():
    # undersubscribed reserved pool -> everything accepted
    assert ss_acceptance({"ss_reserved": 250001, "ss_tendered": 401, "total_reserved": 1666667,
                          "total_tendered": 1622822}) == pytest.approx(1.0)
    # oversubscribed reserved pool, whole offer oversubscribed -> pro-rata on the reserved pool
    assert ss_acceptance({"ss_reserved": 450000, "ss_tendered": 900000, "total_reserved": 3000000,
                          "total_tendered": 3900000}) == pytest.approx(0.5)
    # reserved pool oversubscribed but the whole offer is not -> spill-over accepts everything
    assert ss_acceptance({"ss_reserved": 100, "ss_tendered": 150, "total_reserved": 1000,
                          "total_tendered": 800}) == pytest.approx(1.0)
    assert ss_acceptance({"ss_reserved": 100, "ss_tendered": 0, "total_reserved": 1000,
                          "total_tendered": 800}) is None


def test_is_result_announcement():
    assert is_result_announcement({"desc": "Post Buyback Public Announcement", "attchmntText": ""})
    assert is_result_announcement({"desc": "Copy of Newspaper Publication",
                                   "attchmntText": "Copy of Newspaper Publication- Post Buyback Newspaper Advertisement"})
    assert is_result_announcement({"desc": "Closure of Buy Back", "attchmntText": "x"})
    assert not is_result_announcement({"desc": "Buyback", "attchmntText": "Letter of offer"})
    assert not is_result_announcement({"desc": "Copy of Newspaper Publication",
                                       "attchmntText": "Public Announcement for buyback"})


def test_pick_result_prefers_post_buyback_pa_then_closure():
    rows = [{"desc": "Closure of Buy Back", "attchmntText": "", "attchmntFile": "c.pdf", "an_dt": "17-Sep-2026 19:00:46"},
            {"desc": "Copy of Newspaper Publication", "attchmntText": "Post Buyback PA", "attchmntFile": "n.pdf",
             "an_dt": "11-Sep-2026 10:19:32"},
            {"desc": "Post Buyback Public Announcement", "attchmntText": "", "attchmntFile": "p.pdf",
             "an_dt": "10-Sep-2026 10:00:00"}]
    assert [r["attchmntFile"] for r in pick_result(rows)] == ["p.pdf", "n.pdf", "c.pdf"]


def test_results_row_shape():
    parsed = parse_post_buyback(IITL)
    row = results_row(7, parsed, url="https://x/y.pdf", seq_id=123, parsed_by="rule_v1")
    assert row["buyback_id"] == 7 and row["ss_acceptance"] == pytest.approx(1.0)
    assert row["source_url"] == "https://x/y.pdf" and row["source_seq_id"] == 123
    assert row["needs_manual"] is False and row["parsed_by"] == "rule_v1"
    pending = results_row(7, None, url="https://x/scan.pdf", seq_id=124)
    assert pending["needs_manual"] is True and pending["ss_acceptance"] is None


# --- real layouts the fixed-column regex missed (2026-09-24 backfill) ------------------

ZYDUS = ("Particulars Shares reserved received In the Shares Validly (%) In the Buyback categorv Tendered "
         "Reserved Category for Small Shareholder 8,95,523 38,006 1 18,47,289 206.28 General Category for other "
         "Eligible Shareholders 50.74.626 7,302 4,98.39,899 982.14 Total 59,70,149 45,308 5,16,87,188 865.76 2.5 All")

GARFIBRES = ("Reserved Category for 78,750 59,846 1,92,665 59,846 1,92,444 244.37% Small Shareholders General Category "
             "for all 4,46,250 3,279 57, 14,442 3,279 57,14,439 1,280.55% Other Eligible Shareholders Not in Master "
             "file* - 148 389 - Total 5,25,000 63,273 59,07,496 63,125 59,06,883 1,125.13% *148 bids")

FDC = ("No. of times of Response | No. of Equity Shares Accepted 1. Reserved category for Small Shareholders 4,65,000 "
       "35,174 22,57,269 4.85 4,65,000 2. General category for all other Eligible Shareholders 26,35,000 2,891 "
       "1,40,80,739 5.34 26,35,000 Total 31,00,000 38,065 1,63,38,008 5.27 31,00,000 Note:")

ORBTEXP = ("Reserved Category for Small Shareholders 90,000 5,634 4,81,879 5.35 General Category for all other "
           "Eligible Shareholders 5,10,000 246 2,34,89,160 46.06 TOTAL 39.95 6,00,000 5,880 2,39,71,039 24.")


def test_parse_ocr_noise_between_columns():
    r = parse_post_buyback(ZYDUS)
    assert r["ss_reserved"] == 895523 and r["ss_tendered"] == 1847289 and r["ss_bids"] == 38006
    assert r["ss_response_pct"] == pytest.approx(206.28)
    assert r["total_reserved"] == 5970149 and r["total_tendered"] == 51687188


def test_parse_label_after_numbers_and_extra_columns():
    r = parse_post_buyback(GARFIBRES)
    assert r["ss_reserved"] == 78750 and r["ss_tendered"] == 192444
    assert r["ss_response_pct"] == pytest.approx(244.37)
    assert r["total_reserved"] == 525000 and r["total_tendered"] == 5906883


def test_parse_times_instead_of_percent():
    r = parse_post_buyback(FDC)
    assert r["ss_reserved"] == 465000 and r["ss_tendered"] == 2257269 and r["ss_bids"] == 35174
    assert r["ss_response_pct"] == pytest.approx(485.43, abs=0.5)
    assert r["total_tendered"] == 16338008
    r = parse_post_buyback(ORBTEXP)
    assert r["ss_reserved"] == 90000 and r["ss_tendered"] == 481879
    assert r["total_reserved"] == 600000 and r["total_tendered"] == 23971039


# --- validity checks (2026-09-24 backfill false positives) -------------------------------

TEAMLEASE = ("uyback (A) (B) than Record category (C)** | received to the Date** total no. of Equity Shares to be bought "
             "back) (C/A) | General Category | 278,688 887 | 49.,27.680 | 387 _751 | 4926929 | = 17.68 | | Small "
             "Shareholder Category | 49,181 46,951 | 1,34,530 | | 46,951 1,312 | 1,33,218 271 | | Not in master file? "
             "| a 193 | 2,546 | 0 9 | Q | 0 | Total 3,27,869 47,531 50,64,756 47,338 2,063 | 50,60,147 | 15.43 |")

ZYDUS_BAD_TOTAL = ("Reserved Category for Small Shareholder 8,95,523 38,006 18,47,289 206.28 General Category for other "
                   "Eligible Shareholders 50,74,626 7,302 4,98,39,899 982.14 Total 788 3 0.38 2.5 All valid bids")


def test_small_row_never_borrows_the_general_row():
    # the small-shareholder numbers are unreadable; the general row precedes the label
    assert parse_post_buyback(TEAMLEASE) is None


def test_duplicate_small_and_general_rows_rejected():
    dup = ("Reserved Category for Small Shareholders 6,36,735 3,692 7,36,545 115.68 General Category "
           "6,36,735 3,692 7,36,545 115.68 Total 81,111 14,122 17.41")
    assert parse_post_buyback(dup) is None


def test_inconsistent_total_is_dropped_not_trusted():
    r = parse_post_buyback(ZYDUS_BAD_TOTAL)
    assert r["ss_reserved"] == 895523 and r["gen_reserved"] == 5074626
    assert r["total_reserved"] is None and r["total_tendered"] is None
    # with the total gone, acceptance is the pro-rata on the reserved pool (not 100%)
    assert ss_acceptance(r) == pytest.approx(895523 / 1847289)


def test_total_must_be_the_sum_of_the_categories_when_both_read():
    r = parse_post_buyback(IITL)
    assert r["total_reserved"] == 1666667            # 2,50,001 + 14,16,666 -> kept
    r = parse_post_buyback(GANDHI)
    assert r["total_reserved"] == 868100             # 1,30,215 + 7,37,885 -> kept
