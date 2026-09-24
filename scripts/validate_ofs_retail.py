"""Validate candidate signal #23: the OFS retail reservation.

Events: every OFS in `ofs_events` (chittorgarh, Jan-2025 ->) whose retail day is >= 25 days old.
Prices: unadjusted NSE closes from the cloud store (source="db").

Measured (fixed in advance), all vs the FLOOR price (the retail bidder's entry when the
non-retail book clears at the floor — a higher cut-off only makes the entry worse):
  floor_discount        = floor / close before the non-retail day - 1   (what the seller concedes)
  nonretail_day_move    = non-retail-day close / that pre-close - 1     (the OFS-day drop)
  retail_close_vs_floor = retail-day close / floor - 1                  (is the floor still cheap?)
  t1 / t5 / t20         = close 1 / 5 / 20 sessions after the retail day / floor - 1
The actionable leg is t1 (allotment on T+1 = first sellable session) net of ~0.3% costs; a PSU
retail discount (typically 5%, not on the page) would ADD to the PSU rows — flagged, not assumed.
Segments (pre-specified): PSU seller vs private; retail quota share; stake size (% of equity).

    python scripts/validate_ofs_retail.py [--exclude-results-window N] [--publish]
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
from scanner.ofs import ofs_returns, study_events  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402

COST = 0.003
OUT = Path(__file__).resolve().parent.parent / "cache" / "ofs_retail_results.csv"
COLS = ["floor_discount", "nonretail_day_move", "retail_close_vs_floor", "t1", "t5", "t20"]


def fmt(label: str, xs) -> str:
    s = summarize([x for x in xs if x is not None and not pd.isna(x)])
    if not s["n"]:
        return f"  {label:<38} n=   0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    return (f"  {label:<38} n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  median={s['median']*100:+6.2f}%  "
            f"up={s['pct_positive']*100:4.0f}%  t={t}")


def build() -> pd.DataFrame:
    rows = db.select_all("ofs_events", {"select": "chittorgarh_id,symbol,seller,floor_price,retail_date,"
                                                  "non_retail_date,retail_shares,total_shares,pct_equity"})
    events = study_events(rows, today=date.today())
    print(f"{len(rows)} OFS events stored -> {len(events)} with a retail day >= 25 days old", flush=True)
    out = []
    for e in events:
        rd = date.fromisoformat(e["retail_date"])
        px = get_closes(e["symbol"], rd - timedelta(days=15), rd + timedelta(days=40), source="db")
        r = ofs_returns(px, e["floor_price"], e["retail_date"], e["non_retail_date"])
        out.append({**e, **(r or {}), "priced": r is not None})
    df = pd.DataFrame(out)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    ok = df[df["priced"]].copy()
    print(f"\nevents: {len(df)} | priced {len(ok)} | PSU sellers {int(ok['psu'].sum())}")
    print("\n=== ALL (vs floor; t1 = allotment day, the first sellable close) ===")
    for c in COLS:
        print(fmt(c, ok[c]))
    print(fmt("t1 net of costs", ok["t1"] - COST))
    for label, mask in (("PSU seller", ok["psu"]), ("private seller", ~ok["psu"])):
        print(f"\n=== {label} ===")
        for c in ("floor_discount", "retail_close_vs_floor", "t1", "t5", "t20"):
            print(fmt(c, ok.loc[mask, c]))
    # Robustness (pre-specified): a floor far below the market means the non-retail book cleared
    # well above it and retail paid the cut-off, not the floor — those rows overstate the retail
    # leg. Keep floors within 15% of the pre-close and never above it.
    clean = ok[(ok["floor_discount"] <= 0) & (ok["floor_discount"] >= -0.15)]
    print(f"\n=== ROBUSTNESS: floor within 15% below the pre-close (book plausibly clears at the floor) "
          f"n={len(clean)} of {len(ok)} ===")
    for c in ("floor_discount", "retail_close_vs_floor", "t1", "t5", "t20"):
        print(fmt(c, clean[c]))
    print(fmt("t1 net of costs", clean["t1"] - COST))
    for label, mask in (("PSU seller", clean["psu"]), ("private seller", ~clean["psu"])):
        print(fmt(f"{label} t1", clean.loc[mask, "t1"]))
        print(fmt(f"{label} t20", clean.loc[mask, "t20"]))
    med = ok["pct_equity"].median()
    if pd.notna(med):
        print(f"\n=== stake size (pct_equity above / below median {med:.1f}%) ===")
        for label, mask in (("large stake", ok["pct_equity"] >= med), ("small stake", ok["pct_equity"] < med)):
            print(fmt(f"{label} t1", ok.loc[mask, "t1"]))
            print(fmt(f"{label} t20", ok.loc[mask, "t20"]))
    print("\n=== per event ===")
    cols = ["symbol", "retail_date", "psu", "floor_price", "floor_discount", "retail_close_vs_floor", "t1", "t5", "t20"]
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        show = ok[cols].copy()
        for c in ("floor_discount", "retail_close_vs_floor", "t1", "t5", "t20"):
            show[c] = (show[c] * 100).round(2)
        print(show.sort_values("retail_date").to_string(index=False))
    print("\nNote: cut-off prices above the floor (oversubscribed books) are not on the source page; "
          "the retail entry is therefore no better than measured. PSU retail discounts (~5%) are also "
          "unrecorded and would improve the PSU rows.")


def _study(args) -> dict:
    df = exclude_results(build(), "retail_date", args.exclude_results_window)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("ofs_retail", _study)
