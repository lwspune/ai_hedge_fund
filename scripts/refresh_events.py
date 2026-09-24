"""Refresh the corporate-events calendar (infra I3). Idempotent upserts.

    python scripts/refresh_events.py actions [--from 2025-01-01] [--to 2025-12-31]  # default: last 45d
    python scripts/refresh_events.py fo-ban  [--from 2024-01-01] [--to ...]         # default: last 10d
    python scripts/refresh_events.py rights  [--from-id 1] [--to-id 700]            # chittorgarh rights issues
    python scripts/refresh_events.py ipos    [--from-id 1] [--to-id 3000]           # default: frontier probe
                                                                                   #  + recheck last 120d
    python scripts/refresh_events.py holidays                                       # trading_calendar (weekly)
    python scripts/refresh_events.py board-meetings [--from ...] [--to ...]         # default: -10d..+90d
    python scripts/refresh_events.py bands                                          # price-band changes

All sources also work from GitHub Actions runners (scripts/probe_sources.py); chittorgarh and
the F&O ban archive are fetched politely (rate-limited).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.events import (  # noqa: E402
    calendar_rows, dedupe_events, fetch_band_changes, fetch_board_meetings, fetch_corp_actions,
    fetch_fo_ban, fetch_holidays, fetch_ipo, fetch_rights, holiday_descriptions, ipo_events,
    recheck_ids, rights_recheck_ids)

CHUNK = 500
GAP_STOP = 30      # consecutive missing IPO pages that end a frontier probe


def upsert_events(events: list[dict]) -> int:
    events = dedupe_events(events)
    for i in range(0, len(events), CHUNK):
        db.insert("corporate_events", events[i:i + CHUNK],
                  on_conflict="symbol,event_type,event_date,source", return_rows=False)
    return len(events)


def run_actions(frm: date, to: date) -> None:
    total, cur = 0, frm
    while cur <= to:  # quarter chunks keep nselib responses small
        end = min(cur + timedelta(days=90), to)
        ev = fetch_corp_actions(cur, end)
        total += upsert_events(ev)
        print(f"  actions {cur}..{end}: {len(ev)}")
        cur = end + timedelta(days=1)
    print(f"upserted {total} corporate-action events")


def run_fo_ban(frm: date, to: date) -> None:
    ev, d = [], frm
    while d <= to:
        if d.weekday() < 5:
            ev += fetch_fo_ban(d)
            time.sleep(0.3)
        d += timedelta(days=1)
    print(f"upserted {upsert_events(ev)} F&O-ban events")


def _ipo_frontier() -> int:
    rows = db.select("ipos", {"select": "chittorgarh_id", "order": "chittorgarh_id.desc", "limit": "1"})
    return max((rows[0]["chittorgarh_id"] if rows else 1) - 10, 1)


def run_recheck(days: int = 120) -> None:
    """Re-read recent IPO pages whose lock-in dates weren't published when first seen."""
    rows = db.select_all("ipos", {"select": "chittorgarh_id,listing_date,anchor_lockin_30,anchor_lockin_90"})
    ids, s, got = recheck_ids(rows, date.today(), days), requests.Session(), []
    for i in ids:
        try:
            _, row = fetch_ipo(i, s)
        except requests.RequestException as e:
            print(f"  recheck {i}: {e!r}"[:120])
            continue
        if row:
            got.append(row)
        time.sleep(0.4)
    _flush_ipos(got)
    print(f"rechecked {len(ids)} recent IPOs")


def run_ipos(from_id: int | None, to_id: int | None) -> None:
    s, i = requests.Session(), from_id or _ipo_frontier()
    gap, rows = 0, []
    while (to_id is None and gap < GAP_STOP) or (to_id is not None and i <= to_id):
        try:
            exists, row = fetch_ipo(i, s)
        except requests.RequestException as e:
            print(f"  {i}: {e!r}"[:120])
            exists, row = True, None
        gap = 0 if exists else gap + 1
        if row:
            rows.append(row)
        if len(rows) >= 100:
            _flush_ipos(rows)
            rows = []
        i += 1
        time.sleep(0.4)
    _flush_ipos(rows)
    print(f"ipo scan finished at id {i - 1}")


def _flush_ipos(rows: list[dict]) -> None:
    if not rows:
        return
    rows, rejected = db.upsert_resilient("ipos", rows, "chittorgarh_id")
    for r, err in rejected:  # a DB constraint rejected it: keep the good ones, log the bad
        print(f"  rejected ipo {r['chittorgarh_id']} {r['symbol']}: {err[-160:]}")
    if not rows:
        return
    n = upsert_events([e for r in rows for e in ipo_events(r)])
    print(f"  ipos: +{len(rows)} (last id {rows[-1]['chittorgarh_id']}), {n} events")


