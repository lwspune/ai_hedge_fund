"""Test-first spec for credit-rating extraction from NSE rating filings (Reg 30). Cases are the
wording of real filings from the 2024-26 sample — the formats to catch and the traps to reject."""
import pytest

from scanner.ratings import notch, parse_ratings, rating_rows


def _one(text, agency=None, term="long"):
    got = [r for r in parse_ratings(text) if r["term"] == term and (agency is None or r["agency"] == agency)]
    assert len(got) == 1, got
    assert got[0]["quote"] in " ".join(text.split())   # every row is checkable against the filing
    return got[0]


# ── the scale ─────────────────────────────────────────────────────────────────────────────
def test_notch_orders_long_and_short_term_scales():
    assert notch("AAA", "long") == 1 and notch("AA-", "long") == 4 and notch("BBB-", "long") == 10
    assert notch("D", "long") == 20
    assert notch("A1+", "short") == 1 and notch("A4", "short") == 8 and notch("D", "short") == 9
    assert notch("Baa3", "long") == 10 and notch("CCC+", "long") == 17   # global scales
    assert notch("XYZ", "long") is None


# ── each agency's format ──────────────────────────────────────────────────────────────────
def test_icra_bracket_format_with_upgrade_from_previous():
    text = ("This is to inform you that ICRA Limited has upgraded the credit rating for Rs. 110 crore bank "
            "facilities of the Company. Long Term - Fund Based Limits 105.00 [ICRA]A+ Upgraded from [ICRA]A "
            "and outlook revised to Stable from Positive Short Term – Non-Fund Based Limits 5.00 [ICRA]A1+ "
            "Upgraded from [ICRA]A1")
    lt = _one(text, "ICRA")
    assert (lt["rating"], lt["prev_rating"], lt["action"], lt["notch"]) == ("A+", "A", "upgraded", 5)
    st = _one(text, "ICRA", "short")
    assert (st["rating"], st["prev_rating"], st["action"]) == ("A1+", "A1", "upgraded")


def test_icra_reaffirmed_with_outlook_in_parentheses():
    text = ("ICRA has assigned the below ratings of Titan Company Limited on 27th August 2025 as follows: "
            "Long term – Fixed deposit programme 6,200.0 [ICRA]AAA (Stable); reaffirmed Short term – "
            "Commercial paper programme 2,500.0 [ICRA]A1+; reaffirmed")
    lt = _one(text, "ICRA")
    assert (lt["rating"], lt["outlook"], lt["action"]) == ("AAA", "Stable", "reaffirmed")


def test_care_downgrade_semicolon_outlook():
    text = ("inform you that CARE Ratings Limited ('CARE') has revised the credit ratings. CARE Ratings "
            "Long-term bank facilities CARE BB+; Stable | Downgraded; Outlook revised from Negative "
            "Long-term / short-term bank facilities CARE BB+; Stable / CARE A4+ Downgraded;")
    lt = _one(text, "CARE")
    assert (lt["rating"], lt["outlook"], lt["action"]) == ("BB+", "Stable", "downgraded")
    assert _one(text, "CARE", "short")["rating"] == "A4+"


def test_care_upgrade_with_previous_outlook():
    text = ("Long Term Bank Facilities 254.59 (Reduced from 305.64) CARE BBB; Stable Upgraded from CARE "
            "BBB-; Positive Short Term Bank Facilities 117.00 CARE A3+ Upgraded from CARE A3 Total")
    lt = _one(text, "CARE")
    assert (lt["rating"], lt["outlook"], lt["prev_rating"], lt["action"]) == ("BBB", "Stable", "BBB-", "upgraded")


def test_crisil_mixed_case_after_the_rebrand():
    text = ("Facilities Rated Rs. 604 Crore (Enhanced from Rs. 457 Crore) Long Term Rating Crisil A-/Stable "
            "(Outlook revised from 'Negative'; Rating Reaffirmed) Short Term Rating Crisil A2+ (Reaffirmed)")
    lt = _one(text, "CRISIL")
    assert (lt["rating"], lt["outlook"], lt["action"]) == ("A-", "Stable", "reaffirmed")
    assert _one(text, "CRISIL", "short")["rating"] == "A2+"


