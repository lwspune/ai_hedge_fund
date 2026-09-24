"""Validate candidate signal #10: the demerger listing flow.

Events: every newly listed demerged child in data/demerger_listings.csv (curated; see
scanner/demerger.py). T = the child's first trading day. Prices: unadjusted NSE closes from the
cloud store (nselib for listings before Feb-2020), benchmark NIFTY 500. A child with a
split/bonus/rights inside its first 45 days is dropped.

Measured (fixed in advance), abnormal vs NIFTY 500 on the CHILD:
  sell     T+0 -> T+5    the forced-selling window (inside the 10-session trade-for-trade period)
  recovery T+5 -> T+20   what a buyer entering after the selling captures
  late     T+10 -> T+30  same, entering after the trade-for-trade period ends
  full     T+0 -> T+30
CONTROL: same-length placebo windows on the same child (T+60..65, T+120..125). Also the
PARENT's cum -> ex move on the record date (last cum close -> ex close), for the ratio check.
Statistics: iid t and a cluster-robust t by scheme (children of one demerger share every date)
and by listing week. Segments (pre-specified): parent in NIFTY 50 / Next 50 vs not (curated),
parent market-cap bucket as of the ex-date (pointintime), era, child day-1 turnover tercile.

    python scripts/validate_demerger.py [--exclude-results-window N] [--publish]
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, run  # noqa: E402
from scanner import db  # noqa: E402
from scanner.demerger import PLACEBO, WINDOWS, load_listings, study_events, window_return  # noqa: E402
from scanner.eventstudy import summarize  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pointintime import mcap_bucket_at  # noqa: E402
from scanner.pricestore import get_bars, get_closes  # noqa: E402

BENCH = "^CRSLDX"
COST = 0.003
DB_FROM = pd.Timestamp("2020-02-01")
PATH_DAYS = 10
OUT = Path(__file__).resolve().parent.parent / "cache" / "demerger_results.csv"


def fmt(label: str, xs, clusters=None) -> str:
    s = summarize(list(xs), clusters=None if clusters is None else list(clusters))
    if not s["n"]:
        return f"  {label:<40} n=  0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    tc = f"  t_cl={s['t_cluster']:+5.1f} ({s['n_clusters']})" if s.get("t_cluster") is not None else ""
    return (f"  {label:<40} n={s['n']:>3}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}{tc}")


def closes_for(sym: str, start, end) -> pd.Series | None:
    src = "db" if pd.Timestamp(start) >= DB_FROM else "nse"
    try:
        return get_closes(sym, start, end, source=src)
    except Exception as ex:  # nselib raises on unknown symbols
        print(f"  {sym}: {ex!r}"[:100])
        return None


def build() -> pd.DataFrame:
    companies = {c["symbol"]: c for c in db.select_all("companies", {"select": "symbol,status"})}
    events = study_events(load_listings(), companies, today=date.today())
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": "gte.2019-01-01"})
    bench = get_closes(BENCH, "2018-06-01", source="yf")
    print(f"{len(events)} listed children from {len({e['scheme'] for e in events})} demergers", flush=True)
    rows = []
    for k, e in enumerate(events, 1):
        lst = pd.Timestamp(e["listing_date"])
        s = closes_for(e["child"], lst - pd.Timedelta(days=3), lst + pd.Timedelta(days=200))
        row = {**e, "priced": s is not None and len(s) > 0,
               "blocked": blocking_action(acts, e["child"], lst, lst + pd.Timedelta(days=45))}
        if row["priced"]:
            row["first_close_date"] = s.index.min().date().isoformat()
            row["listed_as_curated"] = abs((s.index.min() - lst).days) <= 3
        if row["priced"] and not row["blocked"]:
            for w, (a, b) in {**WINDOWS, **PLACEBO}.items():
                row[w] = window_return(s, bench, lst, a, b)
            path = s.sort_index().iloc[:PATH_DAYS + 1]
            for i in range(1, min(PATH_DAYS, len(path) - 1) + 1):
                row[f"d{i}"] = float(path.iloc[i] / path.iloc[0] - 1)
            try:
                bars = get_bars(e["child"], lst, lst + pd.Timedelta(days=10))
                row["day1_turnover_lakh"] = float(bars["turnover_lakh"].iloc[0]) if bars is not None and len(bars) else None
            except Exception:
                row["day1_turnover_lakh"] = None
        # the parent's cum -> ex move on the record date (sanity check on the scheme ratio)
        ex = pd.Timestamp(e["ex_date"])
        p = closes_for(e["parent"], ex - pd.Timedelta(days=15), ex + pd.Timedelta(days=10))
        row["parent_ex_move"] = window_return(p, bench, ex, -1, 0) if p is not None else None
        try:
            row["parent_mcap"] = mcap_bucket_at(e["parent"], ex.date())
        except Exception:
            row["parent_mcap"] = None
        rows.append(row)
        if k % 10 == 0:
            print(f"  {k}/{len(events)}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    ok = df[df["priced"] & ~df["blocked"] & df["full"].notna()].copy()
    wk = pd.to_datetime(ok["listing_date"]).dt.to_period("W").astype(str)
    print(f"\nchildren: {len(df)} | unpriced {int((~df['priced']).sum())} | blocked "
          f"{int((df['priced'] & df['blocked']).sum())} | usable {len(ok)} | "
          f"listing date matches the store {int(ok['listed_as_curated'].sum())}/{len(ok)}")
    print("\n=== CHILD abnormal return vs NIFTY 500 (T = first close); t_cl by scheme ===")
    for w, (a, b) in WINDOWS.items():
        sub = ok[ok[w].notna()]
        print(fmt(f"{w:<9} T{a:+d}->T{b:+d}", sub[w], clusters=sub["scheme"]))
    print(fmt("sell (t_cl by listing week)", ok["sell"].dropna(), clusters=wk[ok["sell"].notna()]))
    print("\n=== CONTROL: sell window vs same-length placebo windows (same children) ===")
    for w in ("sell", "placebo_a", "placebo_b"):
        print(fmt(w, ok[w].dropna()))
    print(fmt("PARENT cum->ex move on the record date", ok["parent_ex_move"].dropna()))

    print(f"\n=== PATH: median child close vs its first close, sessions 1..{PATH_DAYS} (raw, not benchmark-adjusted) ===")
    cols = [f"d{i}" for i in range(1, PATH_DAYS + 1) if f"d{i}" in ok]
    med = ok[cols].median() * 100
    mean = ok[cols].mean() * 100
    print("  session : " + " ".join(f"{c[1:]:>6}" for c in cols))
    print("  median% : " + " ".join(f"{v:+6.1f}" for v in med.values))
    print("  mean%   : " + " ".join(f"{v:+6.1f}" for v in mean.values))
    print("  n       : " + " ".join(f"{int(ok[c].notna().sum()):>6}" for c in cols))

    print("\n=== SEGMENTS (pre-specified): sell | recovery | late ===")
    idx = ok["parent_index"].isin(["nifty50", "next50"])
    yr_cuts = {"parent in NIFTY 50 / Next 50": idx, "parent not in either": ~idx}
    for b in ("large", "mid", "small_mid", "small"):
        yr_cuts[f"parent mcap={b}"] = ok["parent_mcap"] == b
    for era in ("2019-21", "2022-23", "2024-26"):
        yr_cuts[f"era {era}"] = ok["era"] == era
    turn = ok["day1_turnover_lakh"]
    if turn.notna().sum() >= 9:
        lo, hi = turn.quantile(1 / 3), turn.quantile(2 / 3)
        yr_cuts["day-1 turnover LOW"] = turn <= lo
        yr_cuts["day-1 turnover MID"] = (turn > lo) & (turn <= hi)
        yr_cuts["day-1 turnover HIGH"] = turn > hi
    for label, m in yr_cuts.items():
        for w in ("sell", "recovery", "late"):
            print(fmt(f"{label} [{w}]", ok.loc[m, w].dropna()))

    print("\n=== per child ===")
    show = ok[["child", "parent", "listing_date", "parent_index", "parent_mcap", "sell", "recovery", "late", "full"]].copy()
    for c in ("sell", "recovery", "late", "full"):
        show[c] = (show[c] * 100).round(1)
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(show.sort_values("listing_date").to_string(index=False))
    print(f"\nA buyer entering after the sell window nets the recovery/late mean minus ~{COST*100:.1f}%; "
          "the child trades trade-for-trade with a 5% band for its first 10 sessions.")


def _study(args) -> dict:
    df = exclude_results(build(), "listing_date", args.exclude_results_window)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("demerger_listing", _study)
