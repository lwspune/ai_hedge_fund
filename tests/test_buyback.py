"""Test-first spec for buyback tender-arbitrage math + entitlement parsing."""
from pathlib import Path

import pandas as pd
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
    # a buyback worth 10% of mkt cap should lift acceptance above the flat prior (untested nudge).
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

def test_estimate_acceptance_prior_is_flat_and_calibrated():
    """2026-09-24: 24 published post-buyback response tables (2023-26) put small-shareholder
    acceptance at 52% / 59% / 16% / 51% by cap bucket (median 42%, mean 51%) -- no market-cap
    gradient. The old 90% small-cap / 12% large-cap guess is gone; the prior is flat until the
    calibration says otherwise (`python -m scanner.calibrate`)."""
    from scanner.buyback import _MCAP_ACCEPTANCE_PRIOR, CALIBRATED_ACCEPTANCE
    assert {a for _, a in _MCAP_ACCEPTANCE_PRIOR} == {CALIBRATED_ACCEPTANCE}
    assert 0.40 <= CALIBRATED_ACCEPTANCE <= 0.55
    assert estimate_acceptance(market_cap_cr=800, entitlement_small=0.10) == pytest.approx(CALIBRATED_ACCEPTANCE)
    assert estimate_acceptance(market_cap_cr=200000, entitlement_small=0.05) == pytest.approx(CALIBRATED_ACCEPTANCE)


def test_estimate_acceptance_respects_entitlement_floor():
    # Entitlement higher than the prior -> floor wins (it is guaranteed).
    assert estimate_acceptance(market_cap_cr=200000, entitlement_small=0.60) == pytest.approx(0.60)


def test_estimate_acceptance_unknown_mcap_falls_to_floor():
    assert estimate_acceptance(market_cap_cr=None, entitlement_small=0.12) == pytest.approx(0.12)


def test_estimate_acceptance_never_decreases_with_size():
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


def test_fetch_page_does_not_follow_redirects():
    """Unknown buyback ids 307-redirect to a listing page that also says 'Buyback'."""
    from scanner.buyback import _fetch_page

    class R:
        status_code, text = 307, "<title>Buyback list</title>"

    class S:
        kw = None

        def get(self, url, **kw):
            S.kw = kw
            return R()

    assert _fetch_page(9999, S()) == (False, None)
    assert S.kw.get("allow_redirects") is False


# --- 2026 chittorgarh page format (DATA_INFRA_SPEC WP1) ------------------------

FIX = Path(__file__).resolve().parent / "fixtures" / "buyback"


def _fx(bid):
    return (FIX / f"{bid}.html").read_text(encoding="utf-8")


def test_parse_entitlement_ratio_table_wording():
    assert parse_entitlement("Small Shareholders 11 : 56 9,00,00,000") == pytest.approx(11 / 56)
    assert parse_entitlement("Small Shareholders 17 : 61") == pytest.approx(17 / 61)


def test_parse_entitlement_old_wording_still_works():
    txt = "Reserved Category for Small Shareholders 25 Equity Shares out of every 103 Fully paid-up"
    assert parse_entitlement(txt) == pytest.approx(25 / 103)


def test_parse_entitlement_ignores_general_category():
    assert parse_entitlement("General Category 10 : 197 51,00,00,000") is None


def test_parse_entitlement_rejects_ratio_above_one():
    assert parse_entitlement("Small Shareholders 56 : 11") is None
    assert parse_entitlement("Small Shareholders 0 : 11") is None


def test_parse_buyback_2026_wipro():
    from scanner.buyback import parse_buyback
    bb = parse_buyback(_fx(219), 219)
    assert bb["symbol"] == "WIPRO"
    assert bb["buyback_price"] == 250
    assert bb["record_date"] == pd.Timestamp("2026-06-05")
    assert bb["close_date"] == pd.Timestamp("2026-06-17")
    assert bb["entitlement_small"] == pytest.approx(11 / 56)
    assert bb["issue_size_cr"] == pytest.approx(15000.0)


def test_parse_buyback_2026_bajaj_auto():
    from scanner.buyback import parse_buyback
    bb = parse_buyback(_fx(225), 225)
    assert bb["symbol"] == "BAJAJ-AUTO"
    assert bb["buyback_price"] == 12000
    assert bb["record_date"] == pd.Timestamp("2026-06-24")
    assert bb["close_date"] == pd.Timestamp("2026-07-07")
    assert bb["entitlement_small"] == pytest.approx(17 / 61)
    assert bb["issue_size_cr"] == pytest.approx(5632.8)


