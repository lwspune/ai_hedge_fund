"""Test-first spec for buyback tender-arbitrage math + entitlement parsing."""
import pytest

from scanner.buyback import parse_entitlement, parse_symbol, arb_return, after_tax_return


# --- NSE symbol parsing (quotes are backslash-escaped in the raw HTML) -------

def test_parse_symbol_double_escaped_nsecode():
    # Real chittorgarh payload: double-encoded JSON -> \\" before each quote.
    assert parse_symbol(r'a \\"nseCode\\":\\"GPIL\\",\\"bseCode\\":\\"532734\\" b') == "GPIL"


def test_parse_symbol_nse_symbol_field():
    assert parse_symbol(r'\\"nse_symbol\\":\\"TRITURBINE\\"') == "TRITURBINE"


def test_parse_symbol_picks_nse_not_bse():
    assert parse_symbol(r'\\"bseCode\\":\\"532540\\",\\"nseCode\\":\\"TCS\\"') == "TCS"


def test_parse_symbol_none():
    assert parse_symbol("no code here") is None


# --- entitlement ratio parsing (from chittorgarh detail tables) -------------

def test_parse_entitlement_basic():
    txt = "5 Equity Shares out of every 56 Fully paid-up Equity Shares held on the Record Date."
    assert parse_entitlement(txt) == pytest.approx(5 / 56)


def test_parse_entitlement_other_ratio():
    assert parse_entitlement("21 Equity Shares out of every 251 ... held") == pytest.approx(21 / 251)


def test_parse_entitlement_none_when_absent():
    assert parse_entitlement("no ratio here") is None


# --- gross arbitrage return --------------------------------------------------

def test_arb_return_premium_capture_flat_residual():
    # entry 1000, buyback 1400 (+40%), residual sells flat at 1000, accept 10%.
    # N=200 (2L/1000). accepted=20 -> +400 each = 8000 gain. residual flat.
    r = arb_return(entry_price=1000, buyback_price=1400, post_price=1000,
                   accept_frac=0.10, capital=200000, cost_bps=0)
    assert r == pytest.approx((20 * 1400 + 180 * 1000) / (200 * 1000) - 1)
    assert r > 0


def test_arb_return_hurt_by_residual_crash():
    # Same premium but residual craters 30% -> can flip negative.
    good = arb_return(1000, 1400, 1000, 0.10, cost_bps=0)
    bad = arb_return(1000, 1400, 700, 0.10, cost_bps=0)
    assert bad < good


def test_arb_return_higher_acceptance_helps():
    lo = arb_return(1000, 1400, 950, 0.10, cost_bps=0)
    hi = arb_return(1000, 1400, 950, 0.50, cost_bps=0)
    assert hi > lo


def test_arb_return_none_when_capital_too_small():
    assert arb_return(entry_price=500000, buyback_price=600000, post_price=500000,
                      accept_frac=0.1, capital=200000) is None


# --- after-tax: the Oct-2024 regime change ----------------------------------

def test_post_oct2024_tax_reduces_return_vs_pre():
    args = dict(entry_price=1000, buyback_price=1400, post_price=980, accept_frac=0.20)
    pre = after_tax_return(**args, regime="pre_oct2024", slab=0.30)
    post = after_tax_return(**args, regime="post_oct2024", slab=0.30)
    # Post-Oct-2024 taxes the whole buyback proceeds as dividend -> strictly worse.
    assert post < pre


def test_pre_oct2024_close_to_gross():
    args = dict(entry_price=1000, buyback_price=1400, post_price=1000, accept_frac=0.20)
    gross = arb_return(**args, cost_bps=0)
    pre = after_tax_return(**args, regime="pre_oct2024", slab=0.30, cost_bps=0)
    # Pre-Oct-2024 buyback proceeds were tax-free; flat residual -> ~gross.
    assert pre == pytest.approx(gross, abs=1e-9)