def run_rights(from_id: int | None, to_id: int | None) -> None:
    """chittorgarh rights-issue pages -> rights_issues. Default: probe up from the stored
    frontier (gap-stop) and re-read issues closing in the last 45 days (dates fill in late)."""
    s = requests.Session()
    stored = db.select_all("rights_issues", {"select": "chittorgarh_id,issue_close"})
    if from_id is None:
        top = max((r["chittorgarh_id"] for r in stored), default=1)
        ids = rights_recheck_ids(stored, date.today()) + list(range(max(top - 5, 1), top + 1))
        i, gap = top + 1, 0
    else:
        ids, i, gap = [], from_id, 0
    rows = []

    def take(rid):
        try:
            exists, row = fetch_rights(rid, s)
        except requests.RequestException as e:
            print(f"  rights {rid}: {e!r}"[:120])
            return True
        if row:
            rows.append(row)
        time.sleep(0.4)
        return exists

    for rid in sorted(set(ids)):
        take(rid)
    while (to_id is None and gap < GAP_STOP) or (to_id is not None and i <= to_id):
        gap = 0 if take(i) else gap + 1
        i += 1
    good, bad = db.upsert_resilient("rights_issues", rows, "chittorgarh_id")
    for r, err in bad:
        print(f"  rejected rights {r['chittorgarh_id']} {r['symbol']}: {err[-160:]}")
    print(f"upserted {len(good)} rights issues (scan ended at id {i - 1})")


MIN_HOLIDAYS = 8   # NSE has ~15 CM holidays a year; fewer = a truncated / changed response


def run_holidays() -> None:
    """NSE holiday master -> trading_calendar rows for every weekday of this and next year
    (next year's holidays appear once NSE publishes them, usually in December)."""
    raw = fetch_holidays()
    hol = holiday_descriptions(raw)
    if len(hol) < MIN_HOLIDAYS:
        raise SystemExit(f"holiday master returned {len(hol)} CM holidays (< {MIN_HOLIDAYS}); not writing")
    this = date.today().year
    rows = calendar_rows(hol, this) + calendar_rows(hol, this + 1)
    for i in range(0, len(rows), CHUNK):
        db.insert("trading_calendar", rows[i:i + CHUNK], on_conflict="trade_date", return_rows=False)
    print(f"trading_calendar: {len(rows)} weekdays, {len(hol)} holidays")


def run_board_meetings(frm: date, to: date) -> None:
    """Board meetings / results dates, one NSE call per 30 days."""
    total, cur = 0, frm
    while cur <= to:
        end = min(cur + timedelta(days=29), to)
        ev = fetch_board_meetings(cur, end)
        total += upsert_events(ev)
        print(f"  board meetings {cur}..{end}: {len(ev)} "
              f"({sum(e['event_type'] == 'results' for e in ev)} results)")
        cur = end + timedelta(days=1)
        time.sleep(0.5)
    if total == 0:
        raise SystemExit(f"no board meetings {frm}..{to} — the NSE response changed?")
    print(f"upserted {total} board-meeting events")


def run_bands() -> None:
    ev = fetch_band_changes()  # can legitimately be empty
    print(f"upserted {upsert_events(ev)} band-change events")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["actions", "fo-ban", "ipos", "rights", "holidays",
                                     "board-meetings", "bands"])
    ap.add_argument("--from", dest="frm", type=date.fromisoformat)
    ap.add_argument("--to", type=date.fromisoformat)
    ap.add_argument("--from-id", type=int)
    ap.add_argument("--to-id", type=int)
    a = ap.parse_args()
    today = date.today()
    if a.what == "actions":
        run_actions(a.frm or today - timedelta(days=45), a.to or today)
    elif a.what == "fo-ban":
        run_fo_ban(a.frm or today - timedelta(days=10), a.to or today)
    elif a.what == "rights":
        run_rights(a.from_id, a.to_id)
    elif a.what == "holidays":
        run_holidays()
    elif a.what == "board-meetings":  # recent (late intimations) + the next quarter's results season
        run_board_meetings(a.frm or today - timedelta(days=10), a.to or today + timedelta(days=90))
    elif a.what == "bands":
        run_bands()
    else:
        run_ipos(a.from_id, a.to_id)
        if a.from_id is None:  # daily mode: also refresh recent pages (lock-in dates fill in late)
            run_recheck()


if __name__ == "__main__":
    main()
