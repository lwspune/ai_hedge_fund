"""Load NSE daily bhavcopies into the cloud price store (DATA_INFRA_SPEC WP3).

    python scripts/refresh_prices.py                          # last 5 calendar days (heals a missed run)
    python scripts/refresh_prices.py --date 2026-09-23
    python scripts/refresh_prices.py --from 2024-01-01 --to 2024-12-31   # backfill (backfill.yml)
    python scripts/refresh_prices.py --prune                  # weekly: drop table rows > KEEP_DAYS
    python scripts/refresh_prices.py --indices-only --from 2020-01-01 --to 2022-07-31   # benchmarks only (backfill.yml what=indices)

Per trading day: fetch sec_bhavdata_full -> parse (guarded) -> `reload_daily_prices` RPC (only
for dates inside the table's retention window, so a backfill never bloats Postgres) -> merged
into that month's raw parquet in the private `prices` bucket (bhav/YYYY-MM.parquet: every
series and column, the durable history). Past weekdays with no file are recorded as holidays
in `trading_calendar` (source nse_bhavcopy) — historical trading days for validations. Also
refreshes `index_prices` (Yahoo benchmarks) for the same window; a stock session Yahoo has no close
for (Muhurat, Budget Saturdays, some 1 Jan / 26 Dec) is filled from NSE's daily index-close file,
checked against the previous close + NSE's change before it is stored.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.bhavcopy import confirm_close, fetch_index_closes, parse_index_closes  # noqa: E402
from scanner.sectors import load_sector_indices, sector_symbols  # noqa: E402

KEEP_DAYS = 400                       # daily_prices retention (400 d since 2026-09-30, was 730); older rows live in the bucket only
BENCHMARKS = ("^NSEI", "^CRSLDX")     # NIFTY 50, NIFTY 500
POLITE = 0.3


# --- pure helpers ---------------------------------------------------------------

def in_table_window(d: date, today: date, keep_days: int = KEEP_DAYS) -> bool:
    return d >= today - timedelta(days=keep_days)


def months_of(dates) -> dict:
    out: dict = {}
    for d in sorted(dates):
        out.setdefault(f"{d:%Y-%m}", []).append(d)
    return out


def file_is_for(rows: list[dict], d: date) -> bool:
    """False for NSE's holiday copies: on a holiday the archive serves the previous session's
    file under the holiday's name (2026-09-14 Ganesh Chaturthi -> 2026-09-11 data)."""
    return bool(rows) and rows[0]["trade_date"] == d.isoformat()


def calendar_from_presence(checked, present: set, today: date) -> list[dict]:
    """trading_calendar rows from which past weekdays had a bhavcopy (today is not final yet)."""
    return [{"trade_date": d.isoformat(), "is_trading": d in present, "description": None,
             "source": "nse_bhavcopy"}
            for d in sorted(checked) if d.weekday() < 5 and d < today]


# --- I/O -------------------------------------------------------------------------

def _load_month(ym: str) -> pd.DataFrame | None:
    from scanner import db
    blob = db.storage_get("prices", f"bhav/{ym}.parquet")
    return pd.read_parquet(io.BytesIO(blob)) if blob else None


def _save_month(ym: str, df: pd.DataFrame) -> None:
    from scanner import db
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="zstd")
    db.storage_put("prices", f"bhav/{ym}.parquet", buf.getvalue(), "application/vnd.apache.parquet")


MAX_BRIDGE_DAYS = 10     # a special session the bhavcopy store lacks sits within a few calendar days


def _bridge(sym: str, prev_day: date, prev: float, d: date, rec: dict, lookup) -> list[tuple] | None:
    """Sessions between `prev_day` and `d` that NSE has but the stock store doesn't (Muhurat, a Budget
    Saturday): [(date, close), ...] that chain prev -> ... -> d, or None if no such chain exists."""
    if lookup is None or (d - prev_day).days > MAX_BRIDGE_DAYS:
        return None
    chain, p = [], prev
    for k in range(1, (d - prev_day).days):
        day = prev_day + timedelta(days=k)
        r = (lookup(day) or {}).get(sym)
        if r and r["date"] == day and confirm_close(p, r["close"], r["change"]):
            chain.append((day, r["close"]))
            p = r["close"]
    return chain if chain and confirm_close(p, rec["close"], rec["change"]) else None


