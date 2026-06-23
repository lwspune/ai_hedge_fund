"""Test-first spec for the pure mean-reversion signal math.

These cover the deterministic core (RSI, distance from the 200-DMA, and the
quality gate). Data-fetching is integration code and is validated by running
the scan against live sources, not here.
"""
import math

import pytest

from scanner.signals import rsi, pct_from_sma, passes_quality, evaluate


# --- RSI ---------------------------------------------------------------------

def test_rsi_all_gains_is_100():
    # A strictly rising series has no losses -> RSI saturates at 100.
    closes = list(range(1, 30))
    assert rsi(closes, period=14) == pytest.approx(100.0)


def test_rsi_all_losses_is_0():
    # A strictly falling series has no gains -> RSI bottoms at 0.
    closes = list(range(30, 1, -1))
    assert rsi(closes, period=14) == pytest.approx(0.0)


def test_rsi_mixed_is_between_bounds():
    closes = [10, 11, 10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18]
    val = rsi(closes, period=14)
    assert 0.0 < val < 100.0


def test_rsi_needs_enough_data():
    with pytest.raises(ValueError):
        rsi([1, 2, 3], period=14)


# --- distance from the 200-DMA ----------------------------------------------

def test_pct_from_sma_at_average_is_zero():
    closes = [100.0] * 5
    assert pct_from_sma(closes, window=5) == pytest.approx(0.0)


def test_pct_from_sma_below_average_is_negative():
    # sma5 = (100*4 + 80)/5 = 96; last = 80 -> (80-96)/96 = -1/6
    closes = [100.0, 100.0, 100.0, 100.0, 80.0]
    assert pct_from_sma(closes, window=5) == pytest.approx(-1 / 6)


def test_pct_from_sma_needs_enough_data():
    with pytest.raises(ValueError):
        pct_from_sma([100.0, 100.0], window=200)


# --- quality gate ------------------------------------------------------------

def test_passes_quality_accepts_large_lowdebt():
    assert passes_quality(market_cap_cr=50_000, debt_to_equity=0.3,
                          min_mcap_cr=10_000, max_de=0.5) is True


def test_passes_quality_rejects_small_cap():
    assert passes_quality(market_cap_cr=500, debt_to_equity=0.1,
                          min_mcap_cr=10_000, max_de=0.5) is False


def test_passes_quality_rejects_high_debt():
    assert passes_quality(market_cap_cr=50_000, debt_to_equity=1.2,
                          min_mcap_cr=10_000, max_de=0.5) is False


def test_passes_quality_missing_fundamentals_is_false():
    # Unknown fundamentals must not silently pass the gate.
    assert passes_quality(market_cap_cr=None, debt_to_equity=None,
                          min_mcap_cr=10_000, max_de=0.5) is False


# --- end-to-end evaluation ---------------------------------------------------

def test_evaluate_flags_oversold_quality_name():
    # 200 days: flat at 100 then a hard sell-off to ~78 -> >20% below 200-DMA,
    # falling tail drives RSI well under 30.
    closes = [100.0] * 195 + [95, 90, 86, 82, 78]
    res = evaluate(closes, market_cap_cr=50_000, debt_to_equity=0.2,
                   cfg={"rsi_period": 14, "dma_window": 200,
                        "rsi_max": 30, "below_dma_min": 0.20,
                        "min_mcap_cr": 10_000, "max_de": 0.5})
    assert res["rsi"] < 30
    assert res["pct_from_dma"] <= -0.20
    assert res["quality_ok"] is True
    assert res["signal"] is True


def test_evaluate_rejects_when_not_oversold():
    closes = [100.0] * 200
    res = evaluate(closes, market_cap_cr=50_000, debt_to_equity=0.2,
                   cfg={"rsi_period": 14, "dma_window": 200,
                        "rsi_max": 30, "below_dma_min": 0.20,
                        "min_mcap_cr": 10_000, "max_de": 0.5})
    assert res["signal"] is False