def test_parse_buyback_2025_regression():
    from scanner.buyback import parse_buyback
    bb = parse_buyback(_fx(213), 213)
    assert bb["symbol"] == "NECLIFE"
    assert bb["buyback_price"] == 27
    assert bb["record_date"] == pd.Timestamp("2025-12-24")
    assert bb["close_date"] == pd.Timestamp("2026-01-06")
    assert bb["entitlement_small"] == pytest.approx(25 / 103)
    assert bb["issue_size_cr"] == pytest.approx(81.0)


def test_parse_issue_type():
    from scanner.buyback import parse_issue_type
    assert parse_issue_type(_fx(219)) == "tender"
    assert parse_issue_type("<li>Issue Type</li><li>Open Market</li>") == "open_market"
    assert parse_issue_type("<p>nothing</p>") is None


def test_open_market_page_rejected():
    """An open-market buyback must never be scored as a tender arb, even if a ratio slips in."""
    from scanner.buyback import parse_buyback
    html = _fx(219).replace("Tender Offer", "Open Market")
    assert parse_buyback(html, 219) is None


class _FixtureSession:
    """Serves fixtures by id; every other id 307-redirects (chittorgarh's unknown-id behaviour)."""
    PAGES = {213: 213, 219: 219, 225: 225, 214: "junk"}

    def get(self, url, **kw):
        bid = int(url.rstrip("/").rsplit("/", 1)[1])
        src = self.PAGES.get(bid)

        class R:
            pass
        r = R()
        if src is None:
            r.status_code, r.text = 307, "Buyback list"
        elif src == "junk":
            r.status_code, r.text = 200, "<html><title>Some Buyback</title><p>no tables</p></html>"
        else:
            r.status_code, r.text = 200, _fx(src)
        return r


def test_discover_buybacks_counts_pages_and_rejections():
    from scanner.buyback import discover_buybacks
    stats = {}
    found = discover_buybacks(212, max_gap=6, hard_cap=50, session=_FixtureSession(),
                              stats=stats, delay=0)
    assert [b["symbol"] for b in found] == ["NECLIFE", "WIPRO", "BAJAJ-AUTO"]
    # ids 213, 214, 219, 225 exist; 214 is not a parseable tender
    assert stats == {"pages_seen": 4, "tender_parsed": 3, "rejected": 1}


def test_discover_buybacks_hard_cap_stops():
    from scanner.buyback import discover_buybacks
    stats = {}
    discover_buybacks(212, max_gap=100, hard_cap=5, session=_FixtureSession(), stats=stats, delay=0)
    assert stats["pages_seen"] == 2  # 213, 214 within ids 212..216


def test_scan_defaults_cover_moved_frontier():
    import inspect
    from scanner.buyback import scan_current_buybacks
    sig = inspect.signature(scan_current_buybacks).parameters
    assert sig["max_gap"].default >= 12 and sig["hard_cap"].default >= 120


# --- small-shareholder float -> entitlement estimate (shareholding table, 2026-09-24) --------

def test_estimate_entitlement_from_small_holder_float():
    from scanner.buyback import estimate_entitlement
    # Rs 100 cr buyback at Rs 1,000 = 1e6 shares; 15% reserved = 150,000.
    # Mkt cap 10,000 cr at Rs 800 = 1.25e8 shares; small holders 10% = 1.25e7 -> 1.2%
    e = estimate_entitlement(issue_size_cr=100, buyback_price=1000, market_cap_cr=10000, price=800,
                             small_holder_pct=10)
    assert e == pytest.approx(0.012)
    assert estimate_entitlement(100, 1000, 10000, 800, small_holder_pct=None) is None
    assert estimate_entitlement(100, 1000, None, 800, small_holder_pct=10) is None
    assert estimate_entitlement(100, 1000, 10000, 800, small_holder_pct=0) is None
    # a tiny float can't be over-subscribed past 100% acceptance
    assert estimate_entitlement(1000, 1000, 1000, 800, small_holder_pct=1) == 1.0


