"""Rating-change events for the event study (scripts/validate_rating_change.py): credit_ratings
rows -> one dated event per rating action that says something.

  up / down   the grade moved: from the filing's stated previous rating, else from our own last
              row for the same symbol + agency within HISTORY_DAYS (only when the filing's verb
              doesn't contradict it); a bare "upgraded"/"downgraded" still gives the direction
  watch_neg / watch_pos   placed on rating watch
  affirm      reaffirmed at the same grade — the control: same kind of filing, no news

Assignments (a new rating, no base), withdrawals and verb-less rows are not events. A filing made
at or after the 15:30 IST close counts from the next day. One event per symbol and kind within
CLUSTER_DAYS (several agencies acting on the same news). Pure; tested in tests/test_rating_events.py.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from scanner.ratings import notch

HISTORY_DAYS = 400      # agencies review every ~12 months
CLUSTER_DAYS = 30
IG_FLOOR = 10           # BBB- / Baa3: the last investment-grade notch
DEFAULT = 20            # D
_IST = timezone(timedelta(hours=5, minutes=30))
_CLOSE = (15, 30)


def _ist(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_IST)


def event_day(ts: str) -> date:
    """The first day the market can react: the filing's IST date, or the next day after the close."""
    t = _ist(ts)
    return t.date() + timedelta(days=1) if (t.hour, t.minute) >= _CLOSE else t.date()


def _classify(row: dict, base: int | None) -> tuple[str, int | None] | None:
    """(kind, delta in notches, + = better) or None when the row isn't an event."""
    action, n = row["action"], row["notch"]
    verb = {"upgraded": "up", "downgraded": "down"}.get(action)
    stated = notch(row["prev_rating"] or "", "long")
    if stated is not None and stated != n:
        return ("up" if n < stated else "down"), stated - n
    if action == "watch":
        kind = {"negative": "watch_neg", "positive": "watch_pos"}.get(row["watch"])
        return (kind, None) if kind else None
    if action == "reaffirmed" or (stated is not None and stated == n):
        return "affirm", 0
    if (verb or action == "revised") and base is not None and base != n:
        moved = "up" if n < base else "down"
        if verb and moved != verb:
            return None                    # the verb and our history disagree: trust neither
        return moved, base - n
    if verb:
        return verb, None
    return None


def rating_events(rows: list[dict], scale: str = "domestic") -> list[dict]:
    rows = sorted((r for r in rows if r["scale"] == scale and r["term"] == "long" and r["notch"]),
                  key=lambda r: (_ist(r["disclosed_at"]), r["seq_id"]))
    last: dict = {}                        # (symbol, agency) -> (datetime, notch) of the latest usable row
    events = []
    for r in rows:
        key, when = (r["symbol"], r["agency"]), _ist(r["disclosed_at"])
        prior = last.get(key)
        base = prior[1] if prior and (when - prior[0]).days <= HISTORY_DAYS else None
        if r["action"] == "withdrawn":
            last.pop(key, None)
            continue
        last[key] = (when, r["notch"])
        got = _classify(r, base)
        if not got or not got[0]:
            continue
        kind, delta = got
        before = r["notch"] + delta if delta is not None else None
        events.append({
            "seq_id": r["seq_id"], "symbol": r["symbol"], "agency": r["agency"], "kind": kind, "delta": delta,
            "notch": r["notch"], "prev_notch": before, "event_date": event_day(r["disclosed_at"]),
            "ig_cross": before is not None and (before <= IG_FLOOR) != (r["notch"] <= IG_FLOOR),
            "default": kind == "down" and r["notch"] == DEFAULT})
    return _cluster(events)


def _cluster(events: list[dict]) -> list[dict]:
    out, seen = [], {}
    for e in sorted(events, key=lambda e: (e["event_date"], e["seq_id"])):
        k = (e["symbol"], e["kind"])
        if k in seen and (e["event_date"] - seen[k]).days <= CLUSTER_DAYS:
            continue
        seen[k] = e["event_date"]
        out.append(e)
    return out
