"""Validate candidate signal #4: rights-entitlement (RE) mispricing.

Events: every rights issue since 2020 in corporate_events (nse_ca) with a face value on record
and no later split/bonus/consolidation. RE prices: nselib `<SYM>-RE` (series BE) from ex-date
to ex+60 days; stock: unadjusted NSE closes.

Measured (fixed in advance): daily gap = (S - issue - RE) / S at the close (positive = RE
cheap: RE + subscription beats buying the stock). Tradable days = RE turnover >= Rs 5 lakh.
Hurdle 0.5% of S (RE brokerage/STT + a few weeks' capital lock on the application money).
Cuts: first 3 vs last 3 RE trading days (retail dumping), era, liquidity.

    python scripts/validate_rights_re.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.eventstudy import summarize  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402
from scanner.rights import (  # noqa: E402
    HURDLE, MIN_TURNOVER, SHARE_COUNT_CHANGES, fetch_re_frame, gap_series, re_symbol, rights_events)

CACHE = Path(__file__).resolve().parent.parent / "cache" / "re"
OUT = Path(__file__).resolve().parent.parent / "cache" / "rights_re_results.csv"


def fetch_re(sym: str, start: date, end: date) -> pd.DataFrame | None:
    """RE daily close + turnover (cached CSV; RE windows are short and final once closed)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fp = CACHE / f"{re_symbol(sym).replace('&', '_and_')}_{start}.csv"
    if fp.exists():
        df = pd.read_csv(fp, parse_dates=["date"])
        return df.set_index("date") if len(df) else None
    df = fetch_re_frame(sym, start, end)
    if df is None:
        pd.DataFrame(columns=["date", "close", "turnover"]).to_csv(fp, index=False)
        return None
    df.reset_index().to_csv(fp, index=False)
    return df


def fmt(label: str, xs) -> str:
    s = summarize(list(xs))
    if not s["n"]:
        return f"  {label:<40} n=  0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    xs = pd.Series(list(xs)).dropna()
    return (f"  {label:<40} n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  median={s['median']*100:+6.2f}%  "
            f">hurdle={(xs > HURDLE).mean()*100:4.0f}%  <-hurdle={(xs < -HURDLE).mean()*100:4.0f}%  t={t}")


def build() -> pd.DataFrame:
    rights = db.select_all("corporate_events", {"select": "symbol,event_date,record_date,details",
                                                "event_type": "eq.rights", "event_date": "gte.2020-01-01"})
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(SHARE_COUNT_CHANGES))})",
                                              "event_date": "gte.2020-01-01"})
    fv = {c["symbol"]: c["face_value"] for c in db.select_all("companies", {"select": "symbol,face_value"})
          if c["face_value"]}
    cutoff = (date.today() - timedelta(days=45)).isoformat()   # RE window must be over
    events = [e for e in rights_events(rights, fv, acts) if e["ex_date"] <= cutoff]
    print(f"{len(rights)} rights issues since 2020 -> {len(events)} usable events", flush=True)

    rows = []
    for k, e in enumerate(events, 1):
        ex = date.fromisoformat(e["ex_date"])
        re_df = fetch_re(e["symbol"], ex - timedelta(days=3), ex + timedelta(days=60))
        if re_df is None or not len(re_df):
            rows.append({**e, "re_days": 0})
            continue
        stock = get_closes(e["symbol"], ex - timedelta(days=10), ex + timedelta(days=70), source="nse")
        if stock is None:
            rows.append({**e, "re_days": len(re_df), "stock": False})
            continue
        g = gap_series(stock, re_df["close"], e["issue_price"])
        liquid = re_df["turnover"].reindex(g.index).fillna(0) >= MIN_TURNOVER
        rows.append({**e, "re_days": len(re_df), "stock": True, "gap_days": len(g),
                     "liquid_days": int(liquid.sum()),
                     "gaps": ";".join(f"{v:.5f}" for v in g.values),
                     "liquid": ";".join("1" if x else "0" for x in liquid.values),
                     "med_turnover": float(re_df["turnover"].median())})
        if k % 25 == 0:
            print(f"  {k}/{len(events)}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    ok = df[df.get("gap_days", pd.Series(0, index=df.index)).fillna(0) > 0].copy()
    print(f"\nevents: {len(df)} | no RE prices {int((df['re_days'] == 0).sum())} | "
          f"with gaps {len(ok)}")
    day_rows = []
    for _, r in ok.iterrows():
        gs = [float(x) for x in str(r["gaps"]).split(";")]
        lq = [x == "1" for x in str(r["liquid"]).split(";")]
        n = len(gs)
        for i, (g, l) in enumerate(zip(gs, lq)):
            day_rows.append({"symbol": r["symbol"], "year": int(r["ex_date"][:4]), "gap": g, "liquid": l,
                             "first3": i < 3, "last3": i >= n - 3})
    d = pd.DataFrame(day_rows)
    print("\n=== DAY-LEVEL gap = (S - issue - RE)/S  (positive = RE cheap) ===")
    print(fmt("all RE days", d["gap"]))
    print(fmt("liquid days (>= Rs 5L turnover)", d.loc[d.liquid, "gap"]))
    print(fmt("liquid, first 3 days", d.loc[d.liquid & d.first3, "gap"]))
    print(fmt("liquid, last 3 days", d.loc[d.liquid & d.last3, "gap"]))
    for lo, hi in ((2020, 2022), (2023, 2024), (2025, 2026)):
        print(fmt(f"liquid, {lo}-{hi}", d.loc[d.liquid & d.year.between(lo, hi), "gap"]))

    print("\n=== ISSUE-LEVEL (one number per issue: its best liquid day / its liquid-day mean) ===")
    per = d[d.liquid].groupby("symbol")["gap"]
    print(fmt("max liquid-day gap per issue", per.max()))
    print(fmt("mean liquid-day gap per issue", per.mean()))
    print(f"\n  issues with >=1 liquid day above the {HURDLE*100:.1f}% hurdle: "
          f"{int((per.max() > HURDLE).sum())} / {per.ngroups}")


if __name__ == "__main__":
    report(build())