def test_india_ratings_ind_prefix():
    text = "India Ratings and Research has affirmed the Company's bank loans at IND AA-/Stable."
    lt = _one(text, "India Ratings")
    assert (lt["rating"], lt["outlook"], lt["action"]) == ("AA-", "Stable", "reaffirmed")


def test_acuite_pipe_outlook():
    text = ('Acuité has assigned a rating of "ACUITE AA | Stable" (ACUITE Double A with Stable Outlook) '
            "to the enhanced limits")
    lt = _one(text, "Acuite")
    assert (lt["rating"], lt["outlook"], lt["action"]) == ("AA", "Stable", "assigned")


def test_infomerics_and_spelled_out_short_term():
    text = ("Infomerics Ratings has assigned its rating for the Bank Loan Facilities: Long Term Bank Facilities "
            "IVR BBB-/ Negative (IVR Triple B Minus with Negative Outlook) Short-Term Bank Facilities IVR A3 "
            "(IVR A Three)")
    lt = _one(text, "Infomerics")
    assert (lt["rating"], lt["outlook"]) == ("BBB-", "Negative")
    assert _one(text, "Infomerics", "short")["rating"] == "A3"


def test_brickwork_bwr_prefix():
    assert _one("Brickwork has reaffirmed the rating of the Bonds at BWR AAA (CE)/Stable; and BWR AA/Stable "
                "for the issuer", "Brickwork")["rating"] == "AA"   # the CE one is the guarantee's, not ours


def test_watch_with_implications():
    text = ("ICRA has placed the credit ratings under Rating Watch with Positive Implications: Long-term–Fund-"
            "based –Term loans 382.00 382.00 [ICRA]A; Placed on Rating watch with positive implications.")
    lt = _one(text, "ICRA")
    assert (lt["rating"], lt["watch"], lt["action"]) == ("A", "positive", "watch")


def test_watch_abbreviation_and_previous_column_table():
    # "Current Ratings | Previous Ratings" table: the first token per agency is the current one
    text = ("Ratings Instrument / Facility Amount (Rs. crore) Current Ratings Previous Ratings Rating Action "
            "Fund Based Bank Facilities – Term Loan 107.41 IVR C / RWDI (IVR C with Rating Watch with "
            "Developing Implications) IVR BBB / RWDI (IVR Triple B with Rating Watch with Developing")
    lt = _one(text, "Infomerics")
    assert (lt["rating"], lt["watch"]) == ("C", "developing")


def test_previous_ratings_column_gives_the_previous_rating():
    text = ("Facility Current Amount (in Crores) Current Ratings Previous ratings Rating Action Fund Based INR 99 "
            "CRISIL A-/Stable CRISIL BBB+/Stable on INR 51.60 crores Revised Non-Fund Based INR 321 CRISIL A2+ "
            "CRISIL A2 on INR 198.40 crores Revised")
    lt, st = _one(text, "CRISIL"), _one(text, "CRISIL", "short")
    assert (lt["rating"], lt["prev_rating"], lt["action"]) == ("A-", "BBB+", "upgraded")
    assert (st["rating"], st["prev_rating"], st["action"]) == ("A2+", "A2", "upgraded")


def test_previous_column_skips_the_spelled_out_repeat():
    text = ("Current Ratings Previous Ratings Rating Action Term Loan 107.41 IVR C / RWDI (IVR C with Rating Watch "
            "with Developing Implications) IVR BBB / RWDI (IVR Triple B with Rating Watch with Developing "
            "Implications) Downgraded")
    lt = _one(text, "Infomerics")
    assert (lt["rating"], lt["prev_rating"], lt["action"], lt["watch"]) == ("C", "BBB", "downgraded", "developing")


def test_previous_column_first_reverses_the_pair():
    text = ("CARE Ratings Limited has upgraded the credit rating of Navin Fluorine International Limited as detailed "
            "in the below table: Name of the Company Type of Credit Rating Previous Rating Revised Rating Navin "
            "Fluorine International Limited Long-term bank facilities CARE AA; Stable CARE AA+; Stable")
    lt = _one(text, "CARE")
    assert (lt["rating"], lt["prev_rating"], lt["action"], lt["outlook"]) == ("AA+", "AA", "upgraded", "Stable")


