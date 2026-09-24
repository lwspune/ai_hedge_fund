"""Validate candidate signal #7: follow promoter open-market buying (SAST Reg 29 disclosures).

Events: promoter open-market ACQUISITIONS of equity, clustered per symbol (10-day gap), dated at
the first disclosure. Entry = first trading day AFTER disclosure (what a follower can do).
Measured (fixed in advance): abnormal return vs NIFTY 500 over +5 / +20 / +60 trading days from
entry, and the pre-disclosure run-up T-20 -> T0. Contrast legs: promoter open-market SALES and
non-promoter open-market buys. Segments: stake > / <= median, clusters (2+ disclosures), board
(mainboard vs SME — not market cap: today's mcap would leak the future), era.
Prices: unadjusted NSE closes; split/bonus/rights/consolidation/demerger near an event -> dropped.

    python scripts/validate_promoter_buys.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, run  # noqa: E402
from scanner import db  # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize, window_return  # noqa: E402
from scanner.insider import disclosure_events, fetch_reg29, parse_reg29  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402

BENCH = "^CRSLDX"
HORIZONS = (5, 20, 60)
COST = 0.003
START = date(2020, 1, 1)
CACHE = Path(__file__).resolve().parent.parent / "cache" / "reg29"
OUT = Path(__file__).resolve().parent.parent / "cache" / "promoter_buys_results.csv"
SME_SERIES = {"SM", "ST", "SZ"}


def load_raw() -> list[dict]:
    """Year files cached locally; the current year is always refetched."""
    import requests
    CACHE.mkdir(parents=True, exist_ok=True)
    s, raw, today = requests.Session(), [], date.today()
    for y in range(START.year, today.year + 1):
        fp = CACHE / f"{y}.json"
        if fp.exists() and y < today.year:
            raw += json.loads(fp.read_text(encoding="utf-8"))
            continue
        rows = fetch_reg29(date(y, 1, 1), min(date(y, 12, 31), today), s)
        fp.write_text(json.dumps(rows), encoding="utf-8")
        raw += rows
    return raw


def fmt(label: str, xs) -> str:
    s = summarize(list(xs))
    if not s["n"]:
        return f"  {label:<44} n=   0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    return (f"  {label:<44} n={s['n']:>5}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}")


def build() -> pd.DataFrame:
    rows = parse_reg29(load_raw())
    cutoff = (date.today() - timedelta(days=100)).isoformat()   # room for the +60d horizon
    legs = {
        "promoter_buy": disclosure_events(rows, "BUY", True),
        "promoter_sell": disclosure_events(rows, "SELL", True),
        "nonpromoter_buy": disclosure_events(rows, "BUY", False),
    }
    legs = {k: [e for e in v if e["date"] <= cutoff] for k, v in legs.items()}
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
        lo = (pd.Timestamp(min(span[sym])) - pd.Timedelta(days=45)).date()
        hi = (pd.Timestamp(max(span[sym])) + pd.Timedelta(days=100)).date()
        try:
            prices[sym] = get_closes(sym, lo, hi, source="nse")
        except Exception:  # nselib raises on renamed / unknown symbols
            prices[sym] = None
        if k % 100 == 0:
            print(f"  priced {k}/{len(span)} symbols", flush=True)
    for leg, evs in legs.items():
        for e in evs:
            s, t0 = prices.get(e["symbol"]), pd.Timestamp(e["date"])
            row = {**e, "leg": leg, "board": "sme" if series.get(e["symbol"]) in SME_SERIES else "main",
                   "priced": s is not None,
                   "blocked": blocking_action(acts, e["symbol"], t0 - pd.Timedelta(days=30),
                                              t0 + pd.Timedelta(days=100))}
            if s is not None and not row["blocked"]:
                row["pre"] = window_return(s, bench, t0, -20, 0)
                for h in HORIZONS:
                    row[f"h{h}"] = forward_abnormal_return(s, bench, t0, h, entry_lag=1)
            out.append(row)
    df = pd.DataFrame(out)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    ok = df[df["priced"] & ~df["blocked"] & df["h20"].notna()]
    print(f"\nevents {len(df)} | usable {len(ok)} | unpriced {int((~df['priced']).sum())} | "
          f"blocked {int((df['priced'] & df['blocked']).sum())}")
    for leg in ("promoter_buy", "promoter_sell", "nonpromoter_buy"):
        sub = ok[ok["leg"] == leg]
        print(f"\n=== {leg} (abnormal vs NIFTY 500; entry = day after disclosure) ===")
        print(fmt("pre-disclosure run-up T-20 -> T0", sub["pre"].dropna()))
        for h in HORIZONS:
            print(fmt(f"follower +{h}d", sub[f"h{h}"].dropna()))

    pb = ok[ok["leg"] == "promoter_buy"]
    med = pb["pct"].median()
    yr = pd.to_datetime(pb["date"]).dt.year
    print(f"\n=== promoter_buy SEGMENTS (pre-specified) — +20d | +60d ===")
    cuts = {f"stake > median ({med:.2f}%)": pb["pct"] > med, "stake <= median": pb["pct"] <= med,
            "cluster (2+ disclosures)": pb["n"] >= 2, "single disclosure": pb["n"] == 1,
            "board = mainboard": pb["board"] == "main", "board = SME": pb["board"] == "sme",
            "era 2020-21": yr.between(2020, 2021), "era 2022-23": yr.between(2022, 2023),
            "era 2024-26": yr.between(2024, 2026)}
    for label, m in cuts.items():
        print(fmt(f"{label} [+20d]", pb.loc[m, "h20"].dropna()))
        print(fmt(f"{label} [+60d]", pb.loc[m, "h60"].dropna()))
    print(f"\nNet of costs: subtract ~{COST*100:.1f}% (more for small caps / SME spreads).")


def _study(args) -> dict:
    df = exclude_results(build(), "date", args.exclude_results_window)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("promoter_buying", _study)
