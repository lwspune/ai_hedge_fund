"""Quarterly shareholding + promoter pledge -> `shareholding` (scanner/shareholding.py).

    python scripts/refresh_shareholding.py                       # weekly: every listed symbol, 2 new quarters each
    python scripts/refresh_shareholding.py --symbols A,B         # a few symbols
    python scripts/refresh_shareholding.py --per-symbol 30 --xbrl-limit 20000 --floor 2020-01-01   # backfill

One NSE master call per symbol (cheap) tells which quarters exist; only quarters not yet stored
(on/after --floor) get their XBRL fetched, newest first, up to --per-symbol per company and
--xbrl-limit per run — the current quarter fills market-wide first, history deepens over runs.
Every processed symbol's latest quarter is re-upserted with the master's headline fields (+
updated_at), which is what the freshness rule watches.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.shareholding import (  # noqa: E402
    fetch_shp_master, fetch_xbrl, parse_shp_xbrl, quarters_to_fetch, session, shareholding_row)

CHUNK = 200
FLOOR = "2020-01-01"


def listed_symbols() -> list[str]:
    rows = db.select_all("companies", {"select": "symbol", "status": "eq.listed", "order": "symbol"})
    return [r["symbol"] for r in rows]


def stored_quarters() -> dict[str, set]:
    out = defaultdict(set)
    for r in db.select_all("shareholding", {"select": "symbol,quarter_end"}):
        out[r["symbol"]].add(r["quarter_end"])
    return out


def _flush(rows: list[dict]) -> int:
    n = 0
    for i in range(0, len(rows), CHUNK):
        good, bad = db.upsert_resilient("shareholding", rows[i:i + CHUNK], "symbol,quarter_end")
        for r, err in bad:
            print(f"  rejected {r['symbol']} {r['quarter_end']}: {err[-120:]}")
        n += len(good)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols")
    ap.add_argument("--per-symbol", type=int, default=2)
    ap.add_argument("--xbrl-limit", type=int, default=3000)
    ap.add_argument("--floor", default=FLOOR)
    a = ap.parse_args()
    symbols = a.symbols.split(",") if a.symbols else listed_symbols()
    stored = stored_quarters()
    now = datetime.now(timezone.utc).isoformat()
    s, budget, rows, touched, fetched, failed = session(), a.xbrl_limit, [], [], 0, 0
    for k, sym in enumerate(symbols, 1):
        try:
            master = fetch_shp_master(sym, s)
        except requests.RequestException as e:
            failed += 1
            print(f"  {sym}: master {e!r}"[:120])
            if failed > 50 and fetched == 0:
                raise SystemExit("NSE shareholding master unreachable — stopping")
            time.sleep(1)
            continue
        if master:  # headline refresh of the newest quarter (no XBRL): the freshness heartbeat
            m = master[0]
            touched.append({"symbol": m["symbol"], "quarter_end": m["quarter_end"], "broadcast_at": m["broadcast_at"],
                            "promoter_pct": m["promoter_pct"], "public_pct": m["public_pct"], "revised": m["revised"],
                            "xbrl_url": m["xbrl_url"], "updated_at": now})
        for q in quarters_to_fetch(master, stored.get(sym, set()), limit=a.per_symbol, floor=a.floor):
            if budget <= 0:
                break
            try:
                xb = parse_shp_xbrl(fetch_xbrl(q["xbrl_url"], s))
            except requests.RequestException as e:
                print(f"  {sym} {q['quarter_end']}: xbrl {e!r}"[:120])
                continue
            budget -= 1
            fetched += 1
            rows.append({**shareholding_row(q, xb), "updated_at": now})
            time.sleep(0.2)
        if len(rows) >= CHUNK:
            _flush(rows)
            rows = []
        if len(touched) >= CHUNK:
            _flush(touched)
            touched = []
        if k % 200 == 0:
            print(f"  {k}/{len(symbols)} symbols, {fetched} XBRL fetched, budget left {budget}", flush=True)
        time.sleep(0.25)
    _flush(rows)
    _flush(touched)
    print(f"shareholding: {len(symbols)} symbols, {fetched} quarters parsed, {failed} master failures")
    if symbols and failed >= len(symbols):
        raise SystemExit("every master call failed")


if __name__ == "__main__":
    main()