def test_filing_verb_beats_a_standing_watch():
    text = ("CARE Edge Ratings Limited (CARE), has Reaffirmed the ratings of following debt instruments of IFCI "
            "Limited, as under:- S. No. Nature of Facility Reaffirmed Ratings 1. Infrastructure Bonds 'CARE BB (RWD)' "
            "2. Long-Term Bank Facilities 'CARE BB (RWD)'")
    lt = _one(text, "CARE")
    assert (lt["rating"], lt["watch"], lt["action"]) == ("BB", "developing", "reaffirmed")


def test_default_drops_a_stale_short_term_rating():
    text = ("India Ratings has maintained the Long-Term Issuer Rating at 'IND D(ISSUER NOT COOPERATING)' on the "
            "agency's website. Rating history: Short-term rating IND A1 (2023)")
    assert [(r["term"], r["rating"]) for r in parse_ratings(text)] == [("long", "D")]


def test_curly_quoted_outlook():
    text = "India Ratings has downgraded the Long-Term Issuer Rating to 'IND A-’/Stable/‘IND A2+’ from ‘IND A’/Negative"
    assert _one(text, "India Ratings")["outlook"] == "Stable"


def test_watch_without_another_verb_is_a_watch_action():
    text = "India Ratings has kept the rating of the Company at IND AA- on rating watch with negative implication."
    lt = _one(text, "India Ratings")
    assert (lt["watch"], lt["action"]) == ("negative", "watch")


def test_guaranteed_and_third_party_ratings_are_skipped():
    # MTNL: the sovereign-guaranteed bond's short-term leg and the escrow bank's own ratings
    text = ("Long-term bank facilities 2,752.48 CARE D Reaffirmed Bonds 3,500 CARE AAA (CE); Stable / CARE A1+ (CE) "
            "Reaffirmed. The trustee-administered escrow account maintained with Bank of India (BoI, CARE AA+; "
            "Stable / CARE A1+) for servicing sovereign guarantee (SG) backed bonds.")
    got = parse_ratings(text)
    assert [(r["agency"], r["term"], r["rating"]) for r in got] == [("CARE", "long", "D")]
    # a nested "(CE)" inside the aside must not close it
    text = ("Long-term bank facilities CARE D Reaffirmed. Operations were taken over by Bharat Sanchar Nigam "
            "Limited (BSNL, rated ‘CARE AAA (CE); Stable’/ CARE BBB Positive; CARE A3+) from January 01, 2025.")
    assert [(r["term"], r["rating"]) for r in parse_ratings(text)] == [("long", "D")]


def test_withdrawn_keeps_the_withdrawn_rating():
    text = ("inform you that ICRA has withdrawn the credit rating assigned for Long-term Fund-based – Term "
            "loans 150.00 [ICRA]AA-(Stable); Withdrawn Long-term/ Short term 585.00 [ICRA]AA-(Stable)/[ICRA]A1+; "
            "Withdrawn")
    lt = _one(text, "ICRA")
    assert (lt["rating"], lt["action"]) == ("AA-", "withdrawn")


def test_revised_action_resolved_by_previous_rating():
    text = ("Crisil Ratings Limited has revised the credit ratings on banking facilities. Fund Based INR 99 "
            "CRISIL A-/Stable Revised from CRISIL BBB+/Stable")
    lt = _one(text, "CRISIL")
    assert (lt["prev_rating"], lt["action"]) == ("BBB+", "upgraded")


def test_filing_level_action_is_the_fallback():
    text = ("This is to inform that CARE Ratings has reaffirmed the ratings of the Company. Long Term Bank "
            "Facilities 500.00 CARE AA; Stable")
    assert _one(text, "CARE")["action"] == "reaffirmed"


# ── global agencies ───────────────────────────────────────────────────────────────────────
def test_fitch_issuer_default_rating():
    text = ("Sub.: FITCH Ratings affirms Tata Chemicals Limited's credit rating at BB+ (Outlook: Stable) "
            "This is to inform that Fitch Ratings has affirmed Tata Chemicals Limited's Long Term Foreign "
            "Currency Issuer Default Rating (IDR) at BB+ (Outlook: Stable).")
    r = _one(text, "Fitch")
    assert (r["rating"], r["scale"], r["outlook"], r["action"], r["notch"]) == ("BB+", "global", "Stable", "reaffirmed", 11)


