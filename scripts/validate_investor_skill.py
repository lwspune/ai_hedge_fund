"""Validate: do some investors who take >= 1% stakes have skill a follower can use (6-24 months)?

Events: an investor's first appearance >= 1% in a company's SEBI shareholding pattern (the named
public-holder table; scanner/holders.py), Sep-2021 -> today. Kinds: individual (> Rs 2 lakh / NRI),
AIF, mutual fund (fund house), FPI, insurance, public bodies corporate. Promoters, directors, KMP,
trusts, custodians, FDI, pension funds, passive funds and IEPF are excluded.

Entry: the close of the first session after the filing's broadcast date (point-in-time). Returns:
cloud closes, split / bonus / consolidation-adjusted (`pricestore.adjust_for_actions`, guarded), in
excess of NIFTY 500 at +125 / +250 / +500 sessions (6 / 12 / 24 months). A demerger inside the window
drops the event; a stock that stops trading is scored to its last close (never dropped — that would
flatter the investors whose picks were delisted). Market cap at entry = total shares from the same
filing x the unadjusted close (no lookahead).

Pre-registered (2026-09-26, before the data was loaded):
  A. all entrants by kind / era / market cap — does a >= 1% entry carry information at all?
  B. persistence: per-investor median +125 excess, entries 2022-23 vs 2024-25 (>= 3 in each):
     Spearman rho across investors.
  C. walk-forward (the test): each half-year from 2023-H1, rank investors on the entries whose +125
     outcome was known before the half began (>= 3 scored), follow the top 20% in that half.
     Compared with all entrants and the bottom 20% in the same halves. Unit = unique stock-quarter
     per group (a follower buys once). t clustered by entry quarter (overlapping windows).
  D. robustness: rank on +250 instead of +125.
PASS (all of): top-group +250 median excess > 0 and >= 3 pp above all entrants; top - all > 0 in
both test eras (2023-24, 2025-26); top +250 mean t_cl >= 2; persistence rho > 0 with t >= 2.
Otherwise the verdict is null (or premium, if all entrants beat NIFTY 500 only through size).

    python scripts/validate_investor_skill.py [--publish]
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.buyback import mcap_bucket  # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize  # noqa: E402
from scanner.holders import entry_events, load_symbol, persistence, walk_forward  # noqa: E402
from scanner.pricestore import adjust_for_actions, get_closes  # noqa: E402
from scanner.validation import run  # noqa: E402

BENCH = "^CRSLDX"
HORIZONS = (125, 250, 500)
PRICE_FROM = "2021-06-01"
MIN_N, FRAC = 3, 0.2
PASS_EDGE = 0.03
OUT = Path(__file__).resolve().parent.parent / "cache" / "investor_skill_results.csv"


def half_years(first: str = "2023-01-01") -> list[tuple[str, str]]:
    out, s = [], pd.Timestamp(first)
    while s <= pd.Timestamp(date.today()):
        e = s + pd.DateOffset(months=6)
        out.append((s.date().isoformat(), e.date().isoformat()))
        s = e
    return out


def load_holders() -> pd.DataFrame:
    rows = db.select_all("companies", {"select": "symbol", "order": "symbol",
                                       "or": "(status.eq.listed,delisted_on.gte.2021-06-30)"})
    frames = []
    for k, r in enumerate(rows, 1):
        d = load_symbol(r["symbol"])
        if d is not None and len(d):
            frames.append(d)
        if k % 500 == 0:
            print(f"  holders: {k}/{len(rows)} symbols read", flush=True)
    print(f"holders: {len(frames)} of {len(rows)} symbols have filings", flush=True)
    return pd.concat(frames, ignore_index=True)


def _vanished_return(s: pd.Series, bench: pd.Series, t0) -> float | None:
    """Excess return from entry (first session after t0) to the stock's last close."""
    i = s.index.searchsorted(pd.Timestamp(t0)) + 1
    if i >= len(s) - 1:
        return None
    a, b = s.index[i], s.index[-1]
    ba, bb = bench.asof(a), bench.asof(b)
    return float(s.iloc[-1] / s.iloc[i] - 1 - (bb / ba - 1))


