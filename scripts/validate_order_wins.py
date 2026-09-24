"""Validate candidate signal #9: follow disclosed order wins (SEBI Reg 30 'Bagging/Receiving of
orders/contracts', NSE filings 2021->).

Events: order filings clustered per stock (5-day gap), dated at the first disclosure; value =
extracted order value (company_kpis, rule_v1) where disclosed. Size = value / revenue of the
last fiscal year already public (no look-ahead).
Measured (fixed in advance), abnormal vs NIFTY 500: announcement reaction T-1 -> T0 (not
tradable), pre-announcement T-6 -> T-1 (leakage), and the FOLLOWER's return entered the day
after disclosure: +1 / +5 / +20 trading days. CONTROL: same stock, 60 trading days away, no
order filing within 10 trading days. Segments: size bucket (<5% / 5-25% / >=25% of revenue /
undisclosed), board (SME vs mainboard), era (2021-22 / 2023-24 / 2025-26).
Prices: unadjusted NSE closes; split/bonus/rights/consolidation/demerger near an event -> dropped.

    python scripts/validate_order_wins.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, parse_args  # noqa: E402
from scanner import db  # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize, window_return  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.orderwins import cluster_orders, revenue_before, size_bucket  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402

BENCH = "^CRSLDX"
HORIZONS = (1, 5, 20)
COST = 0.003
CONTROL_SHIFT, CONTROL_GAP = 60, 10
ORDER_CAT = "Bagging/Receiving of orders/contracts"
OUT = Path(__file__).resolve().parent.parent / "cache" / "order_wins_results.csv"
SME_SERIES = {"SM", "ST", "SZ"}


def fmt(label: str, xs) -> str:
    s = summarize(list(xs))
    if not s["n"]:
        return f"  {label:<40} n=   0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    return (f"  {label:<40} n={s['n']:>5}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}")


def build() -> pd.DataFrame:
    filings = db.select_all("filings", {"select": "seq_id,symbol,disclosed_at",
                                        "category": f'eq.{ORDER_CAT}', "disclosed_at": "gte.2021-01-01"})
    vals = {k["seq_id"]: k["value_cr"] for k in db.select_all(
        "company_kpis", {"select": "seq_id,value_cr", "kpi": "eq.order_win_value"})}
    rows = [{"symbol": f["symbol"], "disclosed_at": f["disclosed_at"], "value_cr": vals.get(f["seq_id"])}
            for f in filings]
    cutoff = (date.today() - timedelta(days=40)).isoformat()   # room for +20 trading days
    events = [e for e in cluster_orders(rows) if e["date"] <= cutoff]
    hist = {r["symbol"]: (r.get("history") or {}).get("annual") or []
            for r in db.select_all("company_snapshot", {"select": "symbol,history"})}
    series = {c["symbol"]: c["series"] for c in db.select_all("companies", {"select": "symbol,series"})}
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": "gte.2020-10-01"})
    bench = get_closes(BENCH, "2020-06-01", source="yf")
    cal = bench.index
    order_days: dict[str, list[pd.Timestamp]] = {}
    for f in filings:
        order_days.setdefault(f["symbol"], []).append(pd.Timestamp(f["disclosed_at"][:10]))
    print(f"{len(filings)} order filings ({sum(v is not None for v in vals.values())} with values) "
          f"-> {len(events)} events across {len({e['symbol'] for e in events})} stocks", flush=True)

    span: dict[str, list[str]] = {}
    for e in events:
        span.setdefault(e["symbol"], []).append(e["date"])
    prices = {}
    for k, sym in enumerate(sorted(span), 1):
        lo = (pd.Timestamp(min(span[sym])) - pd.Timedelta(days=130)).date()
        hi = (pd.Timestamp(max(span[sym])) + pd.Timedelta(days=130)).date()
        try:
            prices[sym] = get_closes(sym, lo, hi, source="nse")
        except Exception:  # nselib raises on renamed / unknown symbols
            prices[sym] = None
        if k % 100 == 0:
            print(f"  priced {k}/{len(span)}", flush=True)

    out = []
    for e in events:
        s, t0 = prices.get(e["symbol"]), pd.Timestamp(e["date"])
        rev = revenue_before(hist.get(e["symbol"], []), e["date"])
        ratio = e["value_cr"] / rev if e["value_cr"] is not None and rev else None
        row = {**e, "revenue_cr": rev, "size_ratio": ratio, "size": size_bucket(ratio),
               "board": "sme" if series.get(e["symbol"]) in SME_SERIES else "main",
               "priced": s is not None,
               "blocked": blocking_action(acts, e["symbol"], t0 - pd.Timedelta(days=15), t0 + pd.Timedelta(days=45))}
        if s is not None and not row["blocked"]:
            row["reaction"] = window_return(s, bench, t0, -1, 0)
            row["pre"] = window_return(s, bench, t0, -6, -1)
            for h in HORIZONS:
                row[f"h{h}"] = forward_abnormal_return(s, bench, t0, h, entry_lag=1)
            p = cal.searchsorted(t0)
            for tag, shift in (("ctl_a", CONTROL_SHIFT), ("ctl_b", -CONTROL_SHIFT)):
                q = p + shift
                if not 0 <= q < len(cal) - 25:
                    continue
                cd = cal[q]
                near = any(abs(cal.searchsorted(d) - q) < CONTROL_GAP for d in order_days.get(e["symbol"], []))
                if near or blocking_action(acts, e["symbol"], cd - pd.Timedelta(days=15), cd + pd.Timedelta(days=45)):
                    continue
                for h in HORIZONS:
                    row[f"{tag}_h{h}"] = forward_abnormal_return(s, bench, cd, h, entry_lag=1)
        out.append(row)
    df = pd.DataFrame(out)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    ok = df[df["priced"] & ~df["blocked"] & df["h5"].notna()]
    print(f"\nevents {len(df)} | usable {len(ok)} | unpriced {int((~df['priced']).sum())} | "
          f"blocked {int((df['priced'] & df['blocked']).sum())}")
    print("\n=== ALL order wins (abnormal vs NIFTY 500) vs same-stock CONTROL ===")
    print(fmt("announcement reaction T-1 -> T0", ok["reaction"].dropna()))
    print(fmt("pre-announcement T-6 -> T-1", ok["pre"].dropna()))
    for h in HORIZONS:
        ctl = pd.concat([ok.get(f"ctl_a_h{h}", pd.Series(dtype=float)),
                         ok.get(f"ctl_b_h{h}", pd.Series(dtype=float))]).dropna()
        print(fmt(f"follower +{h}d", ok[f"h{h}"].dropna()))
        print(fmt(f"control  +{h}d", ctl))

    yr = pd.to_datetime(ok["date"]).dt.year
    cuts = {**{f"size {b}": ok["size"] == b for b in (">=25%", "5-25%", "<5%", "unknown")},
            "board = SME": ok["board"] == "sme", "board = mainboard": ok["board"] == "main",
            "era 2021-22": yr.between(2021, 2022), "era 2023-24": yr.between(2023, 2024),
            "era 2025-26": yr.between(2025, 2026)}
    print("\n=== SEGMENTS (pre-specified): reaction | follower +5d | +20d ===")
    for label, m in cuts.items():
        print(fmt(f"{label} [reaction]", ok.loc[m, "reaction"].dropna()))
        print(fmt(f"{label} [+5d]", ok.loc[m, "h5"].dropna()))
        print(fmt(f"{label} [+20d]", ok.loc[m, "h20"].dropna()))
    big = ok["size"] == ">=25%"
    print("\n=== size >=25% by era (+20d) ===")
    for lo, hi in ((2021, 2022), (2023, 2024), (2025, 2026)):
        print(fmt(f"size >=25% {lo}-{hi}", ok.loc[big & yr.between(lo, hi), "h20"].dropna()))
    print(f"\nNet of costs: subtract ~{COST*100:.1f}% per round trip.")


if __name__ == "__main__":
    args = parse_args()
    report(exclude_results(build(), "date", args.exclude_results_window))