def test_fitch_quoted_rating_with_outlook_after():
    text = ("Fitch Ratings (International Agency) a. Affirms Adani Energy Solutions Limited's (AESL) Long Term "
            "Foreign- and Local-Currency Issuer at 'BBB-' and removed from Rating Watch Negative (RWN) and "
            "assigned a Negative Outlook;")
    r = _one(text, "Fitch")
    assert (r["rating"], r["outlook"], r["action"]) == ("BBB-", "Negative", "reaffirmed")


@pytest.mark.parametrize("text,agency,rating,outlook,prev,action", [
    ("IndiGo is delighted to announce that Moody’s Investor Services, Inc (“Moody’s”) in its debut assessment has "
     "assigned IndiGo a long-term investment grade credit rating of Baa3 with a stable outlook", "Moody's", "Baa3",
     "Stable", None, "assigned"),
    ("This is to inform that Moody’s Investor Services, Inc (“Moody’s”) has issued an announcement on April 30, "
     "2026, following its periodic review of the Company’s ratings (Baa3 stable).", "Moody's", "Baa3", "Stable",
     None, None),
    ("today i.e., on May 29, 2026, Moody’s Ratings (‘Moody’s’) upgraded the issuer rating of Tata Steel Limited "
     "from ‘Baa3 (Stable)’ to ‘Baa2 (Stable)’.", "Moody's", "Baa2", "Stable", "Baa3", "upgraded"),
    ("the following rating has been assigned by Fitch Ratings Limited to Capri Global Capital Limited's USD1 "
     "Billion Global Medium-Term Note (GMTN) programme: Credit Rating Agency Rating Type Fitch Ratings BB-/Stable",
     "Fitch", "BB-", "Stable", None, "assigned"),
])
def test_global_agency_phrasings(text, agency, rating, outlook, prev, action):
    r = _one(text, agency)
    assert (r["rating"], r["outlook"], r["prev_rating"], r["action"]) == (rating, outlook, prev, action)


@pytest.mark.parametrize("text,agency,rating,outlook,prev,action", [
    ("inform that Japan Credit Rating Agency, Ltd. (JCR) has communicated a revision in the long- term issuer credit "
     "rating and outlook of REC Limited to 'A-' with Stable Outlook from 'BBB+' with Stable Outlook.",
     "JCR", "A-", "Stable", "BBB+", "upgraded"),
    ("inform that CareEdge Global Ratings (Rating Agency) has assigned a ‘CareEdge BBB+/Stable’ rating to Canara "
     "Bank’s USD 3 Billion Medium-Term Notes (MTN) programme", "CareEdge Global", "BBB+", "Stable", None, "assigned"),
    ("inform that S&P Global Ratings on August 27, 2026 has assigned its 'BBB' long-term issue rating to following "
     "U.S. dollar-denominated senior unsecured notes", "S&P", "BBB", None, None, "assigned"),
    ("inform that the rating agency, S&P Global Ratings, has assigned 'BBB' long -term and 'A -2' short - term issuer "
     "credit ratings to BOI. The outlook on the long -term rating is stable.", "S&P", "BBB", None, None, "assigned"),
])
def test_more_global_agencies(text, agency, rating, outlook, prev, action):
    r = _one(text, agency)
    assert (r["rating"], r["outlook"], r["prev_rating"], r["action"]) == (rating, outlook, prev, action)


def test_careedge_global_is_not_domestic_care():
    got = parse_ratings("CareEdge Global IFSC Limited has assigned a credit rating of ‘CareEdge BB-/Positive’ to the notes")
    assert [(r["agency"], r["scale"], r["rating"]) for r in got] == [("CareEdge Global", "global", "BB-")]


def test_l_for_one_in_short_term_grade():
    text = ("CRISIL Ratings Limited has re-affirmed the rating for the following instruments of the Company: "
            "Instrument Name Short Term Debt Rating Outstanding CRISIL Al+ Commercial Paper")
    assert _one(text, "CRISIL", "short")["rating"] == "A1+"