def price(ev: pd.DataFrame) -> pd.DataFrame:
    bench = get_closes(BENCH, PRICE_FROM, source="db")
    last_bench = bench.index.max()
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date,details",
                                              "event_type": "in.(split,bonus,consolidation,demerger)",
                                              "event_date": f"gte.{PRICE_FROM}"})
    by_sym: dict[str, list] = {}
    for a in acts:
        by_sym.setdefault(a["symbol"], []).append(a)
    rows = []
    syms = sorted(ev["symbol"].unique())
    for k, sym in enumerate(syms, 1):
        try:
            raw = get_closes(sym, PRICE_FROM, None, source="db")
        except Exception as ex:  # a symbol the store doesn't know
            print(f"  {sym}: {ex!r}"[:100])
            raw = None
        adj = adjust_for_actions(raw, by_sym.get(sym, [])) if raw is not None else None
        stopped = raw is not None and raw.index.max() < last_bench - pd.Timedelta(days=15)
        demergers = [pd.Timestamp(a["event_date"]) for a in by_sym.get(sym, []) if a["event_type"] == "demerger"]
        for _, e in ev[ev["symbol"] == sym].iterrows():
            row = e.to_dict()
            row["status"] = ("unpriced" if raw is None else "bad_adjust" if adj is None else "ok")
            if row["status"] == "ok":
                t0 = e["entry_date"]
                px = raw[raw.index > t0]
                if len(px):
                    total = e["shares"] / (e["pct"] / 100) if e["pct"] else None
                    row["mcap_cr"] = total * float(px.iloc[0]) / 1e7 if total else None
                for h in HORIZONS:
                    end = t0 + pd.Timedelta(days=int(h * 1.5) + 10)
                    if any(t0 < d <= end for d in demergers):
                        row["status"] = "demerger"
                        break
                    r = forward_abnormal_return(adj, bench, t0, h, entry_lag=1)
                    pos = adj.index.searchsorted(t0) + 1 + h
                    if r is None and stopped:
                        r = _vanished_return(adj, bench, t0)
                        row["vanished"] = True
                    row[f"x{h}"] = r
                    row[f"exit{h}"] = adj.index[pos] if r is not None and pos < len(adj) else (
                        adj.index[-1] if r is not None else None)
            rows.append(row)
        if k % 200 == 0:
            print(f"  prices: {k}/{len(syms)} symbols", flush=True)
    df = pd.DataFrame(rows)
    df["mcap"] = [mcap_bucket(v) if pd.notna(v) else "unknown" for v in df.get("mcap_cr", pd.Series(index=df.index))]
    df["cohort"] = df["quarter_end"]
    df["year"] = pd.to_datetime(df["entry_date"]).dt.year
    return df


def fmt(label: str, d: pd.DataFrame, col: str) -> str:
    d = d[d[col].notna()] if col in d else d.iloc[0:0]
    s = summarize(list(d[col]), clusters=list(d["cohort"]))
    if not s["n"]:
        return f"  {label:<46} n=   0"
    tc = f"{s['t_cluster']:+5.1f}" if s.get("t_cluster") is not None else "  n/a"
    return (f"  {label:<46} n={s['n']:>5}  mean={s['mean']*100:+6.1f}%  median={s['median']*100:+6.1f}%  "
            f"up={s['pct_positive']*100:3.0f}%  t_cl={tc}")


def _unique(d: pd.DataFrame) -> pd.DataFrame:
    """One row per stock-quarter: a follower buys a stock once however many investors entered it."""
    return d.drop_duplicates(["symbol", "quarter_end"])


