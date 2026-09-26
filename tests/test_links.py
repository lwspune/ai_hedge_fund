"""Test-first spec for order-win counterparty extraction + listed matching (customer-momentum pilot).
Quotes are real SEBI Reg 30 order-win texts (Phase 0 sample, 2024-26)."""
import pandas as pd
import pytest

from scanner.links import (awarding_entity, is_withheld, linked_suppliers, load_aliases, match_listed,
                           name_index, name_key, shock_days)


@pytest.mark.parametrize("text, want", [
    ("a) Name of the entity awarding the order(s) / contract(s) MP Power Generating Co. Ltd. "
     "b) Significant terms and conditions of order(s)/contract(s) awarded in brief Supply of boiler parts",
     "MP Power Generating Co. Ltd"),
    ("1. Name of the entity awarding the order(s) /contract(s); Bharat Sanchar Nigam Limited (BSNL) "
     "2. Significant terms and conditions", "Bharat Sanchar Nigam Limited (BSNL)"),
    ("a) Name of the entity awarding the order(s)/contract(s); Reply: NTPC Limited b) Significant terms "
     "and conditions of order(s)/contract(s) awarded in brief; Reply: Notification of award (NOA)",
     "NTPC Limited"),
    ("Name of the entity awarding the order(s) / contract(s) M/s. Bharat Electronics Limited 2. "
     "Significant terms and conditions", "Bharat Electronics Limited"),
    ("Name of the entity awarding the order( s )/ contract( s ); Zaggle ignored "
     "2 significant terms", "Zaggle ignored"),
    ("1 name of the entity awarding the order(s)/contract(s); Golden Jasraj Music Platforms Pvt Ltd "
     "2 significant terms and conditions", "Golden Jasraj Music Platforms Pvt Ltd"),
    ("Name of the entity awarding the order / contract Adani Electricity Mumbai Limited 2 Nature of the "
     "order / contract supply of special cables", "Adani Electricity Mumbai Limited"),
    ("A. Name of the entity awarding the order/Contract: Godawari Marathwada Irrigation Development "
     "Corporation B. Significant terms", "Godawari Marathwada Irrigation Development Corporation"),
    ("Name of the entity awarding the order(s) / contract(s) / Letter of Award (LOA) One of India's "
     "leading Renewable Energy companies. 2 Significant terms", "One of India's leading Renewable Energy companies"),
    ("Name of the entity awarding the order(s)/contact(s) Tier-1 customer 2. Significant terms", "Tier-1 customer"),
    # label variants
    ("1 Name(s) of the entity awarding the order (s) /Contract(s) : PROMESE/CAL, Dominican Republic "
     "2 Significant terms", "PROMESE/CAL, Dominican Republic"),
    ("a Name of entity awarding the order(s)/ contract(s) CRC Greens Private Limited b Significant terms "
     "and conditions", "CRC Greens Private Limited"),
    ("1. Name of the entity award in the order(s)/contract(s); JK Cement Ltd 2. Significant terms", "JK Cement Ltd"),
    # table layouts: the value sits between "awarding the" and "order(s)/contract(s)"
    ("1 Name of the entity awarding the Himachal Pradesh State Electricity Board Limited order(s)/ "
     "contract(s) (HPSEBL) 2. Significant terms", "Himachal Pradesh State Electricity Board Limited"),
    ("(a) |Name of the entity awarding the | NTPC Vidyut Vyapar Nigam Limited order(s)/contract(s) (b) | "
     "Significant terms", "NTPC Vidyut Vyapar Nigam Limited"),
    ("1 Name of the entity awarding the | State Bank of India (SBI) order(s)/contract(s) 2 significant terms",
     "State Bank of India (SBI)"),
])
def test_awarding_entity_reads_the_sebi_field(text, want):
    assert awarding_entity(text) == want


@pytest.mark.parametrize("text", [
    "a. Name of the entity awarding the order( s )/ contract( s ); b. Significant terms and conditions",
    "Name of the entity awarding the order(s)/contract( s): B",           # blank field, next label
    "Name of the Entity Significant Terms and Conditions of Order(s)",    # table layout, no value
    "We are pleased to inform that the company has received an order worth Rs 50 crore.",
    "",
])
def test_awarding_entity_none_when_field_missing_or_blank(text):
    assert awarding_entity(text) is None


@pytest.mark.parametrize("name, withheld", [
    ("Not disclosed due to the Non-Disclosure Agreement with the entity awarding the order.", True),
    ("A leading domestic two-wheeler manufacturer*", True),
    ("Due to commercial issue, the Company cannot disclose the name of the Customer.", True),
    ("One of India's leading Renewable Energy companies", True),
    ("Tier-1 customer", True),
    ("International Client", True),
    ("NTPC Limited", False),
    ("Bharat Electronics Limited", False),
])
def test_is_withheld(name, withheld):
    assert is_withheld(name) is withheld


def test_name_key_normalises_legal_suffixes_and_punctuation():
    assert name_key("Tata Power Company Limited") == name_key("Tata Power Co. Ltd.") == "tata power"
    assert name_key("Oil & Natural Gas Corporation Limited") == name_key("Oil and Natural Gas Corpn. Ltd")
    assert name_key("GAIL (India) Limited") == name_key("GAIL (India) Ltd") == "gail"
    assert name_key("The Federal Bank  Limited") == name_key("THE FEDERAL BANK LIMITED")
    assert name_key("M/s. Bharat Electronics Limited") == "bharat electronics"