def test_entitlement_floor_prefers_published_ratio():
    from scanner.buyback import entitlement_floor
    bb = {"entitlement_small": 0.08, "issue_size_cr": 100, "buyback_price": 1000}
    assert entitlement_floor(bb, market_cap_cr=10000, price=800, small_holder_pct=10) == (0.08, "published")
    bb["entitlement_small"] = None
    assert entitlement_floor(bb, 10000, 800, 10) == (pytest.approx(0.012), "estimated")
    assert entitlement_floor(bb, 10000, 800, None) == (None, None)


# --- pre-letter-of-offer tenders (the record-date blind spot, 2026-09-24) -------------

def test_parse_buyback_keeps_tender_before_letter_of_offer():
    """Global Pet (id 248): tender offer, record date announced, entitlement not yet published.
    This is exactly when a buyer must act, so the row must survive with entitlement None."""
    from scanner.buyback import parse_buyback
    bb = parse_buyback(_fx(248), 248)
    assert bb is not None
    assert bb["symbol"] == "GLOBALPET"
    assert bb["buyback_price"] == 160
    assert bb["record_date"] == pd.Timestamp("2026-09-25")
    assert pd.isna(bb["close_date"])
    assert bb["entitlement_small"] is None
    assert bb["issue_type"] == "tender"
    assert bb["issue_size_cr"] == pytest.approx(13.56)


def test_parse_buyback_open_market_still_rejected():
    from scanner.buyback import parse_buyback
    assert parse_buyback(_fx(245), 245) is None          # Man Infra: open market


def test_parse_buyback_unknown_type_without_entitlement_rejected():
    from scanner.buyback import parse_buyback
    assert parse_buyback("<html><title>Buyback Detail</title><table><tr><td>x</td></tr></table></html>", 1) is None


def test_discover_keeps_pre_lof_tender_and_counts_it_parsed():
    from scanner.buyback import discover_buybacks

    pages = {300: _fx(248), 301: _fx(245)}

    class R:
        def __init__(self, bid):
            self.status_code = 200 if bid in pages else 307
            self.text = pages.get(bid, "<title>Buyback list</title>")

    class S:
        def get(self, url, **kw):
            return R(int(url.rstrip("/").rsplit("/", 1)[1]))

    stats = {}
    out = discover_buybacks(300, max_gap=2, session=S(), stats=stats, delay=0)
    assert [b["id"] for b in out] == [300]
    assert out[0]["entitlement_small"] is None
    assert stats == {"pages_seen": 2, "tender_parsed": 1, "rejected": 1}


def test_enrich_uses_estimated_floor_when_entitlement_unpublished():
    from scanner.buyback import enrich_buyback
    bb = {"id": 248, "symbol": "GLOBALPET", "buyback_price": 160.0, "record_date": pd.Timestamp("2026-09-25"),
          "close_date": pd.NaT, "entitlement_small": None, "issue_size_cr": 13.56, "issue_type": "tender"}
    r = enrich_buyback(bb, cur=140.0, market_cap_cr=120.0, small_holder_pct=40.0, today=pd.Timestamp("2026-09-24"))
    assert r["premium"] == pytest.approx(160 / 140 - 1)
    assert r["entitlement_source"] == "estimated"
    assert 0 < r["est_entitlement"] <= 1
    assert r["est_acceptance"] >= r["est_entitlement"]
    assert r["est_return"] is not None and r["exp_return"] is not None
    assert r["is_open"] is True                      # no close date yet = window not over


def test_enrich_without_any_floor_still_ranks_on_acceptance_prior():
    from scanner.buyback import enrich_buyback
    bb = {"id": 1, "symbol": "X", "buyback_price": 120.0, "record_date": pd.Timestamp("2026-09-25"),
          "close_date": pd.NaT, "entitlement_small": None, "issue_size_cr": None, "issue_type": "tender"}
    r = enrich_buyback(bb, cur=100.0, market_cap_cr=500.0, small_holder_pct=None, today=pd.Timestamp("2026-09-24"))
    assert r["entitlement_source"] is None and r["est_entitlement"] is None
    assert r["est_return"] is None                   # no floor -> no floor estimate
    from scanner.buyback import CALIBRATED_ACCEPTANCE
    assert r["est_acceptance"] == pytest.approx(CALIBRATED_ACCEPTANCE)  # flat calibrated prior
    assert r["exp_return"] is not None