def report(df: pd.DataFrame, holders: pd.DataFrame) -> dict:
    ok = df[df["status"] == "ok"]
    n_filings = int((holders["axis"] == "_filing").sum())
    print(f"\n{n_filings} filings, {holders['symbol'].nunique()} companies, "
          f"{holders['quarter_end'].min()} -> {holders['quarter_end'].max()}")
    print(f"entries {len(df)} | priced {len(ok)} | unpriced {(df['status'] == 'unpriced').sum()} | "
          f"bad adjustment {(df['status'] == 'bad_adjust').sum()} | demerger {(df['status'] == 'demerger').sum()} | "
          f"stopped trading (scored to last close) {int(ok.get('vanished', pd.Series(dtype=bool)).fillna(False).sum())}")

    print("\n=== A. all entrants (unique stock-quarter), excess vs NIFTY 500 ===")
    u = _unique(ok)
    for h in HORIZONS:
        print(fmt(f"all entrants +{h}", u, f"x{h}"))
    for kind in ("individual", "aif", "mf", "fpi", "insurance", "corporate"):
        print(fmt(f"kind={kind} +250", _unique(ok[ok["kind"] == kind]), "x250"))
    for y in sorted(ok["year"].unique()):
        print(fmt(f"entry year {y} +250", _unique(ok[ok["year"] == y]), "x250"))
    for b in ("small", "small_mid", "mid", "large", "unknown"):
        print(fmt(f"mcap {b} +250", _unique(ok[ok["mcap"] == b]), "x250"))

    print("\n=== B. persistence: investor median +125, entries 2022-23 vs 2024-25 (>= 3 each) ===")
    a = ok[ok["year"].between(2022, 2023)].groupby("investor")["x125"].agg(["count", "median"])
    b = ok[ok["year"].between(2024, 2025)].groupby("investor")["x125"].agg(["count", "median"])
    rho, n = persistence(a[a["count"] >= MIN_N]["median"], b[b["count"] >= MIN_N]["median"])
    t_rho = rho * np.sqrt((n - 2) / (1 - rho ** 2)) if rho is not None and n > 2 and abs(rho) < 1 else None
    print(f"  Spearman rho = {rho if rho is None else round(rho, 3)} over {n} investors"
          + (f"  (t = {t_rho:+.1f})" if t_rho is not None else ""))

    verdict = {}
    for rank_h in (125, 250):
        tag = "C" if rank_h == 125 else "D"
        print(f"\n=== {tag}. walk-forward: rank on +{rank_h} known before each half-year, top/bottom "
              f"{int(FRAC*100)}%, min {MIN_N} ===")
        wf = walk_forward(ok, f"x{rank_h}", f"exit{rank_h}", half_years(), min_n=MIN_N, frac=FRAC)
        ranked_per_fold = wf.groupby("fold")["group"].apply(lambda g: (g != "unranked").sum())
        print(f"  test entries {len(wf)} across {wf['fold'].nunique()} half-years; ranked entries per half: "
              + ", ".join(f"{k[:7]}={v}" for k, v in ranked_per_fold.items()))
        for h in HORIZONS:
            print(fmt(f"TOP investors' entries +{h}", _unique(wf[wf["group"] == "top"]), f"x{h}"))
            print(fmt(f"  all entrants, same halves +{h}", _unique(wf), f"x{h}"))
            print(fmt(f"  bottom investors +{h}", _unique(wf[wf["group"] == "bottom"]), f"x{h}"))
            print(fmt(f"  mid investors +{h}", _unique(wf[wf["group"] == "mid"]), f"x{h}"))
        eras = {"2023-24": wf["fold"] < "2025-01-01", "2025-26": wf["fold"] >= "2025-01-01"}
        diffs = {}
        for era, m in eras.items():
            top = _unique(wf[m & (wf["group"] == "top")])["x250"].dropna()
            allv = _unique(wf[m])["x250"].dropna()
            diffs[era] = (top.median() - allv.median()) if len(top) and len(allv) else None
            print(fmt(f"era {era}: TOP +250", _unique(wf[m & (wf["group"] == "top")]), "x250"))
            print(fmt(f"era {era}: all +250", _unique(wf[m]), "x250"))
        for kind in ("individual", "aif", "mf", "fpi", "corporate"):
            print(fmt(f"TOP, kind={kind} +250", _unique(wf[(wf["group"] == "top") & (wf["kind"] == kind)]), "x250"))
        for bkt in ("small", "small_mid", "mid", "large"):
            print(fmt(f"TOP, mcap {bkt} +250", _unique(wf[(wf["group"] == "top") & (wf["mcap"] == bkt)]), "x250"))
            print(fmt(f"  all, mcap {bkt} +250", _unique(wf[wf["mcap"] == bkt]), "x250"))
        topu = _unique(wf[wf["group"] == "top"])["x250"].dropna()
        allu = _unique(wf)["x250"].dropna()
        st = summarize(list(_unique(wf[wf["group"] == "top"]).dropna(subset=["x250"])["x250"]),
                       clusters=list(_unique(wf[wf["group"] == "top"]).dropna(subset=["x250"])["cohort"]))
        verdict[rank_h] = {
            "top_median": topu.median() if len(topu) else None, "all_median": allu.median() if len(allu) else None,
            "era_diffs": diffs, "t_cl": st.get("t_cluster"), "n_top": len(topu)}
        if rank_h == 125:
            latest = wf["fold"].max()
            train = ok[pd.to_datetime(ok["exit125"]).lt(pd.Timestamp(date.today())) & ok["x125"].notna()]
            ranks = train.groupby("investor").agg(n=("x125", "count"), score=("x125", "median"),
                                                  name=("name", "last"), kind=("kind", "last"))
            ranks = ranks[ranks["n"] >= MIN_N].sort_values("score", ascending=False)
            print(f"\n  investors ranked today (all realised +125 outcomes; latest fold {latest}): {len(ranks)}")
            print("  top 15 by median +125 excess:")
            for inv, r in ranks.head(15).iterrows():
                print(f"    {inv[:52]:<52} n={int(r['n']):>3}  median={r['score']*100:+6.1f}%  e.g. {r['name'][:30]}")
            verdict["ranks"] = ranks

    v = verdict[125]
    passed = (v["top_median"] is not None and v["top_median"] > 0
              and v["all_median"] is not None and v["top_median"] - v["all_median"] >= PASS_EDGE
              and all(d is not None and d > 0 for d in v["era_diffs"].values())
              and v["t_cl"] is not None and v["t_cl"] >= 2
              and rho is not None and rho > 0 and t_rho is not None and t_rho >= 2)
    print("\n=== PRE-REGISTERED RULE (rank +125, judge +250) ===")
    print(f"  top median {v['top_median']}, all median {v['all_median']}, era diffs {v['era_diffs']}, "
          f"t_cl {v['t_cl']}, persistence rho {rho} (t {t_rho})")
    print(f"  -> {'PASS' if passed else 'FAIL'}")
    return verdict


def _study(args) -> dict:
    holders = load_holders()
    ev = entry_events(holders)
    print(f"{len(ev)} entries by {ev['investor'].nunique()} investors", flush=True)
    df = price(ev)
    OUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUT, index=False)
    verdict = report(df, holders)
    frames = {"results": df}
    if "ranks" in verdict:
        frames["investor_ranks"] = verdict["ranks"].reset_index()
    return frames


if __name__ == "__main__":
    run("investor_skill", _study)
