"""Test-first spec for the named-holder study layer (scanner/holders.py): which SHP holders are
investors, who they are across filings, when one newly appears (an "entry"), and the walk-forward
investor ranking that the skill test is built on."""
import pandas as pd
import pytest

from scanner.holders import (
    entry_events, filing_rows, holder_kind, investor_key, persistence, rank_investors, split_by_rank,
)


# --- storage rows -------------------------------------------------------------------------------

def test_filing_rows_carry_the_quarter_and_a_filing_marker():
    master = {"symbol": "GRAVITA", "quarter_end": "2023-12-31", "broadcast_at": "2024-01-18T17:01:02"}
    parsed = [{"axis": "IndividualsOrHUF", "name": "RAJAT AGRAWAL", "shares": 10, "pct": 47.8, "n_holders": 1}]
    rows = filing_rows(master, parsed)
    assert rows[0] == {"symbol": "GRAVITA", "quarter_end": "2023-12-31", "broadcast_at": "2024-01-18T17:01:02",
                       "axis": "_filing", "name": "", "shares": None, "pct": None, "n_holders": None}
    assert rows[1]["name"] == "RAJAT AGRAWAL" and rows[1]["symbol"] == "GRAVITA"
    # a filing with no named holder still records that the quarter was read
    assert len(filing_rows(master, [])) == 1


# --- who is an investor -------------------------------------------------------------------------

@pytest.mark.parametrize("axis,name,kind", [
    ("ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh", "ASHISH KACHOLIA", "individual"),
    ("IndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh", "ATUL KUCHHAL", "individual"),
    ("NonResidentIndians", "AMAL PARIKH", "individual"),
    ("AlternativeInvestmentFunds", "LIGHTHOUSE INDIA FUND IV AIF", "aif"),
    ("MutualFundsOrUTI", "ICICI Prudential Mutual Fund", "mf"),
    ("MutualFundsOrUti", "Axis Mutual Fund Trustee Limited A/C Axis Small Cap Fund", "mf"),
    ("InstitutionsForeignPortfolioInvestorOne", "NOMURA INDIA INVESTMENT FUND MOTHER FUND", "fpi"),
    ("InstitutionsForeignPortfolioInvestor", "MASSACHUSETTS INSTITUTE OF TECHNOLOGY", "fpi"),
    ("InsuranceCompanies", "LIFE INSURANCE CORPORATION OF INDIA", "insurance"),
    ("BodiesCorporate", "PIVOTAL ENTERPRISES PRIVATE LIMITED", "corporate"),
    ("OtherNonInstitutions", "EZEKIEL GLOBAL BUSINESS SOLUTIONS LLP", "corporate"),
])
def test_public_investor_axes(axis, name, kind):
    assert holder_kind(axis, name) == kind


@pytest.mark.parametrize("axis,name", [
    ("IndividualsOrHUF", "RADHAKISHAN SHIVKISHAN DAMANI"),            # promoter group
    ("OthersIndianShareholders", "Bright Star Investments Pvt Ltd"),  # promoter group, any other
    ("DirectorsAndDirectorsRelatives", "KIRAN MAZUMDAR SHAW"),
    ("KeyManagerialPersonnel", "CHAITANYA RATHI"),
    ("EmployeeBenefitsTrusts", "YAGYADATT SHARMA TRUSTEE"),
    ("CustodianOrDRHolder", "JP MORGAN CHASE BANK, NA"),
    ("ForeignDirectInvestment", "CURRANT SEA INVESTMENTS B.V."),       # strategic
    ("ProvidentFundsOrPensionFunds", "NPS TRUST"),
    ("CentralGovernmentOrPresidentOfIndia", "PRESIDENT OF INDIA"),
    ("NonResidentIndividualsOrForeignIndividuals", "HEMLATA A SHENDE"),  # promoter or public: ambiguous
    ("MutualFundsOrUTI", "SBI NIFTY 50 ETF"),                          # passive
    ("MutualFundsOrUti", "SBI-ETF NIFTY 50"),
    ("InstitutionsForeignPortfolioInvestor", "VANGUARD TOTAL INTERNATIONAL STOCK INDEX FUND"),
    ("MutualFundsOrUTI", "DSP NIFTY MIDCAP 150 ETF"),
    ("OtherNonInstitutions", "IEPF"),                                  # unclaimed shares, not an investor
    ("OtherNonInstitutions", "INVESTOR EDUCATION AND PROTECTION FUND AUTHORITY MINISTRY OF CORPORATE AFFAIRS"),
    ("OtherNonInstitutions", "Clearing Members"),
])
def test_non_investors_are_excluded(axis, name):
    assert holder_kind(axis, name) is None