def test_enrich_published_entitlement_wins():
    from scanner.buyback import enrich_buyback
    bb = {"id": 2, "symbol": "Y", "buyback_price": 120.0, "record_date": pd.Timestamp("2026-09-01"),
          "close_date": pd.Timestamp("2026-09-17"), "entitlement_small": 0.25, "issue_size_cr": 50.0,
          "issue_type": "tender"}
    r = enrich_buyback(bb, cur=100.0, market_cap_cr=500.0, small_holder_pct=40.0, today=pd.Timestamp("2026-09-24"))
    assert r["entitlement_source"] == "published"
    assert r["est_return"] == pytest.approx(__import__("scanner.buyback", fromlist=["arb_return"]).arb_return(100, 120, 100, 0.25))
    assert r["is_open"] is False


def _closes(dates, values):
    return pd.Series(values, index=pd.DatetimeIndex(pd.to_datetime(dates)), dtype="float64")


def test_last_buy_close_t1_era_is_the_close_before_the_record_date():
    # T+1 settlement (from 2023-01-27): record date = ex-date, so the last cum close is the
    # previous session's, not the record day's (which the old study used).
    from scanner.buyback import last_buy_close
    s = _closes(["2025-06-10", "2025-06-11", "2025-06-12", "2025-06-13"], [100, 102, 95, 94])
    d, px = last_buy_close(s, pd.Timestamp("2025-06-12"))
    assert d == pd.Timestamp("2025-06-11") and px == 102


def test_last_buy_close_t2_era_is_two_sessions_before_the_record_date():
    # Under T+2 the ex-date was the session before the record date; buy the session before that.
    from scanner.buyback import last_buy_close
    s = _closes(["2022-06-10", "2022-06-13", "2022-06-14", "2022-06-15"], [100, 102, 95, 94])
    d, px = last_buy_close(s, pd.Timestamp("2022-06-14"))
    assert d == pd.Timestamp("2022-06-10") and px == 100


def test_last_buy_close_skips_a_non_trading_record_date_and_needs_history():
    from scanner.buyback import last_buy_close
    s = _closes(["2025-06-12", "2025-06-13", "2025-06-16"], [95, 94, 93])
    d, px = last_buy_close(s, pd.Timestamp("2025-06-14"))   # Saturday record date
    assert d == pd.Timestamp("2025-06-13") and px == 94
    assert last_buy_close(s, pd.Timestamp("2025-06-12")) is None


def test_last_buy_date_is_the_trading_day_before_the_record_date():
    from datetime import date
    from scanner.buyback import last_buy_date
    hol = frozenset({date(2025, 6, 16)})
    assert last_buy_date(date(2025, 6, 17), hol) == date(2025, 6, 13)   # skips holiday + weekend
    assert last_buy_date(None, hol) is None


def test_enrich_closes_the_buy_window_once_the_record_date_has_passed():
    # Tender window still open (close date ahead) but the record date is behind us: nothing a
    # new buyer can do, so the Act row must not show it as open.
    from datetime import date
    from scanner.buyback import enrich_buyback
    bb = {"id": 3, "symbol": "Z", "buyback_price": 120.0, "record_date": pd.Timestamp("2026-09-22"),
          "close_date": pd.Timestamp("2026-10-06"), "entitlement_small": 0.25, "issue_size_cr": 50.0,
          "issue_type": "tender"}
    r = enrich_buyback(bb, cur=100.0, market_cap_cr=500.0, small_holder_pct=40.0, today=pd.Timestamp("2026-09-24"))
    assert r["last_buy_date"] == date(2026, 9, 21)
    assert r["is_open"] is False
    early = enrich_buyback(bb, cur=100.0, market_cap_cr=500.0, small_holder_pct=40.0, today=pd.Timestamp("2026-09-21"))
    assert early["is_open"] is True


def test_format_table_marks_estimated_entitlement():
    from scanner.buyback import format_buyback_table
    row = {"symbol": "GLOBALPET", "cur_price": 140.0, "buyback_price": 160.0, "premium": 0.1429,
           "market_cap_cr": 120.0, "entitlement_small": None, "est_entitlement": 0.31, "entitlement_source": "estimated",
           "est_acceptance": 0.9, "exp_return": 0.05, "is_open": True}
    out = format_buyback_table([row])
    assert "GLOBALPET" in out and "31%~" in out and "OPEN" in out
