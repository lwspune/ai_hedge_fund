"""Refresh the corporate-events calendar (infra I3). Idempotent upserts.

    python scripts/refresh_events.py actions [--from 2025-01-01] [--to 2025-12-31]  # default: last 45d
    python scripts/refresh_events.py fo-ban  [--from 2024-01-01] [--to ...]         # default: last 10d
    python scripts/refresh_events.py ipos    [--from-id 1] [--to-id 3000]           # default: frontier probe

nselib (actions) needs a residential IP; F&O ban + chittorgarh are static and polite-rate-limited.
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
    dedupe_events, fetch_corp_actions, fetch_fo_ban, fetch_ipo, ipo_events)

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
    db.insert("ipos", rows, on_conflict="chittorgarh_id", return_rows=False)
    n = upsert_events([e for r in rows for e in ipo_events(r)])
    print(f"  ipos: +{len(rows)} (last id {rows[-1]['chittorgarh_id']}), {n} events")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["actions", "fo-ban", "ipos"])
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
    else:
        run_ipos(a.from_id, a.to_id)


if __name__ == "__main__":
    main()
