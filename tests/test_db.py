"""Tests for the pure row-builders + config of the persistence layer (no network)."""
from datetime import date

import pytest

from scanner import db


def test_scan_run_row():
    r = db.scan_run_row("buyback_arb", "conditional", 3, {"ids": "214-229"})
    assert r == {"signal_name": "buyback_arb", "verdict": "conditional",
                 "n_candidates": 3, "params": {"ids": "214-229"}}


def test_candidate_row_defaults_payload():
    r = db.candidate_row(7, "buyback_arb", "GPIL", score=0.05)
    assert r["run_id"] == 7 and r["symbol"] == "GPIL" and r["payload"] == {}


def test_buyback_row_serialises_dates():
    bb = {"id": 172, "company": "Godawari", "symbol": "GPIL", "buyback_price": 1400.0,
          "record_date": date(2024, 6, 28), "close_date": date(2024, 7, 10),
          "entitlement_small": 0.0893}
    r = db.buyback_row(bb, est_return=0.04)
    assert r["chittorgarh_id"] == 172
    assert r["record_date"] == "2024-06-28" and r["close_date"] == "2024-07-10"
    assert r["est_return"] == 0.04


def test_buyback_row_est_falls_back_to_dict():
    bb = {"id": 1, "est_return": 0.07}
    assert db.buyback_row(bb)["est_return"] == 0.07


def test_tender_and_outcome_rows():
    t = db.tender_row(5, date(2024, 6, 20), shares_bought=140, capital=196000)
    assert t["buyback_id"] == 5 and t["decided_on"] == "2024-06-20" and t["tendered"] is True
    o = db.outcome_row(9, accepted_shares=130, realized_acceptance=0.93)
    assert o["tender_id"] == 9 and o["realized_acceptance"] == 0.93


def test_iso_passthrough_for_str():
    assert db._iso("2024-06-28") == "2024-06-28"
    assert db._iso(date(2024, 6, 28)) == "2024-06-28"


def test_headers_have_auth_and_prefer():
    h = db._headers("KEY123", "return=representation")
    assert h["apikey"] == "KEY123"
    assert h["Authorization"] == "Bearer KEY123"
    assert h["Prefer"] == "return=representation"


def test_config_raises_without_credentials(monkeypatch):
    monkeypatch.setattr(db, "_ENV_LOADED", True)  # skip .env loading
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        db.config()