COMPANIES = [{"symbol": "NTPC", "name": "NTPC Limited"},
             {"symbol": "BEL", "name": "Bharat Electronics Limited"},
             {"symbol": "GUJENERGY", "name": "GUJARAT ENERGY LIMITED"},
             {"symbol": "ENERGYDEV", "name": "Energy Development Company Limited"},
             {"symbol": "NSIL", "name": "Nalwa Sons Investments Limited"},
             {"symbol": "GRSE", "name": "Garden Reach Shipbuilders & Engineers Limited"},
             {"symbol": "HINDZINC", "name": "Hindustan Zinc Limited"},
             {"symbol": "TATAPOWER", "name": "Tata Power Company Limited"},
             {"symbol": "TCI", "name": "Transport Corporation of India Limited"},
             {"symbol": "NIACL", "name": "The New India Assurance Company Limited"}]
ALIASES = [{"alias": "Garden Reach Shipbuilders Limited", "symbol": "GRSE"},
           {"alias": "Tata Power Renewable Energy Limited", "symbol": "TATAPOWER"}]
IDX = name_index(COMPANIES, ALIASES)


@pytest.mark.parametrize("name, sym", [
    ("NTPC Limited", "NTPC"),
    ("Bharat Electronics Limited", "BEL"),
    ("Transport Corporation of India Limited", "TCI"),
    ("The New India Assurance Company Ltd", "NIACL"),
    ("Garden Reach Shipbuilders Limited", "GRSE"),                      # alias
    ("Tata Power Renewable Energy Limited", "TATAPOWER"),               # subsidiary alias
    # trailing text after the legal suffix is ignored
    ("Hindustan Zinc Limited (CIN: L27204RJ1966PLC001208) B", "HINDZINC"),
    ("Hindustan Zinc Limited, a Vedanta group company", "HINDZINC"),
])
def test_match_listed_exact_and_alias(name, sym):
    assert match_listed(name, IDX) == sym


@pytest.mark.parametrize("name", [
    "Gujarat Energy Transmission Corporation Limited",   # Phase-0 false positive: GETCO is unlisted
    "New & Renewable Energy Development Corporation of Andhra Pradesh Ltd (NREDCAP)",
    "NewSpace India Limited (NSIL)",                     # NSIL is Nalwa Sons on NSE: no abbreviation matching
    "Bharat Sanchar Nigam Limited (BSNL)",
    "One of India's leading Renewable Energy companies",
    "",
])
def test_match_listed_rejects_near_misses(name):
    assert match_listed(name, IDX) is None


def test_alias_file_is_well_formed():
    rows = load_aliases()
    assert len(rows) >= 10
    assert {r["relation"] for r in rows} <= {"name_variant", "short_form", "subsidiary"}
    keys = [name_key(r["alias"]) for r in rows]
    assert all(keys) and len(keys) == len(set(keys))
    assert all(r["symbol"] and r["symbol"] == r["symbol"].upper() for r in rows)


def test_name_index_refuses_an_ambiguous_key():
    idx = name_index([{"symbol": "A", "name": "Alpha Limited"}, {"symbol": "B", "name": "Alpha Ltd."}], [])
    assert match_listed("Alpha Limited", idx) is None


LINKS = [{"supplier": "BHEL", "customer": "NTPC", "disclosed_at": "2025-01-10T19:00:00+05:30"},
         {"supplier": "AVANTEL", "customer": "BEL", "disclosed_at": "2025-03-01T10:00:00+05:30"},
         {"supplier": "POWERMECH", "customer": "NTPC", "disclosed_at": "2025-06-02T10:00:00+05:30"}]


def test_linked_suppliers_live_only_after_disclosure_and_within_window():
    assert linked_suppliers(LINKS, "NTPC", pd.Timestamp("2025-01-10")) == set()    # same day: not yet
    assert linked_suppliers(LINKS, "NTPC", pd.Timestamp("2025-01-11")) == {"BHEL"}
    assert linked_suppliers(LINKS, "NTPC", pd.Timestamp("2025-07-01")) == {"BHEL", "POWERMECH"}
    assert linked_suppliers(LINKS, "NTPC", pd.Timestamp("2026-01-11")) == {"POWERMECH"}  # BHEL link expired
    assert linked_suppliers(LINKS, "BEL", pd.Timestamp("2025-02-01")) == set()
    assert linked_suppliers(LINKS, "NTPC", pd.Timestamp("2025-01-15"), window_days=3) == set()


def test_shock_days_signed_by_direction():
    ar = pd.Series([0.01, 0.06, -0.051, -0.02, 0.05, None],
                   index=pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-06",
                                         "2025-01-07", "2025-01-08"]))
    assert shock_days(ar, 0.05) == [(pd.Timestamp("2025-01-02"), 1), (pd.Timestamp("2025-01-03"), -1),
                                    (pd.Timestamp("2025-01-07"), 1)]
