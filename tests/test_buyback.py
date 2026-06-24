"""Test-first spec for buyback tender-arbitrage math + entitlement parsing."""
import pytest

from scanner.buyback import (
    parse_entitlement, parse_symbol, arb_return, after_tax_return,
    estimate_acceptance, expected_after_tax, parse_issue_size,
    mcap_bucket, calibrate_from_outcomes,
)


# --- issue-size feature ------------------------------------------------------

def test_parse_issue_size_crores():
    assert parse_issue_size("Issue Size (Amount) ₹60.24 Crores Buyback Price") == pytest.approx(60.24)


def test_parse_issue_size_none():
    assert parse_issue_size("no issue size here") is None


def test_parse_issue_size_strips_rupee_entity():
    # &#8377; (₹) entity's digits (8377) must not be mistaken for the amount.
    assert parse_issue_size("Issue Size (Amount) &#8377;60.24 Crores") == pytest.approx(60.24)


def test_large_relative_buyback_boosts_acceptance():
    # mid-cap (base ~0.30); a buyback worth 10% of mkt cap should lift acceptance.
    base = estimate_acceptance(market_cap_cr=8000, entitlement_small=0.05)
    boosted = estimate_acceptance(market_cap_cr=8000, entitlement_small=0.05, issue_size_cr=800)
    assert boosted > base


def test_small_relative_buyback_no_boost():
    base = estimate_acceptance(market_cap_cr=8000, entitlement_small=0.05)
    tiny = estimate_acceptance(market_cap_cr=8000, entitlement_small=0.05, issue_size_cr=80)  # 1%
    assert tiny == pytest.approx(base)


# --- calibration harness (fits from realized outcomes) ----------------------

def test_mcap_bucket_boundaries():
    assert mcap_bucket(800) == "small"
    assert mcap_bucket(8000) == "small_mid"
    assert mcap_bucket(25000) == "mid"
    assert mcap_bucket(200000) == "large"
    assert mcap_bucket(None) == "unknown"


def test_calibrate_from_outcomes_means_by_bucket():
    recs = [
        {"market_cap_cr": 500, "realized_acceptance": 1.0},
        {"market_cap_cr": 900, "realized_acceptance": 0.8},   # both 'small'
        {"market_cap_cr": 200000, "realized_acceptance": 0.1},  # 'large'
    ]
    out = calibrate_from_outcomes(recs)
    assert out["small"]["n"] == 2
    assert out["small"]["acceptance"] == pytest.approx(0.9)
    assert out["large"]["acceptance"] == pytest.approx(0.1)


def test_calibrate_skips_missing():
    out = calibrate_from_outcomes([{"market_cap_cr": 500, "realized_acceptance": None},
                                   {"market_cap_cr": None, "realized_acceptance": 0.9}])
    assert out == {}


# --- acceptance estimation (the selection model) ----------------------------

def test_estimate_acceptance_small_cap_is_high():
    # Small-cap: little retail tendering vs the reserved pool -> high acceptance.
    assert estimate_acceptance(market_cap_cr=800, entitlement_small=0.10) >= 0.8


def test_estimate_acceptance_large_cap_is_low_but_at_least_floor():
    a = estimate_acceptance(market_cap_cr=200000, entitlement_small=0.05)
    assert a < 0.3
    assert a >= 0.05  # never below the guaranteed entitlement floor


def test_estimate_acceptance_respects_entitlement_floor():
    # Entitlement higher than the bucket base -> floor wins.
    assert estimate_acceptance(market_cap_cr=200000, entitlement_small=0.40) == pytest.approx(0.40)


def test_estimate_acceptance_unknown_mcap_falls_to_floor():
    assert estimate_acceptance(market_cap_cr=None, entitlement_small=0.12) == pytest.approx(0.12)


def test_estimate_acceptance_monotonic_in_size():
    small = estimate_acceptance(800, 0.05)
    mid = estimate_acceptance(8000, 0.05)
    large = estimate_acceptance(80000, 0.05)
    assert small >= mid >= large


# --- expected after-tax return (regime picked from record date) -------------

def test_expected_after_tax_picks_regime_by_record_date():
    pre = expected_after_tax(1000, 1400, 0.5, record_date="2024-06-28", slab=0.30)
    post = expected_after_tax(1000, 1400, 0.5, record_date="2025-06-28", slab=0.30)
    assert post < pre  # Oct-2024 dividend tax makes the post-period worse


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