def test_fitch_group_is_india_ratings_not_fitch():
    text = ("India Ratings and Research (a Fitch Group Company) has assigned/affirmed IFB Agro Industries Limited's "
            "existing rating at 'lND A+/Stable/lND A1+',. A copy of the report issued by India Ratings")
    got = parse_ratings(text)
    assert sorted((r["agency"], r["term"], r["rating"]) for r in got) == [
        ("India Ratings", "long", "A+"), ("India Ratings", "short", "A1+")]


def test_moodys_scale():
    r = _one("Moody's Ratings has upgraded the Company's corporate family rating to Baa3 with a Stable outlook.",
             "Moody's")
    assert (r["rating"], r["notch"], r["action"]) == ("Baa3", 10, "upgraded")


# ── traps ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    # ESG score, not a credit rating
    "ESG Risk Assessments & Insights Limited, a SEBI registered ESG Rating Provider, has voluntarily assigned "
    "an ESG Score of '67' (Strong) to the Company",
    # structured / credit-enhanced paper is not the company's own credit
    "ICRA Limited has assigned the below mentioned final ratings to the Pass-Through Certificates: Series A1 "
    "SNs [ICRA]AAA(SO); Assigned Equity Tranche SNs [ICRA]AA-(SO); Assigned",
    # accounting standard, not a rating
    "The financial statements are prepared in accordance with IND AS 115 and IND AS 116.",
    # the letter only points at the enclosure
    "India Ratings vide their letter dated July 03, 2026, has affirmed the Company's ratings w.r.t. bank loan "
    "facilities. A copy of aforesaid credit rating issued by India Ratings is enclosed herewith.",
])
def test_rejects_traps(text):
    assert parse_ratings(text) == []


def test_pronounced_duplicate_is_not_a_long_term_rating():
    text = ("CRISIL Ratings Limited has assigned a Credit rating of 'Crisil A1+' (pronounced as Crisil A one plus "
            "rating) to the proposed Rs.500 crores commercial paper of the Company.")
    got = parse_ratings(text)
    assert [(r["term"], r["rating"], r["action"]) for r in got] == [("short", "A1+", "assigned")]


def test_one_row_per_agency_and_term():
    text = ("CARE AA-; Stable reaffirmed ... CARE A1+ reaffirmed ... ICRA: [ICRA]AA-(Stable) reaffirmed ... "
            "Annexure rating history: CARE A+; Stable (2021) CARE A; Stable (2019)")
    got = parse_ratings(text)
    assert sorted((r["agency"], r["term"], r["rating"]) for r in got) == [
        ("CARE", "long", "AA-"), ("CARE", "short", "A1+"), ("ICRA", "long", "AA-")]


# ── production audit (2026-09-26, 40 random rows of the first 300 filings) ────────────────
def test_capitalised_spelled_out_grade_is_not_a_rating():
    got = parse_ratings("ICRA has reaffirmed the rating at [ICRA]A1+ (pronounced ICRA A One Plus) This is for your "
                        "information and record.")
    assert [(r["term"], r["rating"]) for r in got] == [("short", "A1+")]


def test_first_verb_after_the_rating_wins_over_the_next_rows():
    text = "CARE has reviewed the ratings. Short-term bank facilities CARE A1+ Reaffirmed Long Term Bank Facilities _ _ Withdrawn"
    assert _one(text, "CARE", "short")["action"] == "reaffirmed"


def test_same_grade_upgrade_is_an_outlook_change():
    text = ("Current Rating Previous Rating Rating Action Long Term Bank Facilities IVR BBB/Positive (Triple B with Outlook "
            "Positive) IVR BBB/Stable (Triple B with Outlook Stable) Rating upgraded and outlook revised from IVR BBB/Stable")
    lt = _one(text, "Infomerics")
    assert (lt["rating"], lt["outlook"], lt["action"]) == ("BBB", "Positive", "reaffirmed")


def test_slash_watch_and_with_a_stable_outlook():
    assert _one("Crisil has upgraded the ratings: Crisil A1/Watch Positive", "CRISIL", "short")["watch"] == "positive"
    text = "India Ratings has affirmed Larsen's Long-Term Issuer Rating at ‘IND AAA’ with a Stable Outlook"
    assert _one(text, "India Ratings")["outlook"] == "Stable"


