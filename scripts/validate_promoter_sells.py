"""Validate the pre-registered leg from CONCLUSIONS §10: promoter open-market SELLING
(SAST Reg 29 disclosures, 2020->) as a negative-drift signal for a holder (exit / avoid).

Hypothesis (registered 2026-09-24 before this run): after a promoter open-market sale cluster,
the stock underperforms NIFTY 500 over +20 / +60 trading days, in the 2024-26 era as well as
pooled. Entry = first trading day after the disclosure. Contrast legs: non-promoter open-market
sales and promoter buys. Control: same-stock placebo windows away from the disclosure.
Segments: stake sold > / <= median, clusters, board, era. Prices: unadjusted NSE closes; events
with a share-count-changing action nearby dropped.

    python scripts/validate_promoter_sells.py [--limit N] [--exclude-results-window N] [--publish]
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, run  # noqa: E402
from scanner import db  # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize, window_return  # noqa: E402
from scanner.insider import disclosure_events, parse_reg29  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402
from scripts.validate_promoter_buys import SME_SERIES, fmt, load_raw  # noqa: E402

BENCH = "^CRSLDX"
HORIZONS = (5, 20, 60)
COST = 0.003
PLACEBO = {"placebo_pre": (-40, -20), "placebo_post": (70, 90)}   # 20-day windows away from T0
OUT = Path(__file__).resolve().parent.parent / "cache" / "promoter_sells_results.csv"


def build(limit: int | None = None) -> pd.DataFrame:
    rows = parse_reg29(load_raw())
    cutoff = (date.today() - timedelta(days=130)).isoformat()   # room for the +90d placebo
    legs = {"promoter_sell": disclosure_events(rows, "SELL", True),
            "nonpromoter_sell": disclosure_events(rows, "SELL", False),
            "promoter_buy": disclosure_events(rows, "BUY", True)}
    legs = {k: [e for e in v if e["date"] <= cutoff][: limit or None] for k, v in legs.items()}
    print({k: len(v) for k, v in legs.items()}, "events", flush=True)
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": "gte.2019-11-01"})
    series = {c["symbol"]: c["series"] for c in db.select_all("companies", {"select": "symbol,series"})}
    bench = get_closes(BENCH, "2019-01-01", source="yf")
    span: dict[str, list[str]] = {}
    for evs in legs.values():
        for e in evs:
            span.setdefault(e["symbol"], []).append(e["date"])
    prices, out = {}, []
    for k, sym in enumerate(sorted(span), 1):
        lo = (pd.Timestamp(min(span[sym])) - pd.Timedelta(days=75)).date()
        hi = (pd.Timestamp(max(span[sym])) + pd.Timedelta(days=140)).date()
        try:
            prices[sym] = get_closes(sym, lo, hi, source="nse")
        except Exception:
            prices[sym] = None
        if k % 100 == 0:
            print(f"  priced {k}/{len(span)} symbols", flush=True)
    for leg, evs in legs.items():
        for e in evs:
            s, t0 = prices.get(e["symbol"]), pd.Timestamp(e["date"])
            row = {**e, "leg": leg, "board": "sme" if series.get(e["symbol"]) in SME_SERIES else "main",
                   "priced": s is not None,
                   "blocked": blocking_action(acts, e["symbol"], t0 - pd.Timedelta(days=60), t0 + pd.Timedelta(days=140))}
            if s is not None and not row["blocked"]:
                row["pre"] = window_return(s, bench, t0, -20, 0)
                for h in HORIZONS:
                    row[f"h{h}"] = forward_abnormal_return(s, bench, t0, h, entry_lag=1)
                for w, (a, b) in PLACEBO.items():
                    row[w] = window_return(s, bench, t0, a, b)
            out.append(row)
    df = pd.DataFrame(out)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    ok = df[df["priced"] & ~df["blocked"] & df["h20"].notna()]
    print(f"\nevents {len(df)} | usable {len(ok)} | unpriced {int((~df['priced']).sum())} | "
          f"blocked {int((df['priced'] & df['blocked']).sum())}")
    for leg in ("promoter_sell", "nonpromoter_sell", "promoter_buy"):
        sub = ok[ok["leg"] == leg]
        print(f"\n=== {leg} (abnormal vs NIFTY 500; entry = day after disclosure) ===")
        print(fmt("pre-disclosure T-20 -> T0", sub["pre"].dropna()))
        for h in HORIZONS:
            print(fmt(f"follower +{h}d", sub[f"h{h}"].dropna()))
        for w in PLACEBO:
            print(fmt(f"{w} (20d, same stocks)", sub[w].dropna()))
    ps = ok[ok["leg"] == "promoter_sell"]
    med = ps["pct"].median()
    yr = pd.to_datetime(ps["date"]).dt.year
    print("\n=== promoter_sell SEGMENTS (pre-specified) — +20d | +60d ===")
    cuts = {f"stake sold > median ({med:.2f}%)": ps["pct"] > med, "stake sold <= median": ps["pct"] <= med,
            "cluster (2+ disclosures)": ps["n"] >= 2, "single disclosure": ps["n"] == 1,
            "board = mainboard": ps["board"] == "main", "board = SME": ps["board"] == "sme",
            "era 2020-21": yr.between(2020, 2021), "era 2022-23": yr.between(2022, 2023),
            "era 2024-26": yr.between(2024, 2026)}
    for label, m in cuts.items():
        print(fmt(f"{label} [+20d]", ps.loc[m, "h20"].dropna()))
        print(fmt(f"{label} [+60d]", ps.loc[m, "h60"].dropna()))
    print(f"\nA holder's exit saves -(mean) minus ~{COST*100:.1f}% costs; not shortable for retail.")


def _study(args) -> dict:
    import argparse
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--limit", type=int)
    extra, _ = ap.parse_known_args()
    df = exclude_results(build(extra.limit), "date", args.exclude_results_window)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("promoter_sells", _study)
