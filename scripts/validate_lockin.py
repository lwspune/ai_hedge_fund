"""Validate candidate signal #2: anchor lock-in expiry overhang.

Events: every anchor lock-in expiry (30d = first 50% unlock; 90d = the rest, post-Apr-2022)
in the `ipos` table. Prices: unadjusted NSE closes (EQ + SME series) via the price store;
benchmark NIFTY 500. Events with a split/bonus/rights/consolidation/demerger inside the
window are dropped. Returns are benchmark-adjusted; the SHORT side is the negation.

Windows (pre-specified, T = first trading day on/after expiry): pre T-10->T-1,
event T-1->T+2, post T+2->T+10, full T-10->T+10.
Segments (pre-specified): 30d vs 90d, board, era (listing before/after 1-Apr-2022),
anchors in profit at T-1 (price vs issue), anchor share of the issue (above/below median).

    python scripts/validate_lockin.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, parse_args  # noqa: E402
from scanner import db  # noqa: E402
from scanner.eventstudy import summarize  # noqa: E402
from scanner.lockin import BLOCKING, WINDOWS, blocking_action, lockin_events, window_return  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402

BENCH = "^CRSLDX"            # NIFTY 500
COST = 0.003                 # ~30 bps round trip
# Control: same-length (3-day) windows on the SAME stocks away from the unlock. New IPOs
# drift down vs the index anyway; the event window must beat this baseline, not zero.
PLACEBO = {"placebo_pre": (-20, -17), "placebo_post": (15, 18)}
OUT = Path(__file__).resolve().parent.parent / "cache" / "lockin_results.csv"


def fmt(label: str, xs) -> str:
    s = summarize(list(xs))
    if not s["n"]:
        return f"  {label:<34} n=  0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    return (f"  {label:<34} n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}")


def build() -> pd.DataFrame:
    ipos = db.select_all("ipos", {"select": "symbol,board,listing_date,issue_price,anchor_shares,"
                                            "shares_allotted,anchor_lockin_30,anchor_lockin_90"})
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})"})
    cutoff = (date.today() - timedelta(days=21)).isoformat()   # need T+10 trading days of data
    events = [e for e in lockin_events(ipos) if e["expiry"] <= cutoff]
    bench = get_closes(BENCH, "2005-01-01", source="yf")
    print(f"blocking corporate actions loaded: {len(acts)}")
    print(f"{len(events)} lock-in expiries from {len(ipos)} IPOs; pricing "
          f"{len({e['symbol'] for e in events})} symbols (unadjusted NSE)...", flush=True)

    last_exp = {}
    for e in events:  # fetch each symbol only through its last expiry (+ room for T+10)
        last_exp[e["symbol"]] = max(last_exp.get(e["symbol"], e["expiry"]), e["expiry"])
    prices, rows = {}, []
    for k, e in enumerate(events, 1):
        sym = e["symbol"]
        if sym not in prices:
            try:
                end = (pd.Timestamp(last_exp[sym]) + pd.Timedelta(days=45)).date().isoformat()
                prices[sym] = get_closes(sym, e["listing_date"], end, source="nse")
            except Exception as ex:  # nselib throws on unknown / renamed symbols
                print(f"  {sym}: {ex!r}"[:100])
                prices[sym] = None
        s = prices[sym]
        exp = pd.Timestamp(e["expiry"])
        row = {**e, "priced": s is not None and len(s) > 0,
               "blocked": blocking_action(acts, sym, e["listing_date"], exp + pd.Timedelta(days=21))}
        if row["priced"] and not row["blocked"]:
            for w, (a, b) in {**WINDOWS, **PLACEBO}.items():
                row[w] = window_return(s, bench, exp, a, b)
            pre = s[s.index < exp]
            row["px_vs_issue"] = (float(pre.iloc[-1]) / e["issue_price"] - 1) if len(pre) else None
        rows.append(row)
        if k % 100 == 0:
            print(f"  {k}/{len(events)}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    ok = df[df["priced"] & ~df["blocked"] & df["full"].notna()]
    print(f"\nevents: {len(df)} | unpriced {int((~df['priced']).sum())} | "
          f"dropped for corporate actions {int((df['priced'] & df['blocked']).sum())} | usable {len(ok)}")
    print("\n=== LONG-side abnormal return vs NIFTY 500 (a short earns the negative) ===")
    for kind in ("30d", "90d"):
        sub = ok[ok["kind"] == kind]
        print(f"-- {kind} expiry --")
        for w, (a, b) in WINDOWS.items():
            print(fmt(f"{w:<6} T{a:+d}->T{b:+d}", sub[w].dropna()))

    print("\n=== CONTROL: event window vs same-length placebo windows (same stocks) ===")
    for kind in ("30d", "90d"):
        sub = ok[ok["kind"] == kind]
        for w in ("event", "placebo_pre", "placebo_post"):
            print(fmt(f"{kind} {w}", sub[w].dropna()))
    print("\n=== REGIME: event window by expiry year ===")
    yr = pd.to_datetime(ok["expiry"]).dt.year
    for kind in ("30d", "90d"):
        for lo, hi in ((2006, 2021), (2022, 2023), (2024, 2026)):
            sub = ok[(ok["kind"] == kind) & yr.between(lo, hi)]
            print(fmt(f"{kind} {lo}-{hi}", sub["event"].dropna()))

    print("\n=== SEGMENTS (pre-specified) — event window T-1->T+2 | full T-10->T+10 ===")
    cuts = {
        "board=mainboard": ok["board"] == "mainboard",
        "board=sme": ok["board"] == "sme",
        "era=pre_apr2022": ok["era"] == "pre_apr2022",
        "era=post_apr2022": ok["era"] == "post_apr2022",
        "anchors in profit (px>issue)": ok["px_vs_issue"] > 0,
        "anchors under water (px<=issue)": ok["px_vs_issue"] <= 0,
    }
    med = ok["anchor_frac"].median()
    cuts[f"anchor share > median ({med:.2f})"] = ok["anchor_frac"] > med
    cuts[f"anchor share <= median"] = ok["anchor_frac"] <= med
    for kind in ("30d", "90d"):
        for label, m in cuts.items():
            sub = ok[m & (ok["kind"] == kind)]
            print(fmt(f"{kind} {label} [event]", sub["event"].dropna()))
            print(fmt(f"{kind} {label} [full]", sub["full"].dropna()))

    print(f"\nShort-side net of ~{COST*100:.1f}% costs = -(long mean) - {COST*100:.1f}%.")


if __name__ == "__main__":
    args = parse_args()
    report(exclude_results(build(), "expiry", args.exclude_results_window))