# --- who they are -------------------------------------------------------------------------------

def test_individual_key_ignores_name_order_honorifics_and_initials():
    assert investor_key("individual", "Jhunjhunwala Rakesh Radheshyam") == \
        investor_key("individual", "RAKESH RADHESHYAM JHUNJHUNWALA")
    assert investor_key("individual", "Mr. Mukul Mahavir Agrawal") == investor_key("individual", "MUKUL MAHAVIR AGRAWAL")
    assert investor_key("individual", "ANUPAMA K PATIL") == investor_key("individual", "Anupama Patil")


def test_mutual_funds_roll_up_to_the_fund_house():
    k = investor_key("mf", "ICICI Prudential Mutual Fund")
    assert k == investor_key("mf", "ICICI PRUDENTIAL MUTUAL FUND - ICICI PRUDENTIAL NIFTY MIDCAP FUND")
    assert k == investor_key("mf", "Icici Prudential Balanced Advantage Fund")
    assert k != investor_key("mf", "SBI Mutual Fund")


def test_entities_drop_legal_suffixes_but_keep_the_name():
    assert investor_key("corporate", "PIVOTAL ENTERPRISES PRIVATE LIMITED") == \
        investor_key("corporate", "Pivotal Enterprises Pvt. Ltd.")
    assert investor_key("aif", "MARATHON EDGE INDIA FUND I") != investor_key("aif", "LIGHTHOUSE INDIA FUND IV AIF")
    assert investor_key("fpi", "Health &amp; Glow") == investor_key("fpi", "HEALTH AND GLOW")


# --- entries ------------------------------------------------------------------------------------

def _rows(symbol, quarter, broadcast, holders):
    out = [{"symbol": symbol, "quarter_end": quarter, "broadcast_at": broadcast, "axis": "_filing", "name": "",
            "shares": None, "pct": None, "n_holders": None}]
    for axis, name, pct in holders:
        out.append({"symbol": symbol, "quarter_end": quarter, "broadcast_at": broadcast, "axis": axis,
                    "name": name, "shares": 1, "pct": pct, "n_holders": 1})
    return out


IND = "ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh"


def test_entry_is_a_first_appearance_after_a_filed_prior_quarter():
    df = pd.DataFrame(
        _rows("ABC", "2023-06-30", "2023-07-15T18:00:00", [("IndividualsOrHUF", "PROMOTER ONE", 60.0)])
        + _rows("ABC", "2023-09-30", "2023-10-16T18:00:00", [("IndividualsOrHUF", "PROMOTER ONE", 60.0),
                                                              (IND, "ASHISH KACHOLIA", 1.4)]))
    ev = entry_events(df)
    assert len(ev) == 1
    e = ev.iloc[0]
    assert (e["symbol"], e["quarter_end"], e["kind"], e["pct"]) == ("ABC", "2023-09-30", "individual", 1.4)
    assert e["entry_date"] == pd.Timestamp("2023-10-16")
    assert e["investor"] == investor_key("individual", "ASHISH KACHOLIA")


def test_first_filing_and_gaps_give_no_entries():
    # the first filed quarter has no "before"; a missing quarter makes "new" unknowable
    df = pd.DataFrame(_rows("ABC", "2022-06-30", "2022-07-15T10:00:00", [(IND, "A B INVESTOR", 2.0)])
                      + _rows("ABC", "2022-12-31", "2023-01-15T10:00:00", [(IND, "C D INVESTOR", 2.0)]))
    assert entry_events(df).empty


