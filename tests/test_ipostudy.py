"""Test-first spec for the IPO study's pure math (scanner/ipostudy.py): what one retail lottery
ticket is worth."""
import pytest

from scanner.ipostudy import SELL_COST, allot_prob, gmp_pct, listing_gain


def test_mainboard_odds_are_lots_over_applications():
    # Karamtara: 12,057,086 retail shares / lot 59 = 204,357 lots for 2,751,564 applications
    p = allot_prob("mainboard", 12057086, 59, 2751564, 13.98)
    assert p == pytest.approx(204357 / 2751564)


def test_mainboard_without_application_count_uses_calibrated_lots_per_applicant():
    # P x retail times = 1.10 median over 32 mainboard IPOs with exact counts (applicants bid ~1.1 lots)
    assert allot_prob("mainboard", 12057086, 59, None, 20.0) == pytest.approx(1.10 / 20)


def test_mainboard_older_issue_from_the_nse_retail_figure():
    assert allot_prob("mainboard", None, 59, None, None, sub_retail_nse=8.99) == pytest.approx(1.10 / (8.99 / 0.647))
    assert allot_prob("mainboard", None, 59, None, None, sub_retail_nse=0.5) == 1.0      # 0.77x consolidated


def test_sme_without_a_retail_figure_is_unknown():
    assert allot_prob("sme", None, 1000, None, None, sub_retail_nse=None) is None


def test_sme_odds_are_one_over_retail_times_subscribed():
    # SME retail bids are the minimum application, so times subscribed = applicants per ticket
    assert allot_prob("sme", 500000, 1000, 9000, 40.0) == pytest.approx(1 / 40)


def test_undersubscribed_everyone_is_allotted_and_unknown_is_none():
    assert allot_prob("mainboard", 1000000, 50, 5000, 0.8) == 1.0
    assert allot_prob("sme", 1000, 10, None, 0.9) == 1.0
    assert allot_prob("mainboard", None, None, None, None) is None
    assert allot_prob("mainboard", 100, 10, 5, 3.0) == 1.0          # more lots than applicants: capped


def test_listing_gain_is_net_of_the_sale():
    assert listing_gain(254.0, 320.0) == pytest.approx(320 / 254 - 1 - SELL_COST)
    assert listing_gain(100.0, None) is None and listing_gain(None, 90.0) is None


def test_gmp_pct():
    assert gmp_pct(46.0, 254.0) == pytest.approx(46 / 254)
    assert gmp_pct(None, 254.0) is None


@pytest.mark.parametrize("company,unit", [
    ("Mindspace Business REIT Date, Price, GMP, Review, Details", True),
    ("POWERGRID InvIT InvIT Date, Price, GMP, Review, Details", True),
    ("Raajmarg Infra Investment Trust", True), ("Capital Infra Trust InvIT Date", True),
    ("Cube Highways Trust InvIT Date, Price, GMP, Details", True), ("Nexus Select Trust REIT", True),
    ("Knowledge Realty Trust REIT Date", True),
    ("Trust Fintech", False), ("Beacon Trusteeship", False), ("Karamtara Engineering", False), (None, False),
])
def test_unit_trusts_are_not_company_ipos(company, unit):
    from scanner.ipostudy import is_unit_trust
    assert is_unit_trust(company) is unit


def test_study_scope_is_nse_listed():
    from scanner.ipostudy import on_nse
    assert on_nse("BSE, NSE") and on_nse("NSE SME") and on_nse("NSE, BSE")
    assert not on_nse("BSE SME") and not on_nse("BSE") and not on_nse(None)
