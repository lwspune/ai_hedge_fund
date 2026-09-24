"""Segment the Next 50 rebalance events by the ONLY mechanism-motivated cut:
the size of the forced flow relative to liquidity (proxy: pre-event ₹ ADV).

The index-effect mechanism predicts any effect concentrates in the LEAST-liquid
affected names (forced flow is large vs normal volume). So we tercile events by
pre-announcement median daily turnover and re-run:
  * ADDS  — TIGHT window (effective-5 -> effective): does a pop appear in illiquid adds?
  * DROPS — POST  window (effective -> effective+5): does the rebound concentrate
            in the most-illiquid (most-oversold) deletions?
Plus a confirmatory ERA cut (passive AUM grew, so any effect should decay).

Pre-event ADV is measured over the 20 sessions ending 3 days BEFORE announce, so the
liquidity measure is not contaminated by the event itself. GROSS, pre-cost.

    python scripts/segment_index_rebalance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.eventstudy import summarize
from scanner.rebalance import abnormal_return_between, drop_blocked, load_next50_events
from validate_index_rebalance import POST_DAYS, _signed, load_bench, load_blocking_actions  # reuse helpers


def fetch(symbol, start, end):
    """Return (close, turnover) daily series via nselib, EQ only. None on failure."""
    from nselib import capital_market as cm
    f, t = pd.Timestamp(start).strftime("%d-%m-%Y"), pd.Timestamp(end).strftime("%d-%m-%Y")
    try:
        df = cm.price_volume_and_deliverable_position_data(symbol=symbol, from_date=f, to_date=t)
    except Exception:
        return None, None
    if df is None or len(df) == 0:
        return None, None
    df = df.copy()
    if "Series" in df.columns:
        df = df[df["Series"].astype(str).str.strip() == "EQ"]
    df["d"] = pd.to_datetime(df["Date"], format="%d-%b-%Y", errors="coerce")
    df = df.dropna(subset=["d"]).sort_values("d").set_index("d")
    close = pd.to_numeric(df["ClosePrice"].astype(str).str.replace(",", ""), errors="coerce")
    turn_col = next((c for c in df.columns if "Turnover" in c), None)
    turn = (pd.to_numeric(df[turn_col].astype(str).str.replace(",", ""), errors="coerce")
            if turn_col else pd.Series(np.nan, index=df.index))
    return close.dropna(), turn


def tercile_report(title, rows):
    """rows = list of (adv, signed_ret). Split by ADV terciles, summarize each."""
    rows = [(a, r) for a, r in rows if a is not None and not np.isnan(a) and r is not None]
    if len(rows) < 6:
        print(f"  {title}: too few ({len(rows)})")
        return
    advs = sorted(a for a, _ in rows)
    lo, hi = advs[len(advs) // 3], advs[2 * len(advs) // 3]
    buckets = {"LOW liq": [], "MID liq": [], "HIGH liq": []}
    for a, r in rows:
        buckets["LOW liq" if a <= lo else "HIGH liq" if a > hi else "MID liq"].append(r)
    print(f"  {title}")
    for name, rs in buckets.items():
        s = summarize(rs)
        if s["n"]:
            tt = f" t={s['t_stat']:.2f}" if s["t_stat"] is not None else ""
            print(f"    {name:<9} n={s['n']:>2}  mean {s['mean']*100:+.2f}%  "
                  f"median {s['median']*100:+.2f}%  win {s['pct_positive']*100:.0f}%{tt}")


def main():
    events, blocked = drop_blocked(load_next50_events(), load_blocking_actions(), post_days=POST_DAYS)
    if blocked:
        print(f"dropped {len(blocked)} events with a split/bonus/rights/demerger inside the window: "
              f"{', '.join(f'{e.symbol}({e.review})' for e in blocked)}")
    lo = min(pd.Timestamp(e.announce) for e in events) - pd.Timedelta(days=40)
    hi = max(pd.Timestamp(e.effective) for e in events) + pd.Timedelta(days=15)
    bench = load_bench(f"{lo:%Y-%m-%d}", f"{hi:%Y-%m-%d}")

    recs = []  # (leg, review, adv, tight, post, wide)
    for ev in events:
        close, turn = fetch(ev.symbol,
                            f"{pd.Timestamp(ev.announce) - pd.Timedelta(days=40):%Y-%m-%d}",
                            f"{pd.Timestamp(ev.effective) + pd.Timedelta(days=15):%Y-%m-%d}")
        if close is None:
            continue
        # pre-event liquidity: median daily turnover, 20 sessions ending 3d before announce
        pre = turn.loc[: pd.Timestamp(ev.announce) - pd.Timedelta(days=3)].dropna()
        adv = float(pre.tail(20).median()) if len(pre) >= 5 else np.nan
        eff = pd.Timestamp(ev.effective)
        tight = _signed(ev.leg, abnormal_return_between(
            close, bench, f"{eff - pd.Timedelta(days=8):%Y-%m-%d}", ev.effective, entry_lag=0))
        post = _signed(ev.leg, abnormal_return_between(
            close, bench, ev.effective, f"{eff + pd.Timedelta(days=8):%Y-%m-%d}", entry_lag=0))
        wide = _signed(ev.leg, abnormal_return_between(
            close, bench, ev.announce, ev.effective, entry_lag=1))
        recs.append((ev.leg, ev.review, adv, tight, post, wide))

    adds = [r for r in recs if r[0] == "add"]
    drops = [r for r in recs if r[0] == "drop"]

    print(f"\n=== LIQUIDITY TERCILES (pre-event median daily turnover, Rs) ===  n_add={len(adds)} n_drop={len(drops)}")
    print("\nADDS — TIGHT window (effective-5 -> effective), long:")
    tercile_report("by liquidity", [(r[2], r[3]) for r in adds])
    print("\nDROPS — POST window (effective -> effective+5), short-leg signed:")
    tercile_report("by liquidity", [(r[2], r[4]) for r in drops])
    print("  (reminder: short-leg negative = deleted stock ROSE = forced-selling rebound)")

    print("\n=== ERA CUT (confirmatory: passive AUM grew -> effect should decay) ===")
    def era(rev):
        y = int(rev[:4])
        return "2018-2020" if y <= 2020 else "2021-2022" if y <= 2022 else "2023-2025"
    for period in ("2018-2020", "2021-2022", "2023-2025"):
        a_tight = summarize([r[3] for r in adds if era(r[1]) == period])
        d_post = summarize([r[4] for r in drops if era(r[1]) == period])
        print(f"  {period}: ADD tight mean "
              f"{a_tight['mean']*100:+.2f}% (n={a_tight['n']}) | "
              f"DROP post mean {d_post['mean']*100:+.2f}% (n={d_post['n']})"
              if a_tight['n'] and d_post['n'] else f"  {period}: insufficient")

    print("\nGROSS, pre-cost. Terciles ~25/cell -> suggestive, not a verdict.")


if __name__ == "__main__":
    main()
