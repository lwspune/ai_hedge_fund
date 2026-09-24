"""Load NSE daily bhavcopies into the cloud price store (DATA_INFRA_SPEC WP3).

    python scripts/refresh_prices.py                          # last 5 calendar days (heals a missed run)
    python scripts/refresh_prices.py --date 2026-09-23
    python scripts/refresh_prices.py --from 2024-01-01 --to 2024-12-31   # backfill (backfill.yml)
    python scripts/refresh_prices.py --prune                  # weekly: drop table rows > 730 days

Per trading day: fetch sec_bhavdata_full -> parse (guarded) -> `reload_daily_prices` RPC (only
for dates inside the table's retention window, so a backfill never bloats Postgres) -> merged
into that month's raw parquet in the private `prices` bucket (bhav/YYYY-MM.parquet: every
series and column, the durable history). Past weekdays with no file are recorded as holidays
in `trading_calendar` (source nse_bhavcopy) — historical trading days for validations. Also
refreshes `index_prices` (Yahoo benchmarks) for the same window.
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

KEEP_DAYS = 730                       # daily_prices retention; older rows live in the bucket only
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


def refresh_indices(frm: date, to: date) -> int:
    import yfinance as yf
    from scanner import db
    rows = []
    for sym in BENCHMARKS:
        h = yf.Ticker(sym).history(start=frm.isoformat(), end=(to + timedelta(days=1)).isoformat(),
                                   interval="1d", auto_adjust=False)
        if h is None or h.empty:
            raise SystemExit(f"yfinance returned nothing for {sym} {frm}..{to}")
        rows += [{"index_symbol": sym, "trade_date": pd.Timestamp(i).date().isoformat(), "close": float(c)}
                 for i, c in h["Close"].dropna().items() if c > 0]
    for i in range(0, len(rows), 1000):
        db.insert("index_prices", rows[i:i + 1000], on_conflict="index_symbol,trade_date", return_rows=False)
    return len(rows)


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
    print(f"index_prices: {refresh_indices(frm, to)} benchmark rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--from", dest="frm", type=date.fromisoformat)
    ap.add_argument("--to", type=date.fromisoformat)
    ap.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    ap.add_argument("--prune", action="store_true", help="only drop table rows older than --keep-days")
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
    run(frm, to, a.keep_days)


if __name__ == "__main__":
    main()
