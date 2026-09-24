"""Validate candidate signal: preferential-allotment lock-in expiry overhang.

Events: every `pref_lockin_expiry` row in corporate_events (NSE further-issues listing XBRL:
6-month non-promoter / 18-month promoter tranches; ICDR default 6m where the XBRL was
unreadable — those rows are reported separately and excluded from the headline). Prices:
unadjusted NSE closes from the cloud store (source="db", 2020->), benchmark NIFTY 500. Events
with a split/bonus/rights/consolidation/demerger inside the window are dropped.

Windows (pre-specified, T = first trading day on/after expiry): pre T-10->T-1, event T-1->T+2,
post T+2->T+10, full T-10->T+10, and the actionable LONG leg recovery T+2->T+20.
Controls: same-length placebo windows on the same stocks (T-20..T-17, T+15..T+18).
Segments (pre-specified): 6m vs 18m, tranche share of listed capital above/below median,
allottees in profit at T-1 (close vs offer price), era (two-year buckets), market-cap bucket as
of the event (pointintime).

    python scripts/validate_pref_lockin.py [--exclude-results-window N] [--publish]
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, run  # noqa: E402
from scanner import db  # noqa: E402
from scanner.eventstudy import summarize, window_return  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pointintime import mcap_bucket_at  # noqa: E402
from scanner.prefissues import study_events  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402

BENCH = "^CRSLDX"
COST = 0.003
WINDOWS = {"pre": (-10, -1), "event": (-1, 2), "post": (2, 10), "full": (-10, 10), "recovery": (2, 20)}
PLACEBO = {"placebo_pre": (-20, -17), "placebo_post": (15, 18)}
OUT = Path(__file__).resolve().parent.parent / "cache" / "pref_lockin_results.csv"


def fmt(label: str, xs) -> str:
    s = summarize(list(xs))
    if not s["n"]:
        return f"  {label:<40} n=   0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    return (f"  {label:<40} n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}")


def build() -> pd.DataFrame:
    rows = db.select_all("corporate_events", {"select": "symbol,event_type,event_date,details,source",
                                              "source": "eq.nse_pref"})
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": "gte.2022-06-01"})
    cutoff = (date.today() - timedelta(days=35)).isoformat()   # T+20 trading days of data
    events = [e for e in study_events(rows) if e["expiry"] <= cutoff]
    bench = get_closes(BENCH, "2022-01-01", source="db")
    print(f"{len(events)} lock-in expiries ({sum(e['default'] for e in events)} ICDR-default) on "
          f"{len({e['symbol'] for e in events})} symbols; blocking actions {len(acts)}", flush=True)
    span: dict[str, list[str]] = {}
    for e in events:
        span.setdefault(e["symbol"], []).append(e["expiry"])
    prices, out = {}, []
    for k, sym in enumerate(sorted(span), 1):
        lo = (pd.Timestamp(min(span[sym])) - pd.Timedelta(days=60)).date().isoformat()
        hi = (pd.Timestamp(max(span[sym])) + pd.Timedelta(days=45)).date().isoformat()
        try:
            prices[sym] = get_closes(sym, lo, hi, source="db")
        except Exception as ex:
            print(f"  {sym}: {ex!r}"[:100])
            prices[sym] = None
        if k % 100 == 0:
            print(f"  priced {k}/{len(span)}", flush=True)
    for e in events:
        s, exp = prices.get(e["symbol"]), pd.Timestamp(e["expiry"])
        row = {**e, "priced": s is not None and len(s) > 0,
               "blocked": blocking_action(acts, e["symbol"], exp - pd.Timedelta(days=35), exp + pd.Timedelta(days=35))}
        if row["priced"] and not row["blocked"]:
            for w, (a, b) in {**WINDOWS, **PLACEBO}.items():
                row[w] = window_return(s, bench, exp, a, b)
            pre = s[s.index < exp]
            row["px_vs_offer"] = (float(pre.iloc[-1]) / e["offer_price"] - 1) if len(pre) and e.get("offer_price") else None
            try:
                row["mcap_bucket"] = mcap_bucket_at(e["symbol"], exp.date())
            except Exception:
                row["mcap_bucket"] = None
        out.append(row)
    df = pd.DataFrame(out)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    usable = df[df["priced"] & ~df["blocked"] & df["full"].notna()]
    ok = usable[~usable["default"]]
    print(f"\nevents {len(df)} | unpriced {int((~df['priced']).sum())} | blocked "
          f"{int((df['priced'] & df['blocked']).sum())} | usable {len(usable)} (XBRL-dated {len(ok)})")
    print("\n=== LONG-side abnormal return vs NIFTY 500 (XBRL-dated tranches) ===")
    for m in (6, 18):
        sub = ok[ok["months"] == m]
        print(f"-- {m}-month lock-in --")
        for w, (a, b) in WINDOWS.items():
            print(fmt(f"{w:<9} T{a:+d}->T{b:+d}", sub[w].dropna()))
    print("\n=== CONTROL: event window vs same-length placebo windows (same stocks) ===")
    for m in (6, 18):
        sub = ok[ok["months"] == m]
        for w in ("event", "placebo_pre", "placebo_post"):
            print(fmt(f"{m}m {w}", sub[w].dropna()))
    print("\n=== ICDR-default rows (no readable tranche; 6m assumed) — event window ===")
    print(fmt("default 6m event", usable.loc[usable["default"], "event"].dropna()))
    print("\n=== REGIME: event window by era ===")
    for m in (6, 18):
        for era in sorted(ok["era"].dropna().unique()):
            print(fmt(f"{m}m {era}", ok.loc[(ok["months"] == m) & (ok["era"] == era), "event"].dropna()))
    print("\n=== SEGMENTS (pre-specified) — event T-1->T+2 | recovery T+2->T+20 ===")
    med = ok["share_of_listed"].median()
    cuts = {f"tranche share > median ({med:.3f})": ok["share_of_listed"] > med,
            "tranche share <= median": ok["share_of_listed"] <= med,
            "allottees in profit (px>offer)": ok["px_vs_offer"] > 0,
            "allottees under water (px<=offer)": ok["px_vs_offer"] <= 0}
    for b in sorted(ok["mcap_bucket"].dropna().unique()):
        cuts[f"mcap={b}"] = ok["mcap_bucket"] == b
    for m in (6, 18):
        for label, mask in cuts.items():
            sub = ok[mask & (ok["months"] == m)]
            print(fmt(f"{m}m {label} [event]", sub["event"].dropna()))
            print(fmt(f"{m}m {label} [recovery]", sub["recovery"].dropna()))
    print(f"\nShort side (not available to retail) = -(event mean) - {COST*100:.1f}%; the long "
          f"recovery leg is what a retail buyer could act on, net of ~{COST*100:.1f}%.")


def _study(args) -> dict:
    df = exclude_results(build(), "expiry", args.exclude_results_window)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("pref_lockin", _study)
