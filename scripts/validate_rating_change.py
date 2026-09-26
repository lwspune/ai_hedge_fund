"""Validate candidate signal: does a credit-rating change move the stock?

Events: scanner/ratingevents.rating_events over credit_ratings (NSE Reg 30 rating filings,
2020 ->): domestic long-term upgrades / downgrades (size from the stated or our own previous
rating), rating-watch placements, and reaffirmations as the CONTROL (same kind of filing, no
news). T = the first session the market can react (filings at/after 15:30 IST count next day).
One event per symbol and kind within 30 days.

Measured (fixed in advance), abnormal vs NIFTY 500:
  pre    T-21 -> T-1   anticipation (agencies act on public information)
  react  T-1  -> T+1   the announcement move
  +5 / +20 / +60       a follower entering at the T+1 close
CONTROL: reaffirmations, and the same stock's same-length windows 120 sessions earlier
(placebo_react T-121 -> T-119, placebo_20 T-120 -> T-100). Statistics: iid t and a cluster-robust
t by event week. Pre-specified segments (downgrades, then upgrades): crossing investment grade,
into default, size (1 vs 2+ notches), point-in-time market cap, era, agency.
Prices: unadjusted closes (cloud store from Feb-2020, nselib before); a split / bonus / rights /
consolidation / demerger from T-180 d to T+100 d drops the event.

    python scripts/validate_rating_change.py [--exclude-results-window N] [--publish]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize, window_return  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pointintime import mcap_bucket_at  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402
from scanner.ratingevents import rating_events  # noqa: E402
from scanner.validation import exclude_results, run  # noqa: E402

BENCH = "^CRSLDX"
HORIZONS = (5, 20, 60)
WINDOWS = {"pre": (-21, -1), "react": (-1, 1), "placebo_react": (-121, -119), "placebo_20": (-120, -100)}
DB_FROM = pd.Timestamp("2020-02-01")
COST = 0.003
MIN_GLOBAL = 30
LEGS = ("down", "up", "watch_neg", "watch_pos", "affirm")
OUT = Path(__file__).resolve().parent.parent / "cache" / "rating_change_results.csv"


def fmt(label: str, xs, clusters=None) -> str:
    s = summarize(list(xs), clusters=None if clusters is None else list(clusters))
    if not s["n"]:
        return f"  {label:<40} n=   0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    tc = f"  t_cl={s['t_cluster']:+5.1f} ({s['n_clusters']})" if s.get("t_cluster") is not None else ""
    return (f"  {label:<40} n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}{tc}")


def closes_for(sym: str, start, end) -> pd.Series | None:
    src = "db" if pd.Timestamp(start) >= DB_FROM else "nse"
    try:
        return get_closes(sym, start, end, source=src)
    except Exception as ex:  # nselib raises on renamed / unknown symbols
        print(f"  {sym}: {ex!r}"[:100])
        return None


def load_events() -> tuple[list[dict], list[dict]]:
    rows = db.select_all("credit_ratings", {
        "select": "seq_id,symbol,agency,scale,term,rating,notch,action,prev_rating,watch,disclosed_at",
        "order": "id"})
    return rating_events(rows), rating_events(rows, scale="global")


def build(events: list[dict], scale: str) -> pd.DataFrame:
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": "gte.2019-06-01"})
    bench = get_closes(BENCH, "2019-01-01", source="yf")
    span: dict[str, list] = {}
    for e in events:
        span.setdefault(e["symbol"], []).append(pd.Timestamp(e["event_date"]))
    prices = {}
    for k, sym in enumerate(sorted(span), 1):
        prices[sym] = closes_for(sym, (min(span[sym]) - pd.Timedelta(days=200)).date(),
                                 (max(span[sym]) + pd.Timedelta(days=100)).date())
        if k % 100 == 0:
            print(f"  priced {k}/{len(span)} symbols", flush=True)
    out = []
    for e in events:
        s, t0 = prices.get(e["symbol"]), pd.Timestamp(e["event_date"])
        row = {**e, "scale": scale, "priced": s is not None and len(s) > 0,
               "blocked": blocking_action(acts, e["symbol"], t0 - pd.Timedelta(days=180), t0 + pd.Timedelta(days=100)),
               "week": f"{t0.isocalendar().year}-{t0.isocalendar().week:02d}"}
        if row["priced"] and not row["blocked"]:
            for w, (a, b) in WINDOWS.items():
                row[w] = window_return(s, bench, t0, a, b)
            for h in HORIZONS:
                row[f"h{h}"] = forward_abnormal_return(s, bench, t0, h, entry_lag=1)
            if e["kind"] in ("up", "down"):
                row["mcap"] = mcap_bucket_at(e["symbol"], e["event_date"])
        out.append(row)
    return pd.DataFrame(out)


def _leg(sub: pd.DataFrame, title: str) -> None:
    print(f"\n=== {title} ===")
    for w in ("pre", "react"):
        m = sub[w].notna()
        print(fmt(f"{w:<6} T{WINDOWS[w][0]:+d}->T{WINDOWS[w][1]:+d}", sub.loc[m, w], sub.loc[m, "week"]))
    for h in HORIZONS:
        m = sub[f"h{h}"].notna()
        print(fmt(f"follower +{h}d (entry T+1 close)", sub.loc[m, f"h{h}"], sub.loc[m, "week"]))
    for w in ("placebo_react", "placebo_20"):
        m = sub[w].notna()
        print(fmt(f"CONTROL {w} T{WINDOWS[w][0]:+d}->T{WINDOWS[w][1]:+d}", sub.loc[m, w], sub.loc[m, "week"]))


def _segments(sub: pd.DataFrame, title: str) -> None:
    yr = pd.to_datetime(sub["event_date"]).dt.year
    big3 = sub["agency"].isin(["CRISIL", "ICRA", "CARE"])
    cuts = {"crosses investment grade": sub["ig_cross"], "into default (D)": sub["default"],
            "1 notch": sub["delta"].abs() == 1, "2+ notches": sub["delta"].abs() >= 2,
            "size unknown (verb only)": sub["delta"].isna(),
            "mcap small / small_mid": sub.get("mcap", pd.Series(index=sub.index, dtype=object)).isin(["small", "small_mid"]),
            "mcap mid / large": sub.get("mcap", pd.Series(index=sub.index, dtype=object)).isin(["mid", "large"]),
            "era 2020-22": yr.between(2020, 2022), "era 2023-26": yr.between(2023, 2026),
            "agency CRISIL / ICRA / CARE": big3, "agency others": ~big3}
    print(f"\n=== {title} SEGMENTS (pre-specified) — react | +20d ===")
    for label, m in cuts.items():
        m = m.fillna(False).astype(bool)
        print(fmt(f"{label} [react]", sub.loc[m, "react"].dropna()))
        print(fmt(f"{label} [+20d]", sub.loc[m, "h20"].dropna()))


def report(df: pd.DataFrame) -> None:
    dom = df[df["scale"] == "domestic"]
    print("\nEVENTS (domestic long-term, clustered):")
    print(dom.groupby("kind").agg(events=("symbol", "size"), priced=("priced", "sum"),
                                  blocked=("blocked", "sum")).to_string())
    for kind in ("down", "up"):
        k = dom[dom["kind"] == kind]
        print(f"  {kind}: crosses IG {int(k['ig_cross'].sum())}, default {int(k['default'].sum())}, "
              f"size known {int(k['delta'].notna().sum())}; by year "
              f"{pd.to_datetime(k['event_date']).dt.year.value_counts().sort_index().to_dict()}")
    ok = dom[dom["priced"] & ~dom["blocked"]]
    for kind in LEGS:
        _leg(ok[ok["kind"] == kind], f"{kind} (abnormal vs NIFTY 500)")
    _segments(ok[ok["kind"] == "down"], "DOWNGRADES")
    _segments(ok[ok["kind"] == "up"], "UPGRADES")
    glob = df[(df["scale"] == "global") & df["priced"] & ~df["blocked"]]
    moves = glob[glob["kind"].isin(["up", "down"])]
    if len(moves) >= MIN_GLOBAL:
        for kind in ("down", "up"):
            _leg(glob[glob["kind"] == kind], f"GLOBAL {kind} (Fitch / S&P / Moody's / JCR / CareEdge Global)")
    else:
        print(f"\nGLOBAL: {len(moves)} usable up/down events (< {MIN_GLOBAL}) — not reported.")
    print(f"\nNet of costs: subtract ~{COST*100:.1f}% round trip (more for small caps). Downgrade drift is a "
          f"short: in the cash market it is an avoid / exit rule, not a trade.")


def _study(args) -> dict:
    dom, glob = load_events()
    df = pd.concat([build(dom, "domestic"), build(glob, "global")], ignore_index=True)
    df = exclude_results(df, "event_date", args.exclude_results_window)
    OUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUT, index=False)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("rating_change", _study)
