"""Test-first spec for universe selection (financials handling)."""
from scanner.universe import select_universe, is_financial, FINANCIALS


def test_known_bank_is_financial():
    assert is_financial("HDFCBANK") is True
    assert is_financial("SBIN") is True


def test_nonfinancial_is_not_financial():
    assert is_financial("RELIANCE") is False
    assert is_financial("TCS") is False


def test_select_excludes_financials_by_default():
    syms = ["RELIANCE", "HDFCBANK", "TCS", "BAJFINANCE"]
    assert select_universe(syms, include_financials=False) == ["RELIANCE", "TCS"]


def test_select_keeps_financials_when_requested():
    syms = ["RELIANCE", "HDFCBANK", "TCS"]
    assert select_universe(syms, include_financials=True) == syms


def test_financials_set_covers_nifty_banks_nbfcs_insurers():
    for s in ["ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
              "BAJAJFINSV", "SHRIRAMFIN", "SBILIFE", "HDFCLIFE"]:
        assert s in FINANCIALS
