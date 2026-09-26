"""Named SHP holders per filing -> bucket `holders/<SYMBOL>.parquet` (scanner/holders.py).

    python scripts/refresh_holders.py                          # weekly: every quarter not yet read
    python scripts/refresh_holders.py --symbols GRAVITA,DMART
    python scripts/refresh_holders.py --shard 2/6 --max-minutes 320   # backfill.yml what=holders

Universe: listed companies + companies delisted since 2021-06-30 (the master reaches Sep-2021;
dropping the delisted would make every investor look better than they were). One NSE master call
per symbol; each quarter not yet in the symbol's parquet gets its XBRL read. A file that isn't an
SHP (NSE sometimes links a 404 page) is skipped and retried next run. Resumable: a symbol is saved
as soon as it is done, and the run stops cleanly at --max-minutes.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.holders import COLUMNS, FILING, filing_rows, load_symbol, save_symbol  # noqa: E402
from scanner.shareholding import (  # noqa: E402
    fetch_shp_master, fetch_xbrl, parse_shp_holders, quarters_to_fetch, session)

DELISTED_SINCE = "2021-06-30"


def universe() -> list[str]:
    rows = db.select_all("companies", {"select": "symbol,status,delisted_on", "order": "symbol",
                                       "or": f"(status.eq.listed,delisted_on.gte.{DELISTED_SINCE})"})
    return [r["symbol"] for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols")
    ap.add_argument("--shard", default="0/1", help="i/n: this run takes every n-th symbol from i")
    ap.add_argument("--max-minutes", type=float, default=0, help="stop cleanly after this long (0 = no limit)")
    a = ap.parse_args()
    i, n = (int(x) for x in a.shard.split("/"))
    symbols = a.symbols.split(",") if a.symbols else universe()
    symbols = symbols[i::n]
    t0, s = time.monotonic(), session()
    done = fetched = failed = skipped = 0
    for k, sym in enumerate(symbols, 1):
        if a.max_minutes and (time.monotonic() - t0) / 60 > a.max_minutes:
            print(f"time budget reached: {len(symbols) - k + 1} symbols left for the next run")
            break
        try:
            master = fetch_shp_master(sym, s)
        except (requests.RequestException, ValueError) as e:
            failed += 1
            print(f"  {sym}: master {e!r}"[:120])
            if failed > 50 and fetched == 0:
                raise SystemExit("NSE shareholding master unreachable — stopping")
            time.sleep(1)
            continue
        old = load_symbol(sym, refresh=True)
        have = set(old.loc[old["axis"] == FILING, "quarter_end"]) if old is not None else set()
        new = []
        for q in quarters_to_fetch(master, have):
            try:
                xml = fetch_xbrl(q["xbrl_url"], s)
            except requests.RequestException as e:
                print(f"  {sym} {q['quarter_end']}: xbrl {e!r}"[:120])
                continue
            fetched += 1
            if "ShareholdingPatternMember" not in xml:
                skipped += 1
                continue
            new += filing_rows({**q, "symbol": sym}, parse_shp_holders(xml))
            time.sleep(0.15)
        if new:
            df = pd.DataFrame(new, columns=COLUMNS)
            if old is not None:
                df = pd.concat([old, df], ignore_index=True)
            save_symbol(sym, df)
            done += 1
        if k % 100 == 0:
            print(f"  {k}/{len(symbols)} symbols, {fetched} XBRL read, {done} saved "
                  f"({(time.monotonic() - t0) / 60:.0f} min)", flush=True)
        time.sleep(0.2)
    print(f"holders: {len(symbols)} symbols (shard {a.shard}), {fetched} XBRL read, {skipped} not SHP, "
          f"{done} symbols saved, {failed} master failures")
    if symbols and failed >= len(symbols):
        raise SystemExit("every master call failed")


if __name__ == "__main__":
    main()
