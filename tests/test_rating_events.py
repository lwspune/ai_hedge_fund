"""Test-first spec for the rating-change event builder (scripts/validate_rating_change.py):
credit_ratings rows -> dated up / down / watch / affirm events for the event study."""
from datetime import date

from scanner.ratingevents import rating_events


def _r(symbol="ABC", agency="CRISIL", rating="A", notch=6, action="reaffirmed", prev=None, watch=None,
       at="2025-03-10T12:00:00+05:30", seq=1, scale="domestic", term="long"):
    return {"seq_id": seq, "symbol": symbol, "agency": agency, "scale": scale, "term": term, "rating": rating,
            "notch": notch, "action": action, "prev_rating": prev, "watch": watch, "disclosed_at": at}


def _kinds(events):
    return [(e["symbol"], e["kind"], e["delta"]) for e in events]


def test_stated_previous_rating_gives_direction_and_size():
    ev = rating_events([_r(rating="A+", notch=5, action="upgraded", prev="A-"),
                        _r(symbol="XYZ", rating="BBB", notch=9, action="downgraded", prev="A-", seq=2)])
    assert _kinds(ev) == [("ABC", "up", 2), ("XYZ", "down", -2)]


def test_history_supplies_the_previous_rating_when_the_filing_omits_it():
    ev = rating_events([_r(rating="A", notch=6, action="reaffirmed", at="2025-01-05T12:00:00+05:30", seq=1),
                        _r(rating="A-", notch=7, action="revised", at="2025-11-20T12:00:00+05:30", seq=2)])
    assert _kinds(ev) == [("ABC", "affirm", 0), ("ABC", "down", -1)]


def test_history_is_ignored_when_stale_or_contradicted_or_another_agency():
    rows = [_r(rating="AA", notch=3, at="2023-01-05T12:00:00+05:30", seq=1),
            _r(rating="A", notch=6, action="revised", at="2025-01-05T12:00:00+05:30", seq=2)]   # > 400 days
    assert [e["kind"] for e in rating_events(rows)] == ["affirm"]          # the old row; the revision has no base
    rows = [_r(rating="AA", notch=3, at="2025-01-05T12:00:00+05:30", seq=1),
            _r(rating="A", notch=6, action="reaffirmed", at="2025-06-05T12:00:00+05:30", seq=2)]   # says reaffirmed
    assert [e["kind"] for e in rating_events(rows)] == ["affirm", "affirm"]   # the filing's verb wins
    rows = [_r(agency="ICRA", rating="AA", notch=3, at="2025-01-05T12:00:00+05:30", seq=1),
            _r(agency="CRISIL", rating="A", notch=6, action="revised", at="2025-06-05T12:00:00+05:30", seq=2)]
    assert [e["kind"] for e in rating_events(rows)] == ["affirm"]


def test_verb_without_a_base_still_gives_direction():
    ev = rating_events([_r(action="downgraded", prev=None)])
    assert _kinds(ev) == [("ABC", "down", None)]


def test_verb_and_history_disagreeing_drops_the_row():
    rows = [_r(rating="BBB", notch=9, at="2025-01-05T12:00:00+05:30", seq=1),
            _r(rating="A", notch=6, action="downgraded", at="2025-06-05T12:00:00+05:30", seq=2)]
    assert [e["kind"] for e in rating_events(rows)] == ["affirm"]


def test_watch_placements_and_skipped_actions():
    ev = rating_events([_r(action="watch", watch="negative", seq=1),
                        _r(symbol="P", action="watch", watch="positive", seq=2),
                        _r(symbol="Q", action="assigned", seq=3),
                        _r(symbol="R", action="withdrawn", seq=4),
                        _r(symbol="S", action=None, seq=5)])
    assert _kinds(ev) == [("ABC", "watch_neg", None), ("P", "watch_pos", None)]


def test_investment_grade_and_default_flags():
    ev = rating_events([_r(rating="BB+", notch=11, action="downgraded", prev="BBB-", seq=1),
                        _r(symbol="D1", rating="D", notch=20, action="downgraded", prev="BB", seq=2),
                        _r(symbol="U", rating="BBB-", notch=10, action="upgraded", prev="BB+", seq=3),
                        _r(symbol="N", rating="BBB", notch=9, action="downgraded", prev="BBB+", seq=4)])
    flags = {e["symbol"]: (e["ig_cross"], e["default"]) for e in ev}
    assert flags == {"ABC": (True, False), "D1": (False, True), "U": (True, False), "N": (False, False)}


def test_after_hours_filings_move_to_the_next_day():
    ev = rating_events([_r(at="2025-03-10T15:29:00+05:30", seq=1),
                        _r(symbol="L", at="2025-03-10T15:30:00+05:30", seq=2),
                        _r(symbol="M", at="2025-03-10T09:40:00Z", seq=3)])       # 15:10 IST
    assert {e["symbol"]: e["event_date"] for e in ev} == {
        "ABC": date(2025, 3, 10), "L": date(2025, 3, 11), "M": date(2025, 3, 10)}


def test_one_event_per_symbol_and_kind_within_30_days():
    rows = [_r(agency="CRISIL", action="downgraded", prev="A", rating="A-", notch=7, at="2025-03-10T12:00:00+05:30", seq=1),
            _r(agency="ICRA", action="downgraded", prev="A", rating="A-", notch=7, at="2025-03-20T12:00:00+05:30", seq=2),
            _r(agency="CARE", action="downgraded", prev="A-", rating="BBB+", notch=8, at="2025-05-20T12:00:00+05:30", seq=3)]
    ev = rating_events(rows)
    assert [(e["agency"], e["event_date"]) for e in ev] == [("CRISIL", date(2025, 3, 10)), ("CARE", date(2025, 5, 20))]


def test_only_the_requested_scale_and_long_term():
    rows = [_r(action="downgraded", prev="A", rating="A-", notch=7, seq=1),
            _r(symbol="S", term="short", rating="A2", notch=4, action="downgraded", prev="A1", seq=2),
            _r(symbol="G", scale="global", agency="Fitch", rating="BB", notch=12, action="downgraded", prev="BB+", seq=3)]
    assert [e["symbol"] for e in rating_events(rows)] == ["ABC"]
    assert [e["symbol"] for e in rating_events(rows, scale="global")] == ["G"]
