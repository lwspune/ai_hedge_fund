"""Preferential allotments -> `pref_issues` + lock-in expiry events (scanner/prefissues.py).

    python scripts/refresh_prefissues.py                          # daily: submissions in the last 45 days
    python scripts/refresh_prefissues.py --from 2023-01-01        # backfill, calendar-year windows

Both stages are pulled; listing-stage rows without stored lock-in tranches get their XBRL read
(`lockins`, `shares_listed`), then every listing row's tranches become `pref_lockin_expiry`
rows in corporate_events (source `nse_pref`).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.events import dedupe_events  # noqa: E402
from scanner.prefissues import fetch_pref, fetch_xbrl, lockin_expiry_events, parse_pref_ls_xbrl, session  # noqa: E402

CHUNK = 300


def windows(frm: date, to: date):
    cur = frm
    while cur <= to:
        end = min(date(cur.year, 12, 31), to)
        yield cur, end
        cur = end + timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", type=date.fromisoformat)
    ap.add_argument("--to", type=date.fromisoformat, default=date.today())
    a = ap.parse_args()
    frm = a.frm or a.to - timedelta(days=45)
    s, now = session(), datetime.now(timezone.utc).isoformat()
    have = {r["app_id"]: r for r in db.select_all("pref_issues", {"select": "app_id,lockins,shares_listed"})}
    rows = []
    for lo, hi in windows(frm, a.to):
        for stage in ("in_principle", "listing"):
            got = fetch_pref(stage, lo, hi, s)
            rows += got
            print(f"  {stage} {lo}..{hi}: {len(got)}", flush=True)
            time.sleep(0.5)
    rows = list({r["app_id"]: r for r in rows}.values())
    parsed, failed = 0, 0
    for r in rows:
        r["updated_at"] = now
        if r["stage"] != "listing":
            continue
        prev = have.get(r["app_id"])
        if prev and prev.get("lockins") is not None:
            r["lockins"], r["shares_listed"] = prev["lockins"], prev.get("shares_listed")
            continue
        if not r["xml_url"]:
            r["lockins"] = []
            continue
        try:
            x = parse_pref_ls_xbrl(fetch_xbrl(r["xml_url"], s))
            r["lockins"], r["shares_listed"] = x["lockins"], x["shares_listed"]
            r["allotment_date"] = r["allotment_date"] or x["allotment_date"]
            parsed += 1
        except requests.RequestException as e:
            failed += 1
            print(f"  {r['app_id']} {r['symbol']}: xbrl {e!r}"[:120])
            r["lockins"] = None   # unread: try again next run
        time.sleep(0.2)
    n = 0
    for i in range(0, len(rows), CHUNK):
        good, bad = db.upsert_resilient("pref_issues", rows[i:i + CHUNK], "app_id")
        for r, err in bad:
            print(f"  rejected {r['app_id']} {r['symbol']}: {err[-120:]}")
        n += len(good)
    events = dedupe_events(lockin_expiry_events([r for r in rows if r.get("lockins") is not None]))
    for i in range(0, len(events), CHUNK):
        db.insert("corporate_events", events[i:i + CHUNK],
                  on_conflict="symbol,event_type,event_date,source", return_rows=False)
    print(f"upserted {n} pref issues ({parsed} XBRL parsed, {failed} failed), {len(events)} lock-in expiry events")
    if rows and n == 0:
        raise SystemExit("nothing stored")


if __name__ == "__main__":
    main()