def test_name_variant_or_axis_move_is_not_an_entry():
    df = pd.DataFrame(
        _rows("TM", "2023-03-31", "2023-04-15T10:00:00", [(IND, "Rekha Rakesh Jhunjhunwala", 1.6)])
        + _rows("TM", "2023-06-30", "2023-07-15T10:00:00", [(IND, "Rekha Jhunjhunwala", 1.5)])
        + _rows("TM", "2023-09-30", "2023-10-15T10:00:00", [("BodiesCorporate", "SAPPHIRE INTREX LIMITED", 1.1)])
        + _rows("TM", "2023-12-31", "2024-01-15T10:00:00", [("OtherNonInstitutions", "Sapphire Intrex Ltd", 1.1)]))
    ev = entry_events(df)
    # only Sapphire's first appearance counts; its axis move and Rekha's shorter name do not
    assert list(ev["quarter_end"]) == ["2023-09-30"]


def test_reentry_within_a_year_is_not_new():
    q = [("2022-03-31", [(IND, "X Y HOLDER", 1.2)]), ("2022-06-30", []), ("2022-09-30", [(IND, "X Y HOLDER", 1.3)])]
    df = pd.DataFrame([r for qe, h in q for r in _rows("ABC", qe, f"{qe}T00:00:00", h)])
    assert entry_events(df).empty


def test_late_filings_are_dropped():
    # a revision broadcast long after the quarter would be entered too late to mean anything
    df = pd.DataFrame(_rows("ABC", "2023-06-30", "2023-07-15T10:00:00", [])
                      + _rows("ABC", "2023-09-30", "2024-06-01T10:00:00", [(IND, "LATE ONE", 2.0)]))
    assert entry_events(df).empty


def test_non_investor_newcomers_are_not_entries():
    df = pd.DataFrame(_rows("ABC", "2023-06-30", "2023-07-15T10:00:00", [])
                      + _rows("ABC", "2023-09-30", "2023-10-15T10:00:00",
                              [("IndividualsOrHUF", "NEW PROMOTER", 5.0), ("MutualFundsOrUTI", "UTI NIFTY 50 ETF", 1.2)]))
    assert entry_events(df).empty


# --- ranking ------------------------------------------------------------------------------------

def _ev(investor, ret, date="2022-06-01"):
    return {"investor": investor, "ret": ret, "entry_date": pd.Timestamp(date)}


def test_rank_investors_needs_min_events_and_uses_the_median():
    ev = pd.DataFrame([_ev("a", 0.5), _ev("a", 0.1), _ev("a", 0.2),
                       _ev("b", -0.2), _ev("b", -0.1), _ev("b", 0.9),
                       _ev("c", 3.0), _ev("c", 3.0)])          # only 2 events: unranked
    r = rank_investors(ev, "ret", min_n=3)
    assert list(r.index) == ["a", "b"]
    assert r.loc["a", "score"] == pytest.approx(0.2)
    assert r.loc["b", "score"] == pytest.approx(-0.1)
    assert r.loc["a", "n"] == 3


def test_split_by_rank_takes_top_and_bottom_fraction():
    ranks = pd.DataFrame({"score": [0.5, 0.4, 0.1, 0.0, -0.1, -0.3, -0.5, -0.6, -0.7, -0.9]},
                         index=list("abcdefghij"))
    top, bottom = split_by_rank(ranks, frac=0.2)
    assert top == {"a", "b"} and bottom == {"i", "j"}
    # never fewer than one each
    top, bottom = split_by_rank(ranks.iloc[:3], frac=0.2)
    assert top == {"a"} and bottom == {"c"}


def test_persistence_is_rank_correlation_of_two_periods():
    a = pd.Series({"x": 0.3, "y": 0.1, "z": -0.2, "w": 0.0})
    b = pd.Series({"x": 0.2, "y": 0.05, "z": -0.4, "v": 1.0})
    rho, n = persistence(a, b)
    assert n == 3 and rho == pytest.approx(1.0)
