"""Validate candidate signal #4: rights-entitlement (RE) mispricing.

Events: every NSE rights issue since 2020 in `rights_issues` (chittorgarh offer data: exact
issue price, RE symbol, timetable); partly-paid and withdrawn issues excluded. RE prices: nselib
(stored RE symbol, else <SYM>-RE) over the RE trading window; stock: unadjusted NSE closes.

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
from scanner.validation import exclude_results, run  # noqa: E402
from scanner import db  # noqa: E402
from scanner.eventstudy import summarize  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402
from scanner.rights import (  # noqa: E402
    HURDLE, MIN_TURNOVER, PENNY_ISSUE, PENNY_STOCK, events_from_issues, fetch_re_frame, gap_series, re_symbol)

CACHE = Path(__file__).resolve().parent.parent / "cache" / "re"
OUT = Path(__file__).resolve().parent.parent / "cache" / "rights_re_results.csv"


def fetch_re(sym: str, start: date, end: date, stored_re: str | None = None) -> pd.DataFrame | None:
    """RE daily close + turnover (cached CSV; RE windows are short and final once closed)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fp = CACHE / f"{re_symbol(sym).replace('&', '_and_')}_{start}.csv"
    if fp.exists():
        df = pd.read_csv(fp, parse_dates=["date"])
        return df.set_index("date") if len(df) else None
    df = fetch_re_frame(sym, start, end, stored_re)
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
    issues = db.select_all("rights_issues", {
        "select": "symbol,issue_price,ratio_rights,ratio_held,record_date,re_credit_date,issue_open,"
                  "renunciation_date,issue_close,re_symbol,partly_paid,withdrawn",
        "issue_open": "gte.2020-01-01"})
    cutoff = (date.today() - timedelta(days=10)).isoformat()   # RE window must be over
    events = [e for e in events_from_issues(issues) if e["re_to"] <= cutoff]
    print(f"{len(issues)} NSE rights issues since 2020 -> {len(events)} usable "
          f"(fully paid, not withdrawn, RE window over)", flush=True)

    rows = []
    for k, e in enumerate(events, 1):
        ex = date.fromisoformat(e["re_from"])
        re_df = fetch_re(e["symbol"], ex - timedelta(days=3), date.fromisoformat(e["re_to"]) + timedelta(days=2),
                         e["re_symbol"])
        if re_df is None or not len(re_df):
            rows.append({**e, "re_days": 0})
            continue
        stock = get_closes(e["symbol"], ex - timedelta(days=10), date.fromisoformat(e["re_to"]) + timedelta(days=5),
                           source="nse")
        if stock is None:
            rows.append({**e, "re_days": len(re_df), "stock": False})
            continue
        g = gap_series(stock, re_df["close"], e["issue_price"])
        liquid = re_df["turnover"].reindex(g.index).fillna(0) >= MIN_TURNOVER
        rows.append({**e, "re_days": len(re_df), "stock": True, "gap_days": len(g),
                     "liquid_days": int(liquid.sum()),
                     "gaps": ";".join(f"{v:.5f}" for v in g.values),
                     "liquid": ";".join("1" if x else "0" for x in liquid.values),
                     "med_turnover": float(re_df["turnover"].median()),
                     "stock_px": float(stock.reindex(g.index).median()) if len(g) else None})
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
            day_rows.append({"symbol": r["symbol"], "year": int(r["re_from"][:4]), "gap": g, "liquid": l,
                             "penny": r["issue_price"] < PENNY_ISSUE or (r.get("stock_px") or 0) < PENNY_STOCK,
                             "first3": i < 3, "last3": i >= n - 3})
    d = pd.DataFrame(day_rows)
    print("\n=== DAY-LEVEL gap = (S - issue - RE)/S  (positive = RE cheap) ===")
    print(fmt("all RE days", d["gap"]))
    print(fmt("liquid days (>= Rs 5L turnover)", d.loc[d.liquid, "gap"]))
    print(fmt("liquid, first 3 days", d.loc[d.liquid & d.first3, "gap"]))
    print(fmt("liquid, last 3 days", d.loc[d.liquid & d.last3, "gap"]))
    for lo, hi in ((2020, 2022), (2023, 2024), (2025, 2026)):
        print(fmt(f"liquid, {lo}-{hi}", d.loc[d.liquid & d.year.between(lo, hi), "gap"]))

    np_ = d.liquid & ~d.penny
    print(f"\n=== ROBUSTNESS (post-hoc check, not a selection): non-penny = issue >= Rs {PENNY_ISSUE:.0f} "
          f"and stock >= Rs {PENNY_STOCK:.0f} ===")
    print(fmt("liquid, non-penny", d.loc[np_, "gap"]))
    for lo, hi in ((2020, 2022), (2023, 2024), (2025, 2026)):
        print(fmt(f"liquid, non-penny {lo}-{hi}", d.loc[np_ & d.year.between(lo, hi), "gap"]))
    per_np = d[np_].groupby("symbol")["gap"].median()
    print(f"  non-penny issues: {per_np.size}; per-issue median gap {per_np.median()*100:+.2f}%; "
          f"issues with median above hurdle {(per_np > HURDLE).sum()}/{per_np.size}")

    print("\n=== ISSUE-LEVEL (one number per issue: its best liquid day / its liquid-day mean) ===")
    per = d[d.liquid].groupby("symbol")["gap"]
    print(fmt("max liquid-day gap per issue", per.max()))
    print(fmt("mean liquid-day gap per issue", per.mean()))
    print(f"\n  issues with >=1 liquid day above the {HURDLE*100:.1f}% hurdle: "
          f"{int((per.max() > HURDLE).sum())} / {per.ngroups}")


def _study(args) -> dict:
    df = exclude_results(build(), "re_from", args.exclude_results_window)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("rights_re", _study)
