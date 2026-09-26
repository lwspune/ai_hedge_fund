"""Validate: does a breakout from a price consolidation pay?

Consolidation (scanner/consolidation.py): a 40-session range <= 10% of price on a stock with median
turnover >= Rs 1 crore/day; breakout = the first close outside the range as it stood the day before.
Every NSE company (the company master, listed + delisted — ETFs and funds excluded), Jan-2020 ->
(raw bhavcopy OHLC, one read per month: pricestore.bar_panel).
Fixed in advance:
  entry     the close the session AFTER the breakout (the evening scan's earliest action)
  measured  +5 / +20 / +60 sessions abnormal vs NIFTY 500; up and down breakouts separately;
            t clustered by week; medians and hit rates, costs ~0.3% round trip
  CONTROL   (a) breakouts of the same kind out of WIDE ranges (a 40-day high / low from a range
            > 10%): is the tight range what matters? (b) the same stock entered 120 sessions earlier
  segments  base after a rally (the 60 sessions before the range up > 20%) or not; breakout volume
            >= 1.5x the range's average; delivery >= 50%; liquidity tercile (median turnover over the
            range — point-in-time; per-event market cap is too slow at this event count); mainboard vs
            SME; era 2020-22 vs 2023-26. Robustness: the headline with a 20-session window.
A split / bonus / consolidation / rights / demerger from 90 days before to 100 days after drops the
event (unadjusted prices). A buy signal needs a positive median up-breakout after costs that beats
both controls in both eras.

    python scripts/validate_consolidation.py [--publish]
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.consolidation import breakout_events  # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pricestore import bar_panel, get_closes  # noqa: E402
from scanner.validation import run  # noqa: E402

BENCH = "^CRSLDX"
START = date(2020, 1, 1)
HORIZONS = (5, 20, 60)
PLACEBO_LAG = 120
SME_SERIES = {"SM", "ST", "SZ"}
OUT = Path(__file__).resolve().parent.parent / "cache" / "consolidation_results.csv"


def fmt(label: str, xs, clusters=None) -> str:
    s = summarize(list(xs), clusters=None if clusters is None else list(clusters))
    if not s["n"]:
        return f"  {label:<46} n=     0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    tc = f"  t_cl={s['t_cluster']:+5.1f}" if s.get("t_cluster") is not None else ""
    return (f"  {label:<46} n={s['n']:>6}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}{tc}")


def build(panel: dict, bench: pd.Series, acts: dict, sme: set, n: int) -> pd.DataFrame:
    rows = []
    for k, (sym, df) in enumerate(panel.items(), 1):
        if len(df) <= n + 5:
            continue
        close = df["close"]
        for e in breakout_events(df, sym, n=n):
            t = e["date"]
            if blocking_action(acts.get(sym, []), sym, t - pd.Timedelta(days=90), t + pd.Timedelta(days=100)):
                continue
            i = close.index.get_loc(t)
            row = {**e, "board": "sme" if sym in sme else "main", "year": t.year,
                   "week": f"{t.isocalendar().year}-{t.isocalendar().week:02d}"}
            for h in HORIZONS:
                row[f"h{h}"] = forward_abnormal_return(close, bench, t, h, entry_lag=1)
            if e["tight"] and i - PLACEBO_LAG >= 0:
                row["placebo_h20"] = forward_abnormal_return(close, bench, close.index[i - PLACEBO_LAG], 20, entry_lag=1)
                row["placebo_h60"] = forward_abnormal_return(close, bench, close.index[i - PLACEBO_LAG], 60, entry_lag=1)
            rows.append(row)
        if k % 500 == 0:
            print(f"  {k}/{len(panel)} symbols, {len(rows)} events", flush=True)
    return pd.DataFrame(rows)


def _leg(d: pd.DataFrame, label: str) -> None:
    for h in HORIZONS:
        m = d[f"h{h}"].notna()
        print(fmt(f"{label} +{h}", d.loc[m, f"h{h}"], d.loc[m, "week"]))


def report(df: pd.DataFrame, df20: pd.DataFrame) -> None:
    tight, wide = df[df["tight"]], df[~df["tight"]]
    print(f"\nevents: tight {len(tight)} (up {int((tight['direction'] == 'up').sum())}), wide control {len(wide)}")
    for direction in ("up", "down"):
        t, w = tight[tight["direction"] == direction], wide[wide["direction"] == direction]
        print(f"\n=== {direction.upper()} breakouts (abnormal vs NIFTY 500, entry = the next session's close) ===")
        _leg(t, f"TIGHT range {direction}")
        _leg(w, f"  control: wide-range {direction}")
        for h in (20, 60):
            m = t[f"placebo_h{h}"].notna()
            print(fmt(f"  control: same stock 120 sessions earlier +{h}", t.loc[m, f"placebo_h{h}"], t.loc[m, "week"]))
    up = tight[tight["direction"] == "up"].copy()
    terc = up["turnover_lakh"].quantile([1 / 3, 2 / 3]).to_list()
    cuts = {"base after a rally (prior 60s > +20%)": up["prior_move"] > 0.20,
            "no prior rally": up["prior_move"] <= 0.20,
            "breakout volume >= 1.5x": up["vol_ratio"] >= 1.5, "breakout volume < 1.5x": up["vol_ratio"] < 1.5,
            "delivery >= 50%": up["delivery_pct"] >= 50, "delivery < 50%": up["delivery_pct"] < 50,
            "liquidity: low tercile": up["turnover_lakh"] <= terc[0],
            "liquidity: high tercile": up["turnover_lakh"] > terc[1],
            "mainboard": up["board"] == "main", "SME": up["board"] == "sme",
            "era 2020-22": up["year"].between(2020, 2022), "era 2023-26": up["year"].between(2023, 2026)}
    print("\n=== TIGHT UP breakouts — SEGMENTS (pre-specified) — +20 | +60 ===")
    for label, m in cuts.items():
        m = m.fillna(False).astype(bool)
        for h in (20, 60):
            mm = m & up[f"h{h}"].notna()
            print(fmt(f"{label} [+{h}]", up.loc[mm, f"h{h}"], up.loc[mm, "week"]))
    up20 = df20[df20["tight"] & (df20["direction"] == "up")]
    print("\n=== ROBUSTNESS: 20-session window, tight up breakouts ===")
    _leg(up20, "TIGHT(20) up")
    print("\nA buy signal needs a positive MEDIAN after ~0.3% costs that beats both controls in both eras.")


def _study(args) -> dict:
    today = date.today()
    panel = bar_panel(START, today)
    print(f"{len(panel)} symbols priced {START} -> {today}", flush=True)
    bench = get_closes(BENCH, "2019-06-01", source="yf")
    acts: dict = {}
    for a in db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                                 "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                                 "event_date": "gte.2019-09-01"}):
        acts.setdefault(a["symbol"], []).append(a)
    companies = db.select_all("companies", {"select": "symbol,series"})   # listed + delisted, no ETFs
    sme = {c["symbol"] for c in companies if c.get("series") in SME_SERIES}
    universe = {c["symbol"] for c in companies}
    dropped = len(panel)
    panel = {s: d for s, d in panel.items() if s in universe}
    print(f"company universe: {len(panel)} symbols ({dropped - len(panel)} ETFs / funds / other series dropped)", flush=True)
    df = build(panel, bench, acts, sme, 40)
    df20 = build(panel, bench, acts, sme, 20)
    OUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUT, index=False)
    report(df, df20)
    return {"results": df, "window20": df20}


if __name__ == "__main__":
    run("consolidation", _study)
