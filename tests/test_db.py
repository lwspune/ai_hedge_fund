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


def test_http_errors_carry_postgrest_message():
    """Constraint violations must say which constraint — a bare '400 Bad Request' hides it."""
    import pytest
    import requests
    from scanner.db import _check

    r = requests.Response()
    r.status_code, r.reason, r.url = 400, "Bad Request", "https://x/rest/v1/ipos"
    r._content = b'{"code":"23514","message":"violates check constraint \\"ipos_check\\""}'
    with pytest.raises(requests.HTTPError, match="ipos_check"):
        _check(r)
    ok = requests.Response()
    ok.status_code = 201
    _check(ok)  # no raise


def test_upsert_resilient_keeps_good_rows_when_one_is_rejected(monkeypatch):
    import requests
    from scanner import db
    stored = []

    def fake_insert(table, rows, on_conflict=None, return_rows=True):
        rows = [rows] if isinstance(rows, dict) else rows
        if any(r["symbol"] == "BAD" for r in rows):
            raise requests.HTTPError("409 Conflict: violates foreign key")
        stored.extend(rows)
        return []

    monkeypatch.setattr(db, "insert", fake_insert)
    good, rejected = db.upsert_resilient("t", [{"symbol": "A"}, {"symbol": "BAD"}, {"symbol": "C"}], "symbol")
    assert [r["symbol"] for r in good] == ["A", "C"] == [r["symbol"] for r in stored]
    assert [r["symbol"] for r, _ in rejected] == ["BAD"] and "foreign key" in rejected[0][1]
    assert db.upsert_resilient("t", [], "symbol") == ([], [])


def test_total_from_content_range():
    from scanner.db import _total
    assert _total("0-0/3155") == 3155
    assert _total("*/0") == 0
    assert _total(None) is None


def test_insert_ignore_duplicates_sets_prefer(monkeypatch):
    from scanner import db
    seen = {}

    class R:
        status_code, ok = 201, True

        def json(self):
            return []

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        seen.update(headers=headers, params=params)
        return R()

    monkeypatch.setattr(db, "config", lambda: ("https://x.supabase.co", "k"))
    monkeypatch.setattr(db, "_check", lambda r: None)
    monkeypatch.setattr(db.requests, "post", fake_post)
    db.insert("t", [{"a": 1}], on_conflict="a", return_rows=False, ignore_duplicates=True)
    assert "resolution=ignore-duplicates" in seen["headers"]["Prefer"]
    assert seen["params"] == {"on_conflict": "a"}


# --- buybacks.status: derived from the window, never overwrites the manual lifecycle ---------

def test_buyback_status_from_close_date():
    today = date(2026, 9, 24)
    assert db.buyback_status(date(2026, 9, 30), today) == "open"
    assert db.buyback_status(date(2026, 9, 24), today) == "open"       # last day still open
    assert db.buyback_status(date(2026, 9, 17), today) == "settled"
    assert db.buyback_status(None, today) == "open"                     # timetable not out yet


def test_buyback_row_carries_derived_status():
    r = db.buyback_row({"id": 1, "close_date": date(2026, 9, 17)}, today=date(2026, 9, 24))
    assert r["status"] == "settled"


def test_upsert_buybacks_goes_through_the_guarded_rpc(monkeypatch):
    """A plain upsert would overwrite 'tendered'/'skipped'; the RPC keeps them."""
    calls = []
    monkeypatch.setattr(db, "rpc", lambda fn, args, params=None: calls.append((fn, args)) or 1)
    monkeypatch.setattr(db, "insert", lambda *a, **k: pytest.fail("no direct upsert"))
    db.upsert_buybacks([{"id": 7, "symbol": "X", "close_date": date(2026, 9, 17)}])
    fn, args = calls[0]
    assert fn == "upsert_buybacks" and args["p_rows"][0]["chittorgarh_id"] == 7
    assert args["p_rows"][0]["status"] == "settled"


def test_record_tender_marks_the_buyback_tendered(monkeypatch):
    updates = []
    monkeypatch.setattr(db, "insert", lambda table, rows, **k: [{"id": 5, **rows}])
    monkeypatch.setattr(db, "update", lambda table, filters, values: updates.append((table, filters, values)))
    db.record_tender(42, date(2026, 9, 20), shares_bought=100)
    assert updates == [("buybacks", {"id": "eq.42"}, {"status": "tendered"})]
    updates.clear()
    db.record_tender(42, date(2026, 9, 20), tendered=False)   # bought but didn't tender: no lifecycle change
    assert updates == []


def _paged(rows, calls):
    def fake_select(table, params=None):
        calls.append(int(params["offset"]))
        off = int(params["offset"])
        return rows[off:off + min(int(params["limit"]), 1000)]
    return fake_select


def test_select_all_pages_past_the_cap(monkeypatch):
    rows, calls = list(range(2500)), []
    monkeypatch.setattr(db, "select", _paged(rows, calls))
    assert db.select_all("t") == rows and calls == [0, 1000, 2000]


def test_select_all_max_rows_stops_paging_early(monkeypatch):
    rows, calls = list(range(40000)), []
    monkeypatch.setattr(db, "select", _paged(rows, calls))
    assert db.select_all("t", max_rows=1500) == rows[:1500] and calls == [0, 1000]
    calls.clear()
    assert db.select_all("t", max_rows=300) == rows[:300] and calls == [0]
