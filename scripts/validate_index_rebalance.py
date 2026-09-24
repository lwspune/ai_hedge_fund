"""Validate the index-rebalance front-run signal (🟢 structural / forced-flow).

Hypothesis: passive funds are forced to buy index ADDITIONS / sell DELETIONS at the
effective-date close. Front-run it: long adds, short drops.

Three windows, each benchmark-adjusted vs NIFTY and signed by leg (long add / short drop):
  * WIDE  : announce+1 -> effective       (the full front-run hold)
  * TIGHT : effective-5d -> effective      (just the forced-flow run-up window)
  * POST  : effective -> effective+5d      (reversal: does the move give back?)

Universe: NIFTY Next 50 clean regular-review entries/exits (default) or NIFTY 50.
Next 50 excludes promotion/relegation events (confounded by the larger opposite-
direction Nifty 50 flow) and ad-hoc/merger reviews — see scanner/rebalance.py.

    python scripts/validate_index_rebalance.py            # Next 50 (n=151)
    python scripts/validate_index_rebalance.py --nifty50  # Nifty 50 (n=20)

GROSS, pre-cost. Net ~30bps round-trip + STT (+ short-leg needs single-stock futures)
before any verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, run  # noqa: E402

from scanner.eventstudy import summarize
from scanner.lockin import BLOCKING
from scanner.rebalance import EVENTS, abnormal_return_between, drop_blocked, load_next50_events

BENCH = "^NSEI"  # NIFTY 50 as the broad-market benchmark
POST_DAYS = 8    # calendar days after the effective date covered by the POST window


def load_blocking_actions() -> list[dict]:
    """Split/bonus/rights/consolidation/demerger ex-dates (corporate_events, nse_ca, 2010->):
    the closes are UNADJUSTED, so an event with one inside its window is dropped."""
    from scanner import db
    return db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})"})


def nse_close_series(symbol: str, start: str, end: str):
    from nselib import capital_market as cm
    f, t = pd.Timestamp(start).strftime("%d-%m-%Y"), pd.Timestamp(end).strftime("%d-%m-%Y")
    try:
        df = cm.price_volume_and_deliverable_position_data(symbol=symbol, from_date=f, to_date=t)
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    if "Series" in df.columns:
        df = df[df["Series"].astype(str).str.strip() == "EQ"]
    df["d"] = pd.to_datetime(df["Date"], format="%d-%b-%Y", errors="coerce")
    df = df.dropna(subset=["d"]).sort_values("d")
    close = pd.to_numeric(df["ClosePrice"].astype(str).str.replace(",", ""), errors="coerce")
    return pd.Series(close.values, index=df["d"].values, dtype="float64").dropna()


def load_bench(start: str, end: str):
    import yfinance as yf
    df = yf.download(BENCH, start=start, end=end, progress=False, auto_adjust=True)
    s = df["Close"]
    s = s.iloc[:, 0] if hasattr(s, "columns") else s
    return pd.Series(s.values, index=pd.to_datetime(s.index), dtype="float64").dropna()


def _signed(leg, r):
    return None if r is None else (r if leg == "add" else -r)


def windows(ev, stock, bench):
    eff = pd.Timestamp(ev.effective)
    wide = abnormal_return_between(stock, bench, ev.announce, ev.effective, entry_lag=1)
    tight = abnormal_return_between(stock, bench, f"{eff - pd.Timedelta(days=8):%Y-%m-%d}",
                                    ev.effective, entry_lag=0)
    post = abnormal_return_between(stock, bench, ev.effective,
                                   f"{eff + pd.Timedelta(days=8):%Y-%m-%d}", entry_lag=0)
    return _signed(ev.leg, wide), _signed(ev.leg, tight), _signed(ev.leg, post)


def report(label, rows):
    """rows = [(signed return | None, review)]. t = iid; t_cl = clustered by review (every
    event of one review shares the same dates, so they are not independent draws)."""
    vals = [r for r, _ in rows]
    s = summarize(vals, clusters=[c for _, c in rows])
    if not s["n"]:
        print(f"  {label:<14} n=0")
        return
    t = f"  t={s['t_stat']:.2f}" if s["t_stat"] is not None else ""
    tc = f"  t_cl={s['t_cluster']:.2f} ({s['n_clusters']} reviews)" if s["t_cluster"] is not None else ""
    print(f"  {label:<14} n={s['n']:>3}  mean {s['mean']*100:+.2f}%  "
          f"median {s['median']*100:+.2f}%  win {s['pct_positive']*100:.0f}%{t}{tc}")


def main(args) -> dict:
    use_nifty50 = "--nifty50" in sys.argv[1:]
    events = EVENTS if use_nifty50 else load_next50_events()
    if args.exclude_results_window:
        keep = exclude_results(pd.DataFrame({"symbol": [e.symbol for e in events],
                                             "effective": [e.effective for e in events],
                                             "i": range(len(events))}),
                               "effective", args.exclude_results_window)
        events = [events[i] for i in keep["i"]]
    name = "NIFTY 50" if use_nifty50 else "NIFTY Next 50 (clean entries/exits)"
    events, blocked = drop_blocked(events, load_blocking_actions(), post_days=POST_DAYS)
    print(f"=== {name} — {len(events)} events ===")
    if blocked:
        print(f"dropped {len(blocked)} for a split/bonus/rights/demerger inside the window "
              f"(unadjusted closes): {', '.join(f'{e.symbol}({e.review})' for e in blocked)}")

    span_lo = min(pd.Timestamp(e.announce) for e in events) - pd.Timedelta(days=12)
    span_hi = max(pd.Timestamp(e.effective) for e in events) + pd.Timedelta(days=15)
    bench = load_bench(f"{span_lo:%Y-%m-%d}", f"{span_hi:%Y-%m-%d}")

    res = {"add": {"wide": [], "tight": [], "post": []},
           "drop": {"wide": [], "tight": [], "post": []}}
    missing = []
    for ev in events:
        stock = nse_close_series(ev.symbol,
                                 f"{pd.Timestamp(ev.announce) - pd.Timedelta(days=12):%Y-%m-%d}",
                                 f"{pd.Timestamp(ev.effective) + pd.Timedelta(days=15):%Y-%m-%d}")
        if stock is None:
            missing.append(f"{ev.symbol}({ev.review})")
            continue
        w, t, p = windows(ev, stock, bench)
        res[ev.leg]["wide"].append((w, ev.review))
        res[ev.leg]["tight"].append((t, ev.review))
        res[ev.leg]["post"].append((p, ev.review))

    for win in ("wide", "tight", "post"):
        title = {"wide": "WIDE  announce+1->effective", "tight": "TIGHT effective-5->effective",
                 "post": "POST  effective->effective+5"}[win]
        print(f"\n{title}")
        report("ADDS (long)", res["add"][win])
        report("DROPS (short)", res["drop"][win])
        report("COMBINED", res["add"][win] + res["drop"][win])

    if missing:
        print(f"\nprice-missing ({len(missing)}, excluded): {', '.join(missing)}")
    print("\nGROSS, pre-cost. Net ~30bps + STT (+ futures for the short leg) before any verdict.")
    return {"results": pd.DataFrame([vars(e) for e in events])}


if __name__ == "__main__":
    run("index_rebalance", main)
