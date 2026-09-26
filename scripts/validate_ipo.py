"""Validate candidate #11: are IPOs worth it, and does the grey-market premium (GMP) help?

Three questions, all fixed in advance (NSE company listings Feb-2020 -> — BSE-only issues have no free
listing price and REITs / InvITs are not company shares — where the bhavcopy gives the
listing-day OPEN; mainboard and SME reported separately):

  Q1 APPLY   one retail application = P(allotment) x listing gain. Retail's reserved slice is
             lottery-allotted one minimum lot per winner when oversubscribed (scanner/ipostudy).
             Gain = sell at the listing open (the usual retail exit) after costs; also at the
             close. Reported per board, per year and per retail-subscription bucket.
  Q2 GMP     the DECISION GMP = the last investorgain quote on/before the issue close (what an
             applicant sees), as % of the issue price. Calibration by GMP bucket; rules "apply only
             if GMP >= X%" vs applying to everything. The last pre-listing GMP only checks how
             close the grey market gets to the listing price.
  Q3 AFTER   not allotted -> buy at the listing close: abnormal vs NIFTY 500 over +5/+20/+60/+250
             sessions, by listing pop, board, era; t clustered by listing week. A split / bonus /
             consolidation / rights / demerger within a year of listing drops the event.

    python scripts/validate_ipo.py [--publish]
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize  # noqa: E402
from scanner.gmp import decision_gmp  # noqa: E402
from scanner.ipostudy import allot_prob, gmp_pct, is_unit_trust, listing_gain, on_nse  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pricestore import first_bar, get_closes  # noqa: E402
from scanner.validation import run  # noqa: E402

BENCH = "^CRSLDX"
START = date(2020, 2, 1)
HORIZONS = (5, 20, 60, 250)
SUB_BUCKETS = [(0, 2, "<= 2x"), (2, 10, "2-10x"), (10, 50, "10-50x"), (50, 1e9, "> 50x")]
GMP_BUCKETS = [(-1e9, 0, "< 0%"), (0, 0.05, "0-5%"), (0.05, 0.15, "5-15%"), (0.15, 0.30, "15-30%"),
               (0.30, 0.60, "30-60%"), (0.60, 1e9, "> 60%")]
GMP_RULES = (0.0, 0.05, 0.10, 0.20, 0.30)
POP_BUCKETS = [(-1e9, 0, "listed below issue"), (0, 0.2, "pop 0-20%"), (0.2, 0.5, "pop 20-50%"),
               (0.5, 1e9, "pop > 50%")]
OUT = Path(__file__).resolve().parent.parent / "cache" / "ipo_results.csv"


def pct(x) -> str:
    return "   n/a" if x is None or pd.isna(x) else f"{x*100:+6.1f}%"


def fmt(label: str, xs, clusters=None) -> str:
    s = summarize(list(xs), clusters=None if clusters is None else list(clusters))
    if not s["n"]:
        return f"  {label:<40} n=   0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    tc = f"  t_cl={s['t_cluster']:+5.1f}" if s.get("t_cluster") is not None else ""
    return (f"  {label:<40} n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}{tc}")


def build() -> pd.DataFrame:
    ipos = db.select_all("ipos", {"select": "*", "listing_date": f"gte.{START}", "order": "listing_date"})
    listed = [r for r in ipos if r["listing_date"] <= date.today().isoformat()]
    ipos = [r for r in listed if on_nse(r.get("listing_at")) and not is_unit_trust(r.get("company"))]
    print(f"scope: {len(ipos)} NSE company IPOs; excluded {sum(not on_nse(r.get('listing_at')) for r in listed)} "
          f"BSE-only (no free listing price), {sum(is_unit_trust(r.get('company')) for r in listed)} REIT / InvIT")
    series: dict = {}
    for g in db.select_all("ipo_gmp", {"select": "chittorgarh_id,gmp_date,gmp", "order": "gmp_date"}):
        series.setdefault(g["chittorgarh_id"], []).append(
            {"gmp_date": date.fromisoformat(g["gmp_date"]), "gmp": float(g["gmp"])})
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": f"gte.{START}"})
    bench = get_closes(BENCH, "2019-06-01", source="yf")
    print(f"{len(ipos)} IPOs listed since {START}", flush=True)
    out = []
    for k, r in enumerate(ipos, 1):
        issue, lst = float(r["issue_price"]), date.fromisoformat(r["listing_date"])
        bar = first_bar(r["symbol"], lst, max_days=5)
        close_ser = None
        try:
            close_ser = get_closes(r["symbol"], lst, lst + timedelta(days=400), source="db")
        except Exception as ex:  # an unknown symbol in the store
            print(f"  {r['symbol']}: {ex!r}"[:100])
        s = series.get(r["chittorgarh_id"], [])
        close_day = date.fromisoformat(r["issue_close"]) if r.get("issue_close") else None
        dec = decision_gmp(s, close_day) if close_day else None
        final = decision_gmp(s, lst - timedelta(days=1))
        p = allot_prob(r["board"], r.get("retail_shares_offered"), r.get("lot_size"), r.get("applications"),
                       float(r["sub_retail"]) if r.get("sub_retail") else None)
        g_open = listing_gain(issue, bar["open"] if bar else None)
        row = {
            "symbol": r["symbol"], "board": r["board"], "listing_date": lst, "year": lst.year, "issue": issue,
            "sub_retail": float(r["sub_retail"]) if r.get("sub_retail") else None,
            "sub_qib": float(r["sub_qib"]) if r.get("sub_qib") else None, "p_allot": p,
            "app_rs": issue * r["lot_size"] if r.get("lot_size") else None,
            "open": bar["open"] if bar else None, "close": bar["close"] if bar else None,
            "gain_open": g_open, "gain_close": listing_gain(issue, bar["close"] if bar else None),
            "ev_open": p * g_open if p is not None and g_open is not None else None,
            "gmp_decision": gmp_pct(dec, issue), "gmp_final": gmp_pct(final, issue),
            "week": f"{pd.Timestamp(lst).isocalendar().year}-{pd.Timestamp(lst).isocalendar().week:02d}",
            "blocked": blocking_action(acts, r["symbol"], pd.Timestamp(lst), pd.Timestamp(lst) + pd.Timedelta(days=380)),
        }
        if close_ser is not None and len(close_ser) and not row["blocked"]:
            for h in HORIZONS:
                row[f"h{h}"] = forward_abnormal_return(close_ser, bench, lst, h, entry_lag=0)
        out.append(row)
        if k % 200 == 0:
            print(f"  {k}/{len(ipos)}", flush=True)
    return pd.DataFrame(out)


def _bucket(x, buckets):
    if x is None or pd.isna(x):
        return None
    return next((lab for lo, hi, lab in buckets if lo <= x < hi), None)


def _apply_table(d: pd.DataFrame, by: str, order=None) -> None:
    print(f"  {by:<16} {'n':>5} {'gain@open med':>13} {'mean':>7} {'<issue':>7} {'P(allot) med':>12} "
          f"{'EV/app mean':>11} {'EV/app Rs':>9}")
    groups = d.groupby(by, sort=order is None)
    keys = order if order is not None else [k for k, _ in groups]
    for key in keys:
        if key not in groups.groups:
            continue
        g = groups.get_group(key)
        rs = (g["ev_open"] * g["app_rs"]).mean()
        print(f"  {str(key):<16} {len(g):>5} {pct(g['gain_open'].median()):>13} {pct(g['gain_open'].mean()):>7} "
              f"{(g['gain_open'] < 0).mean()*100:6.0f}% {pct(g['p_allot'].median()):>12} "
              f"{pct(g['ev_open'].mean()):>11} {rs:9.0f}")


def report(df: pd.DataFrame) -> None:
    ok = df[df["gain_open"].notna()]
    print(f"\nIPOs {len(df)} | with a listing open {len(ok)} | with subscription {int(ok['p_allot'].notna().sum())} "
          f"| with a decision GMP {int(ok['gmp_decision'].notna().sum())}")
    for board in ("mainboard", "sme"):
        d = ok[(ok["board"] == board) & ok["ev_open"].notna()]
        print(f"\n=== Q1 APPLY — {board} (per application, sell at the listing open; EV = P(allot) x gain) ===")
        _apply_table(d.assign(all="all"), "all")
        _apply_table(d, "year")
        _apply_table(d.assign(sub=d["sub_retail"].map(lambda x: _bucket(x, SUB_BUCKETS))), "sub",
                     [b[2] for b in SUB_BUCKETS])
        print(f"  sell at the close instead: gain median {pct(d['gain_close'].median())}, mean {pct(d['gain_close'].mean())}")

    g = ok[ok["gmp_decision"].notna()]
    for board in ("mainboard", "sme"):
        d = g[(g["board"] == board) & g["ev_open"].notna()]
        if len(d) < 20:
            print(f"\n=== Q2 GMP — {board}: {len(d)} IPOs with a decision GMP (< 20), skipped ===")
            continue
        rho = d[["gmp_decision", "gain_open"]].corr(method="spearman").iloc[0, 1]
        print(f"\n=== Q2 GMP — {board} (decision GMP = last quote by issue close; Spearman vs gain {rho:+.2f}) ===")
        _apply_table(d.assign(gmp=d["gmp_decision"].map(lambda x: _bucket(x, GMP_BUCKETS))), "gmp",
                     [b[2] for b in GMP_BUCKETS])
        base = d["ev_open"].mean()
        print(f"  rule: apply only if decision GMP >= X  (apply-all EV/app {pct(base)}, {len(d)} apps)")
        for x in GMP_RULES:
            k = d[d["gmp_decision"] >= x]
            skipped = d[d["gmp_decision"] < x]
            print(f"    X={x*100:4.0f}%  apps {len(k):>4}  EV/app {pct(k['ev_open'].mean())}  listed below issue "
                  f"{(k['gain_open'] < 0).mean()*100:3.0f}%  | skipped {len(skipped):>4}, their EV {pct(skipped['ev_open'].mean())}")
        f = d[d["gmp_final"].notna()]
        err = (f["open"] / f["issue"] - 1) - f["gmp_final"]
        print(f"  last pre-listing GMP vs the listing open: median error {pct(err.median())}, "
              f"|error| median {pct(err.abs().median())} (n={len(f)})")

    post = df[~df["blocked"] & df["gain_close"].notna()]
    for board in ("mainboard", "sme"):
        d = post[post["board"] == board]
        print(f"\n=== Q3 AFTER — {board}: buy at the listing close, abnormal vs NIFTY 500 ===")
        for h in HORIZONS:
            m = d[f"h{h}"].notna()
            print(fmt(f"+{h} sessions", d.loc[m, f"h{h}"], d.loc[m, "week"]))
        pop = d["gain_close"].map(lambda x: _bucket(x, POP_BUCKETS))
        for lab in [b[2] for b in POP_BUCKETS]:
            m = (pop == lab) & d["h60"].notna()
            print(fmt(f"{lab} [+60]", d.loc[m, "h60"], d.loc[m, "week"]))
        for lo, hi in ((2020, 2022), (2023, 2026)):
            m = d["year"].between(lo, hi) & d["h60"].notna()
            print(fmt(f"era {lo}-{hi} [+60]", d.loc[m, "h60"], d.loc[m, "week"]))
    print("\nNotes: EV/app is per application of one minimum lot (Rs column = mean rupees per application). "
          "Application money is only blocked (ASBA) for ~a week; one application per PAN.")


def _study(args) -> dict:
    df = build()
    OUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUT, index=False)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("ipo_listing", _study)
