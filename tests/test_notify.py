"""Telegram alerts for new Act candidates: which candidates alert, their dedup keys, the text."""
from scanner.notify import buyback_alerts, new_alerts, rights_alerts


def _bb(symbol="TCS", is_open=True, **kw):
    payload = {"premium": 0.12, "entitlement_small": 0.18, "est_acceptance": 0.4, "est_floor": 0.01,
               "exp_return": 0.035, "is_open": is_open, "buyback_price": 4500.0, "cur_price": 4017.0,
               "record_date": "2026-09-30", "close_date": "2026-10-10", **kw}
    return {"symbol": symbol, "score": payload["exp_return"], "payload": payload}


def _re(symbol="SATIN", action="BUY RE (instead of the stock; subscribe)", **kw):
    payload = {"ratio": "1:5", "issue_price": 100.0, "stock": 150.0, "re": 47.0, "gap": 0.02,
               "turnover": 9e5, "re_date": "2026-09-24", "re_last_day": "2026-09-29",
               "issue_close": "2026-10-03", "action": action, **kw}
    return {"symbol": symbol, "score": payload["gap"], "payload": payload}


def test_buyback_alerts_only_open_tenders_keyed_by_symbol_and_record_date():
    got = buyback_alerts([_bb("TCS"), _bb("INFY", is_open=False)])
    assert [a["alert_key"] for a in got] == ["TCS|2026-09-30"]
    assert got[0]["signal_name"] == "buyback_arb"


def test_buyback_text_carries_the_numbers_and_the_tax_caveat():
    text = buyback_alerts([_bb()])[0]["text"]
    for s in ("TCS", "4,500", "4,017", "12.0%", "40%", "3.5%", "2026-09-30", "2026-10-10", "≤20%"):
        assert s in text
    assert "#/company/TCS" in text


def test_buyback_missing_exp_return_renders_a_dash_not_a_crash():
    text = buyback_alerts([_bb(exp_return=None, est_acceptance=None)])[0]["text"]
    assert "exp after-tax —" in text


def test_rights_alerts_only_buy_re_keyed_by_symbol_and_re_last_day():
    got = rights_alerts([_re("SATIN"), _re("X", action="fair"), _re("Y", action="illiquid"),
                         _re("Z", action="RE rich: holders sell RE, buy stock")])
    assert [a["alert_key"] for a in got] == ["SATIN|2026-09-29"]
    text = got[0]["text"]
    for s in ("SATIN", "2.0%", "100.00", "2026-09-29", "2026-10-03"):
        assert s in text


def test_text_is_html_escaped():
    text = buyback_alerts([_bb("M&M")])[0]["text"]
    assert "M&amp;M" in text and "M&M<" not in text


def test_new_alerts_drops_already_sent_and_duplicates_within_a_batch():
    a = buyback_alerts([_bb("TCS"), _bb("TCS"), _bb("INFY")])
    got = new_alerts(a, {("buyback_arb", "INFY|2026-09-30")})
    assert [x["alert_key"] for x in got] == ["TCS|2026-09-30"]
