"""Daily ASM / GSM snapshot -> `surveillance_daily` (scanner/surveillance.py).

    python scripts/refresh_surveillance.py            # today's lists; prints entries/exits vs the last snapshot

The lists are snapshots, so this must run every trading day for the history to exist. An
empty ASM response (both lists) fails the run: the format changed, not the market.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.surveillance import fetch_asm, fetch_gsm, parse_asm, parse_gsm, session, transitions  # noqa: E402

CHUNK = 500


def previous_snapshot(before: str) -> list[dict]:
    last = db.select("surveillance_daily", {"select": "as_of", "as_of": f"lt.{before}",
                                            "order": "as_of.desc", "limit": "1"})
    if not last:
        return []
    return db.select_all("surveillance_daily", {"select": "symbol,list_name,stage", "as_of": f"eq.{last[0]['as_of']}"})


def main():
    today = date.today()
    s = session()
    rows = parse_asm(fetch_asm(s), today) + parse_gsm(fetch_gsm(s), today)
    if not any(r["list_name"].startswith("asm") for r in rows):
        raise SystemExit("ASM lists came back empty — response format changed?")
    prev = previous_snapshot(today.isoformat())
    for i in range(0, len(rows), CHUNK):
        db.insert("surveillance_daily", rows[i:i + CHUNK], on_conflict="as_of,symbol,list_name", return_rows=False)
    t = transitions(prev, rows)
    counts = {k: sum(r["list_name"] == k for r in rows) for k in ("asm_lt", "asm_st", "gsm")}
    print(f"surveillance {today}: {counts} | entries {len(t['entries'])} exits {len(t['exits'])} "
          f"stage changes {len(t['stage_changes'])}")
    for sym, lst in t["entries"]:
        print(f"  + {sym} {lst}")
    for sym, lst in t["exits"]:
        print(f"  - {sym} {lst}")


if __name__ == "__main__":
    main()