def test_curly_double_quoted_previous_rating():
    text = "CRISIL has upgraded the ratings: Long Term CRISIL A-/Stable Upgraded from “CRISIL BBB+/Stable”"
    assert _one(text, "CRISIL")["prev_rating"] == "BBB+"


def test_global_rating_above_the_sovereign_ceiling_is_a_misread():
    # India is BBB / Baa3; the strongest issuers sit a few notches above (Infosys: S&P A-), never at A+
    assert parse_ratings("S&P Global Ratings has affirmed the bank at 'A+' long-term rating.") == []
    assert _one("S&P Global Ratings has affirmed Infosys at 'A-' with a stable outlook.", "S&P")["rating"] == "A-"
    assert parse_ratings("Moody's Ratings letterhead www.moodys.com Canara Bank rated as A with") == []
    assert _one("Japan Credit Rating Agency has upgraded HUDCO's rating to 'A-' with Stable outlook", "JCR")["rating"] == "A-"


def test_global_rating_only_from_the_covering_letter():
    cover = "Sun Pharma informs that Moody's has published a press release on the Company. " + "x " * 3000
    enclosure = ("said Moody's Ratings Senior Vice President. The rating also incorporates Sun's announced acquisition "
                 "of Organon & Co. (Ba3, ratings under review for upgrade) for an enterprise value")
    assert parse_ratings(cover + enclosure) == []


def test_each_global_agency_only_takes_its_own_scale():
    text = ("Moody’s Ratings and S&P Global Ratings have vide letters dated September 1, 2026, assigned ‘Baa3’ and "
            "‘BBB’ rating to the Notes respectively.")
    got = {r["agency"]: r["rating"] for r in parse_ratings(text)}
    assert got == {"Moody's": "Baa3", "S&P": "BBB"}


def test_rating_column_tables():
    text = ("The details of the ratings assigned are set out below: Rating Agency Instrument/Type Rating Moody’s Long-Term "
            "Issuer Credit Rating Baa1 (Stable Outlook) S&P Global Long-Term Issuer Credit Rating BBB+ (Stable Outlook)")
    got = {r["agency"]: (r["rating"], r["outlook"]) for r in parse_ratings(text)}
    assert got == {"Moody's": ("Baa1", "Stable"), "S&P": ("BBB+", "Stable")}
    text = ("Reg.: Rating action by Moody’s, Fitch and Care Edge Ratings. The details are as under: Rating Agency Rating "
            "Moody’s Ratings Baa3 Fitch Rating BBB- Care Edge Ratings Care Edge BBB+/Stable")
    got = {r["agency"]: r["rating"] for r in parse_ratings(text)}
    assert got == {"Moody's": "Baa3", "Fitch": "BBB-"}


def test_grade_opening_an_aside_is_another_issuers():
    text = ("Moody's Ratings has affirmed Sun Pharma at Baa2 with a stable outlook. The rating also incorporates Sun's "
            "announced acquisition of Organon & Co. (Ba3, ratings under review for upgrade)")
    assert _one(text, "Moody's")["rating"] == "Baa2"
    assert parse_ratings("Moody's notes the acquisition of Organon & Co. (Ba3, ratings under review)") == []


def test_rating_rows_attach_filing_identity():
    filing = {"seq_id": 7, "symbol": "TITAN", "disclosed_at": "2025-08-28T18:19:50+05:30"}
    got = rating_rows(filing, [{"agency": "ICRA", "scale": "domestic", "term": "long", "rating": "AAA", "notch": 1,
                                "outlook": "Stable", "watch": None, "action": "reaffirmed", "prev_rating": None,
                                "quote": "[ICRA]AAA (Stable); reaffirmed"}])
    assert got == [{"seq_id": 7, "symbol": "TITAN", "disclosed_at": "2025-08-28T18:19:50+05:30", "agency": "ICRA",
                    "scale": "domestic", "term": "long", "rating": "AAA", "notch": 1, "outlook": "Stable",
                    "watch": None, "action": "reaffirmed", "prev_rating": None,
                    "quote": "[ICRA]AAA (Stable); reaffirmed", "method": "rule_v1"}]
