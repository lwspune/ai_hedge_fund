"""Control study (backlog #17): turn-of-month seasonality on NIFTY 50 and NIFTY 500.

Expect null net of costs. Measured (fixed in advance): mean daily return on the last 1 + first 3
trading days of each month vs all other days, pooled and by era, on unadjusted index closes from
the cloud store (2020->; `--yf` for the long Yahoo history back to 2007).

    python scripts/validate_turn_of_month.py [--yf] [--publish]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import run  # noqa: E402
from scanner.eventstudy import summarize  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402
from scanner.seasonality import bucket_returns  # noqa: E402

COST_ROUND_TRIP = 0.0005   # an index ETF round trip (STT 0.001% sell + spread), per month


def fmt(label: str, xs) -> str:
    s = summarize(list(xs))
    if not s["n"]:
        return f"  {label:<34} n=   0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    return (f"  {label:<34} n={s['n']:>5}  mean={s['mean']*100:+6.3f}%/day  "
            f"median={s['median']*100:+6.3f}%  up={s['pct_positive']*100:4.0f}%  t={t}")


def _study(args) -> dict:
    yf = "--yf" in sys.argv
    frames = []
    for sym in ("^NSEI", "^CRSLDX"):
        s = get_closes(sym, "2007-01-01", source="yf" if yf else "db")
        if s is None or s.empty:
            print(f"{sym}: no prices")
            continue
        b = bucket_returns(s)
        print(f"\n=== {sym} ({s.index.min().date()} -> {s.index.max().date()}, source={'yf' if yf else 'db'}) ===")
        print(fmt("turn-of-month days (-1..+3)", b["tom"]))
        print(fmt("all other days", b["rest"]))
        months = b["tom"].groupby(b["tom"].index.to_period("M")).sum()
        print(fmt("per-month TOM window return", months).replace("%/day", "/mo  "))
        print(f"  TOM window per month net of ~{COST_ROUND_TRIP*100:.2f}% ETF round trip: "
              f"{(months.mean() - COST_ROUND_TRIP)*100:+.3f}%")
        for lo, hi in ((2007, 2019), (2020, 2021), (2022, 2023), (2024, 2026)):
            m = b["tom"][(b["tom"].index.year >= lo) & (b["tom"].index.year <= hi)]
            r = b["rest"][(b["rest"].index.year >= lo) & (b["rest"].index.year <= hi)]
            if len(m):
                print(fmt(f"era {lo}-{hi} TOM", m))
                print(fmt(f"era {lo}-{hi} rest", r))
        frames.append(pd.DataFrame({"symbol": sym, "ret": pd.concat([b["tom"], b["rest"]]),
                                    "tom": [True] * len(b["tom"]) + [False] * len(b["rest"])}))
    df = pd.concat(frames) if frames else pd.DataFrame()
    return {"results": df.reset_index().rename(columns={"index": "date"})}


if __name__ == "__main__":
    run("turn_of_month", _study)
