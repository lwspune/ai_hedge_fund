"""Market regime (scanner/regime.py, docs/REGIME_VIEW_SPEC.md) -> `market_regime`, one row per trading day.

    python scripts/refresh_regime.py                    # daily: recompute the last RECOMPUTE_SESSIONS sessions, upsert
    python scripts/refresh_regime.py --from 2020-01-01  # rebuild from a date (backfill.yml what=regime), upsert
    python scripts/refresh_regime.py --print [--from D] # compute + print the last 20 rows, no write

Breadth reads a panel reaching LOOKBACK_DAYS before the first date written (every metric looks back
at most 250 prints); the index block always reads NIFTY 500 / NIFTY 50 from 2020, since the running high
and the volatility percentile need the full history. Fails the run (-> GitHub email) when the last date
isn't the benchmark's, the universe is thin, breaks exclude too many stocks, breadth is blank, or the DB
rejects a row.
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_UNIVERSE = 800           # ~1,400 liquid mainboard names today: fires only on a broken panel
MAX_EXCLUDED = 0.10          # share of the would-be universe kept out by breaks on the last date
PAGE = 500


def run_failures(rows: list[dict], bench_last: date | None) -> list[str]:
    """Why this run must not be trusted (empty = fine). Judged on the last date written."""
    if not rows:
        return ["no rows computed"]
    last, out = rows[-1], []
    if bench_last is None or last["trade_date"] != bench_last.isoformat():
        out.append(f"last date {last['trade_date']} is not the benchmark's last close ({bench_last})")
    u, x = last.get("n_universe") or 0, last.get("n_excluded") or 0
    if u < MIN_UNIVERSE:
        out.append(f"universe {u} < {MIN_UNIVERSE} on {last['trade_date']}")
    if u + x and x / (u + x) > MAX_EXCLUDED:
        out.append(f"{x}/{u + x} excluded by breaks > {MAX_EXCLUDED:.0%}")
    if last.get("pct_above_200") is None:
        out.append(f"pct_above_200 blank on {last['trade_date']}")
    return out


def _actions() -> dict[str, list[dict]]:
    from scanner import db
    out = defaultdict(list)
    for a in db.select_all("corporate_events", {"select": "symbol,event_type,event_date,details",
                                                "event_type": "in.(split,bonus,consolidation,demerger)"}):
        out[a["symbol"]].append(a)
    return out


def _peak_mb() -> str:
    try:
        import resource
        return f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB"   # KB on Linux
    except ImportError:
        return "n/a"


def main():
    import pandas as pd
    from scanner import db
    from scanner.pricestore import bar_panel, get_closes
    from scanner.regime import (LOOKBACK_DAYS, RECOMPUTE_SESSIONS, START, breadth, format_table,
                                index_metrics, regime_rows, stock_states)

    args = sys.argv[1:]
    dry = "--print" in args
    frm = date.fromisoformat(args[args.index("--from") + 1]) if "--from" in args else None
    t0 = time.monotonic()
    today = date.today()

    n500 = get_closes("^CRSLDX", START, today, source="db")
    n50 = get_closes("^NSEI", START, today, source="db")
    bench_last = n500.index.max().date() if n500 is not None else None
    if n500 is None:
        raise SystemExit("no NIFTY 500 closes in index_prices")

    panel_start = max(START, (frm or today) - timedelta(days=LOOKBACK_DAYS))
    panel = bar_panel(panel_start, today)
    t_panel = time.monotonic() - t0
    sessions = pd.DatetimeIndex(sorted({d for bars in panel.values() for d in bars.index}))
    since = frm if frm else sessions[-RECOMPUTE_SESSIONS].date()
    actions = _actions()
    states = {sym: stock_states(bars, actions.get(sym, []), sessions) for sym, bars in panel.items()}
    rows = regime_rows(index_metrics(n500, n50), breadth(states), since=since)
    print(f"regime {today}: {len(rows)} rows from {since} | panel {panel_start}.. {len(panel)} symbols, "
          f"{len(sessions)} sessions | benchmark to {bench_last} | panel {t_panel:.0f}s, "
          f"total {time.monotonic() - t0:.0f}s, peak {_peak_mb()}")
    print(format_table(rows[-20:]))

    failures = run_failures(rows, bench_last)
    if failures:
        raise SystemExit("FAILED: " + "; ".join(failures))
    if dry:
        return
    rejected = []
    for i in range(0, len(rows), PAGE):
        _, bad = db.upsert_resilient("market_regime", rows[i:i + PAGE], on_conflict="trade_date")
        rejected += bad
    print(f"upserted {len(rows) - len(rejected)} rows")
    if rejected:
        for r, err in rejected[:20]:
            print(f"  rejected {r['trade_date']}: {err}")
        raise SystemExit(f"{len(rejected)} rows rejected by the database")


if __name__ == "__main__":
    main()
