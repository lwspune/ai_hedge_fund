"""The buyback scan's saved candidate payload is what the Desk and the Telegram alert read."""
from datetime import date

import pandas as pd

from scanner import db, run


def test_save_buyback_payload_carries_last_buy_date_and_null_dates(monkeypatch):
    captured = {}
    monkeypatch.setattr(db, "upsert_buybacks", lambda rows: captured.setdefault("bb", rows))
    monkeypatch.setattr(db, "log_scan", lambda *a, **kw: captured.setdefault("scan", a) or 1)
    row = {"symbol": "VRLLOG", "premium": 0.13, "entitlement_small": None, "buyback_price": 320.0,
           "cur_price": 282.0, "record_date": pd.NaT, "close_date": pd.NaT, "is_open": True,
           "last_buy_date": date(2026, 10, 9), "exp_return": 0.06}
    run._save_buyback([row], {"pages_seen": 8})
    payload = captured["scan"][2][0]["payload"]
    assert payload["last_buy_date"] == "2026-10-09"
    assert payload["record_date"] is None and payload["close_date"] is None
    assert payload["is_open"] is True