def plan_fallback(missing: dict, parsed: dict, known: dict, allow_first: bool = False,
                  lookup=None) -> tuple[list[dict], list[tuple]]:
    """Rows to store from NSE's index-close files, and (sym, date, why) for the rest. A close is stored
    only if the file is for that day and NSE's change from the previous known close agrees
    (`confirm_close`); dates are walked in order so a filled day checks the next one. `allow_first`: an
    index with no earlier close at all (a sector index's first day) is stored on the date match alone.
    `lookup(date) -> parsed file`: when the check fails, the calendar days in between are searched for a
    special session that chains (stored too) — without it one Muhurat day would fail every day after."""
    rows, skipped = [], []
    for sym, days in missing.items():
        closes = dict(known.get(sym, {}))
        for d in sorted(days):
            f = parsed.get(d)
            rec = (f or {}).get(sym)
            prev_days = [x for x in closes if x < d]
            prev = closes[max(prev_days)] if prev_days else None
            first = allow_first and not prev_days     # nothing earlier (later daily rows may already exist)
            why = ("no NSE file" if f is None else f"{sym} not in the file" if rec is None
                   else f"file is for {rec['date']}" if rec["date"] != d
                   else None if first or confirm_close(prev, rec["close"], rec["change"])
                   else f"close {rec['close']} - change {rec['change']} != previous close {prev}")
            if why and rec is not None and rec["date"] == d and prev is not None:
                chain = _bridge(sym, max(prev_days), prev, d, rec, lookup)
                if chain:
                    for day, c in chain:
                        closes[day] = c
                        rows.append({"index_symbol": sym, "trade_date": day.isoformat(), "close": c})
                    why = None
            if why:
                skipped.append((sym, d, why))
                continue
            closes[d] = rec["close"]
            rows.append({"index_symbol": sym, "trade_date": d.isoformat(), "close": rec["close"]})
    return rows, skipped


# --- thin I/O for refresh_indices (monkeypatched in tests) ----------------------------------------

def _yahoo_closes(frm: date, to: date) -> dict:
    import yfinance as yf
    out = {}
    for sym in BENCHMARKS:
        h = yf.Ticker(sym).history(start=frm.isoformat(), end=(to + timedelta(days=1)).isoformat(),
                                   interval="1d", auto_adjust=False)
        if h is None or h.empty:
            raise SystemExit(f"yfinance returned nothing for {sym} {frm}..{to}")
        out[sym] = {pd.Timestamp(i).date(): float(c) for i, c in h["Close"].dropna().items() if c > 0}
    return out


def _known_closes(frm: date, to: date) -> dict:
    from scanner import db
    out = {s: {} for s in BENCHMARKS}
    for r in db.select_all("index_prices", {"select": "index_symbol,trade_date,close",
                                            "and": f"(trade_date.gte.{frm},trade_date.lte.{to})"}):
        if r["index_symbol"] in out:
            out[r["index_symbol"]][date.fromisoformat(r["trade_date"])] = float(r["close"])
    return out


def _insert_index_rows(rows: list[dict]) -> None:
    from scanner import db
    for i in range(0, len(rows), 1000):
        db.insert("index_prices", rows[i:i + 1000], on_conflict="index_symbol,trade_date", return_rows=False)


_FILES: dict = {}


def _index_file(d: date) -> str | None:
    """NSE's index-close file for `d`, fetched once per process (benchmarks and sectors share it)."""
    if d not in _FILES:
        _FILES[d] = fetch_index_closes(d)
        time.sleep(POLITE)
    return _FILES[d]


def _parsed_file(d: date, names: dict | None):
    """The day's index-close file parsed for `names` (None = the benchmarks); None if NSE has no file."""
    text = _index_file(d)
    return parse_index_closes(text, names) if text else None


