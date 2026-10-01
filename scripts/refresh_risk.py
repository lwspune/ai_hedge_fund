"""Daily risk lens (scanner/risk.py, docs/RISK_LENS_SPEC.md) -> `risk_metrics`, one row per listed symbol.

    python scripts/refresh_risk.py                 # whole listed universe, upsert (needs SUPABASE_SERVICE_KEY)
    python scripts/refresh_risk.py --symbols A,B   # write only these (ranks still over the whole run)
    python scripts/refresh_risk.py --print         # compute + print, no write (dev)

One pass over the 400-day window of raw bhavcopy months (`pricestore.bar_panel`), NIFTY 500 as
the benchmark. Fails the run (-> GitHub email) on a stale benchmark, fewer than MIN_ROWS rows,
more than MAX_UNVERIFIED of rows with blanked price metrics, or any row the DB rejects. Warns (does
not fail) when the benchmark misses trading sessions inside the window — a price-store hole turns a
multi-day move into one "day"; backfill it (backfill.yml what=prices).
"""
from __future__ import annotations

import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_ROWS = 1500              # ~2,400 listed symbols print in a normal window
MAX_UNVERIFIED = 0.20        # rows with blanked price metrics (action_unverified / price_break): more =
                             # the actions feed, the adjuster or the price store broke, not the market
BENCHMARK_MAX_AGE = 3        # trading days; a stale benchmark makes every beta wrong
BENCHMARK = "^CRSLDX"        # NIFTY 500, the benchmark every validation uses
PAGE = 500
UNTRUSTED = {"action_unverified", "price_break"}


def run_failures(rows: list[dict]) -> list[str]:
    """Why this run must not be trusted (empty = fine)."""
    out = []
    if len(rows) < MIN_ROWS:
        out.append(f"only {len(rows)} rows < {MIN_ROWS}")
    n_bad = sum(bool(UNTRUSTED & set(r.get("flags") or [])) for r in rows)
    if rows and n_bad / len(rows) > MAX_UNVERIFIED:
        out.append(f"{n_bad}/{len(rows)} rows action_unverified / price_break > {MAX_UNVERIFIED:.0%}")
    return out


def benchmark_stale(last: date | None, today: date, hol) -> bool:
    from scanner.trading_calendar import age_in_trading_days
    age = age_in_trading_days(last, today, hol)
    return age is None or age > BENCHMARK_MAX_AGE


def missing_sessions(have, start: date, end: date, hol) -> list[date]:
    """Trading days in [start, end] absent from `have` (the benchmark's dates) — holes in the store."""
    from scanner.trading_calendar import is_trading_day
    have = set(have)
    out, d = [], start
    while d <= end:
        if is_trading_day(d, hol) and d not in have:
            out.append(d)
        d += timedelta(days=1)
    return out


# --- thin I/O -------------------------------------------------------------------

def _load(start: date):
    from scanner import db
    companies = db.select_all("companies", {"select": "symbol,series", "status": "eq.listed"})
    actions = defaultdict(list)
    for a in db.select_all("corporate_events", {"select": "symbol,event_type,event_date,details",
                                                "event_type": "in.(split,bonus,consolidation,demerger)",
                                                "event_date": f"gte.{start}"}):
        actions[a["symbol"]].append(a)
    surv = defaultdict(set)
    last = db.select("surveillance_daily", {"select": "as_of", "order": "as_of.desc", "limit": "1"})
    if last:
        for r in db.select_all("surveillance_daily", {"select": "symbol,list_name",
                                                      "as_of": f"eq.{last[0]['as_of']}"}):
            surv[r["symbol"]].add(r["list_name"])
    return {c["symbol"]: c.get("series") for c in companies}, actions, surv


def main():
    from scanner import db
    from scanner.pricestore import bar_panel, get_closes
    from scanner.risk import WINDOW_DAYS, add_ranks, format_table, risk_row, symbol_metrics
    from scanner.sectors import N500, assign_indices, load_industries, load_sector_closes
    from scanner.trading_calendar import holidays

    args = sys.argv[1:]
    dry = "--print" in args
    only = None
    if "--symbols" in args:
        only = {s.strip().upper() for s in args[args.index("--symbols") + 1].split(",") if s.strip()}
    t0 = time.monotonic()
    today = date.today()
    start = today - timedelta(days=WINDOW_DAYS)

    mkt = get_closes(BENCHMARK, start, today, source="db")
    mkt_last = mkt.index.max().date() if mkt is not None else None
    hol = holidays()
    if benchmark_stale(mkt_last, today, hol):
        raise SystemExit(f"benchmark {BENCHMARK} stale: last close {mkt_last}")
    gap = missing_sessions({d.date() for d in mkt.index}, mkt.index.min().date(), mkt_last, hol)
    if gap:
        print(f"WARN: {len(gap)} trading sessions missing from the price store in the window "
              f"({gap[0]} .. {gap[-1]}): moves across them read as one session; backfill.yml what=prices")

    universe, actions, surv = _load(start)
    sec_closes = load_sector_closes(start, today)
    picks = assign_indices(load_industries(), {**sec_closes, N500: mkt}, start)
    panel = bar_panel(start, today)
    t_panel = time.monotonic() - t0

    def sector_of(sym):
        idx, fb = picks.get(sym, (None, False))
        if idx is None:
            return None
        return {"index": idx, "fallback": fb, "closes": mkt if idx == N500 else sec_closes.get(idx)}

    rows = [symbol_metrics(sym, panel[sym], mkt, actions.get(sym, []), universe[sym], surv.get(sym, set()),
                           sector=sector_of(sym))
            for sym in sorted(universe) if sym in panel]
    rows = [risk_row(m, today) for m in add_ranks(rows)]
    hist = Counter(f for r in rows for f in r["flags"])
    print(f"risk {today}: {len(rows)} symbols ({len(universe)} listed, {len(panel)} in panel) | "
          f"benchmark to {mkt_last} | panel {t_panel:.0f}s, total {time.monotonic() - t0:.0f}s")
    print("flags: " + (", ".join(f"{k} {v}" for k, v in hist.most_common()) or "none"))

    failures = run_failures(rows)
    out = [r for r in rows if only is None or r["symbol"] in only]
    if dry or only:
        print(format_table(out))
    if failures:
        raise SystemExit("FAILED: " + "; ".join(failures))
    if dry:
        return
    rejected = []
    for i in range(0, len(out), PAGE):
        _, bad = db.upsert_resilient("risk_metrics", out[i:i + PAGE], on_conflict="symbol")
        rejected += bad
    print(f"upserted {len(out) - len(rejected)} rows")
    if rejected:
        for r, err in rejected[:20]:
            print(f"  rejected {r['symbol']}: {err}")
        raise SystemExit(f"{len(rejected)} rows rejected by the database")


if __name__ == "__main__":
    main()