def _known_closes_for(symbols: list[str], frm: date, to: date) -> dict:
    from scanner import db
    out = {s: {} for s in symbols}
    names = ",".join(f'"{s}"' for s in symbols)
    for r in db.select_all("index_prices", {"select": "index_symbol,trade_date,close", "index_symbol": f"in.({names})",
                                            "and": f"(trade_date.gte.{frm},trade_date.lte.{to})"}):
        out[r["index_symbol"]][date.fromisoformat(r["trade_date"])] = float(r["close"])
    return out


def _last_closes_before(symbols: list[str], d: date) -> dict:
    """{symbol: (date, close)} of each index's latest stored close before `d` (absent if none)."""
    from scanner import db
    out = {}
    for s in symbols:
        rows = db.select("index_prices", {"select": "trade_date,close", "index_symbol": f"eq.{s}",
                                          "trade_date": f"lt.{d}", "order": "trade_date.desc", "limit": "1"})
        if rows:
            out[s] = (date.fromisoformat(rows[0]["trade_date"]), float(rows[0]["close"]))
    return out


def refresh_sectors(sessions) -> int:
    """NSE sector indices (data/sector_indices.csv) for each session, from NSE's index-close file. A close
    is stored only if the file is for that day and agrees with the index's previous close (its first-ever
    close: the date match alone). Prints per index what was stored and why anything else was skipped."""
    from collections import Counter
    syms, names = sector_symbols(), load_sector_indices()
    days = sorted(sessions)
    if not days:
        return 0
    known = _known_closes_for(syms, days[0], days[-1])
    for s, (d, c) in _last_closes_before(syms, days[0]).items():
        known.setdefault(s, {})[d] = c
    missing = {s: [d for d in days if d not in known.get(s, {})] for s in syms}
    parsed = {}
    for d in sorted({d for v in missing.values() for d in v}):
        text = _index_file(d)
        parsed[d] = parse_index_closes(text, names) if text else None
    rows, skipped = plan_fallback(missing, parsed, known, allow_first=True,
                                  lookup=lambda day: _parsed_file(day, names))
    _insert_index_rows(rows)
    stored = Counter(r["index_symbol"] for r in rows)
    first = {}
    for r in rows:
        first.setdefault(r["index_symbol"], r["trade_date"])
    for s in syms:
        if stored[s]:
            print(f"  {s}: {stored[s]} closes from {first[s]}")
    seen = {}                                     # first file each index appears in (before it: not launched)
    for d in sorted(parsed):
        for s in parsed[d] or {}:
            seen.setdefault(s, d)
    real = [(s, d, why) for s, d, why in skipped
            if not ("not in the file" in why and d < seen.get(s, date.max))]
    for s, d, why in real[:40]:
        print(f"  WARN {d} {s}: {why}")
    if len(real) > 40:
        print(f"  ... {len(real) - 40} more skipped")
    return len(rows)


def _bucket_sessions(frm: date, to: date) -> set:
    from scanner.pricestore import _bhav_month
    days = set()
    for ym in pd.period_range(frm, to, freq="M"):
        raw = _bhav_month(str(ym))
        if raw is not None and len(raw):
            days |= {d for d in pd.to_datetime(raw["DATE1"]).dt.date if frm <= d <= to}
    return days


def refresh_indices(frm: date, to: date, sessions: set | None = None) -> int:
    """Benchmarks into `index_prices`: Yahoo first, then NSE's daily index-close file for every stock
    session (`sessions`; else the bucket's bhavcopy days) Yahoo lacks — checked against the previous
    close before it is stored. A session still missing is printed; the freshness hole rule fails on it."""
    yahoo = _yahoo_closes(frm, to)
    rows = [{"index_symbol": s, "trade_date": d.isoformat(), "close": c}
            for s, closes in yahoo.items() for d, c in sorted(closes.items())]
    _insert_index_rows(rows)
    sessions = {d for d in (sessions if sessions is not None else _bucket_sessions(frm, to)) if frm <= d <= to}
    known = _known_closes(frm - timedelta(days=15), to)
    for s, closes in yahoo.items():
        known.setdefault(s, {}).update(closes)
    missing = {s: sorted(sessions - set(known.get(s, {}))) for s in BENCHMARKS}
    parsed = {}
    for d in sorted({d for days in missing.values() for d in days}):
        text = _index_file(d)
        parsed[d] = parse_index_closes(text) if text else None
    fallback, skipped = plan_fallback(missing, parsed, known, lookup=lambda day: _parsed_file(day, None))
    _insert_index_rows(fallback)
    for r in fallback:
        print(f"  {r['trade_date']} {r['index_symbol']}: {r['close']} from NSE ind_close_all (Yahoo had none)")
    for s, d, why in skipped:
        print(f"  WARN {d} {s}: no benchmark close ({why})")
    return len(rows) + len(fallback)


def run(frm: date, to: date, keep_days: int = KEEP_DAYS) -> None:
    import requests
    from scanner import db
    from scanner.bhavcopy import fetch_bhavcopy, parse_bhavcopy, parse_raw, to_month_frame

    today = date.today()
    s = requests.Session()
    days = [frm + timedelta(days=k) for k in range((to - frm).days + 1)]
    present, loaded = set(), 0
    for ym, ds in months_of(days).items():
        month, dirty = None, False
        for d in ds:
            text = fetch_bhavcopy(d, s)
            time.sleep(POLITE)
            if text is None:
                continue
            rows = parse_bhavcopy(text)           # raises on a truncated / malformed file
            if not file_is_for(rows, d):
                print(f"  {d}: holiday copy of {rows[0]['trade_date']} — skipped", flush=True)
                continue
            present.add(d)
            if in_table_window(d, today, keep_days):
                n = db.rpc("reload_daily_prices", {"p_date": d.isoformat(), "p_rows": rows})
                loaded += 1
                print(f"  {d}: {n} rows -> daily_prices", flush=True)
            if not dirty:
                month = _load_month(ym)
            month, dirty = to_month_frame(month, parse_raw(text)), True
        if dirty:
            _save_month(ym, month)
            print(f"  bucket bhav/{ym}.parquet: {month['DATE1'].nunique()} days", flush=True)
    cal = calendar_from_presence(days, present, today)
    for i in range(0, len(cal), 500):
        db.insert("trading_calendar", cal[i:i + 500], on_conflict="trade_date", return_rows=False,
                  ignore_duplicates=True)
    print(f"{len(present)} trading days fetched, {loaded} loaded into daily_prices; "
          f"{sum(not r['is_trading'] for r in cal)} past weekdays without a file")
    if frm >= today - timedelta(days=7) and not present:
        raise SystemExit(f"no bhavcopy for any day {frm}..{to} — NSE archive down or moved?")
    print(f"index_prices: {refresh_indices(frm, to, sessions=present)} benchmark rows")
    print(f"index_prices: {refresh_sectors(present)} sector index rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--from", dest="frm", type=date.fromisoformat)
    ap.add_argument("--to", type=date.fromisoformat)
    ap.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    ap.add_argument("--prune", action="store_true", help="only drop table rows older than --keep-days")
    ap.add_argument("--indices-only", action="store_true",
                    help="only refresh index_prices (Yahoo) for the window: no bhavcopy fetch, no bucket write")
    ap.add_argument("--sectors-only", action="store_true",
                    help="only load NSE sector indices for the window's bhavcopy sessions (backfill.yml what=sector-indices)")
    a = ap.parse_args()
    today = date.today()
    if a.prune:
        from scanner import db
        print(f"pruned {db.rpc('prune_daily_prices', {'p_keep_days': a.keep_days})} daily_prices rows "
              f"older than {a.keep_days} days (the bucket keeps them)")
        return
    if a.date:
        frm = to = a.date
    else:
        frm, to = a.frm or today - timedelta(days=5), a.to or today
    if a.indices_only:
        print(f"index_prices: {refresh_indices(frm, to)} benchmark rows {frm}..{to}")
        return
    if a.sectors_only:
        print(f"index_prices: {refresh_sectors(_bucket_sessions(frm, to))} sector index rows {frm}..{to}")
        return
    run(frm, to, a.keep_days)


if __name__ == "__main__":
    main()
