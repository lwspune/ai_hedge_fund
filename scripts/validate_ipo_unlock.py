"""Validate: is the 6-month pre-IPO lock-in expiry a good entry for a 6-12 month hold?

SEBI locks pre-IPO shareholders for 6 months from the IPO allotment (scanner/ipounlock.py). Events:
NSE company IPOs listed Feb-2020 -> (BSE-only unpriced, REITs / InvITs out), unlock = allotment +
6 months. All windows abnormal vs NIFTY 500, fixed in advance:

  premise   listing close -> unlock: did these stocks fall into month 6?
  react     T-1 -> T+2 around the unlock (the anchor-unlock window, CONCLUSIONS §6)
  TRADE     enter at the T+2 close, hold +125 / +250 sessions (6 / 12 months)
  CONTROL   the same stocks entered the same way at month 3 and at month 9 — is month 6 special,
            or is it ordinary post-IPO drift?
Segments (pre-specified, on the +125 / +250 trade): below vs above the issue price at T-1 ("enter
after the fall"), fell vs rose since listing, board, point-in-time market cap, era, listing pop.
t clustered by unlock week. A split / bonus / consolidation / rights / demerger between listing
and T+400 days drops the event. Judged on medians and hit rates, not means (fat tails).

    python scripts/validate_ipo_unlock.py [--publish]
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize, window_return  # noqa: E402
from scanner.ipounlock import span_abnormal, unlock_events  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pointintime import mcap_bucket_at  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402
from scanner.validation import run  # noqa: E402

BENCH = "^CRSLDX"
START = date(2020, 2, 1)
HOLDS = (125, 250)
ENTRY_LAG = 2
OUT = Path(__file__).resolve().parent.parent / "cache" / "ipo_unlock_results.csv"


def fmt(label: str, xs, clusters=None) -> str:
    s = summarize(list(xs), clusters=None if clusters is None else list(clusters))
    if not s["n"]:
        return f"  {label:<44} n=   0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    tc = f"  t_cl={s['t_cluster']:+5.1f}" if s.get("t_cluster") is not None else ""
    return (f"  {label:<44} n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t={t}{tc}")


def build() -> pd.DataFrame:
    ipos = db.select_all("ipos", {"select": "symbol,company,board,listing_at,boa_date,listing_date,issue_price,listing_close",
                                  "listing_date": f"gte.{START}", "order": "listing_date"})
    close_at_listing = {r["symbol"]: r.get("listing_close") for r in ipos}
    events = unlock_events(ipos, date.today())
    print(f"{len(events)} unlocks passed ({sum(e['allot_guessed'] for e in events)} with a guessed allotment date)",
          flush=True)
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": f"gte.{START}"})
    bench = get_closes(BENCH, "2019-06-01", source="yf")
    out = []
    for k, e in enumerate(events, 1):
        s = None
        try:
            s = get_closes(e["symbol"], e["listing_date"], e["m9"] + timedelta(days=420), source="db")
        except Exception as ex:  # a symbol the store doesn't know
            print(f"  {e['symbol']}: {ex!r}"[:100])
        t = pd.Timestamp(e["unlock"])
        row = {**e, "priced": s is not None and len(s) > 0,
               "blocked": blocking_action(acts, e["symbol"], pd.Timestamp(e["listing_date"]), t + pd.Timedelta(days=400)),
               "week": f"{t.isocalendar().year}-{t.isocalendar().week:02d}", "year": e["unlock"].year}
        if row["priced"] and not row["blocked"]:
            pre = s[s.index < t]
            px = float(pre.iloc[-1]) if len(pre) else None
            lc = close_at_listing.get(e["symbol"])
            row.update({
                "premise": span_abnormal(s, bench, e["listing_date"], e["unlock"]),
                "raw_since_listing": px / float(lc) - 1 if px and lc else None,
                "below_issue": px < e["issue_price"] if px else None,
                "pop": float(lc) / e["issue_price"] - 1 if lc else None,
                "react": window_return(s, bench, e["unlock"], -1, 2),
                "mcap": mcap_bucket_at(e["symbol"], e["unlock"]),
            })
            for h in HOLDS:
                row[f"t{h}"] = forward_abnormal_return(s, bench, e["unlock"], h, entry_lag=ENTRY_LAG)
                row[f"m3_{h}"] = forward_abnormal_return(s, bench, e["m3"], h, entry_lag=ENTRY_LAG)
                row[f"m9_{h}"] = forward_abnormal_return(s, bench, e["m9"], h, entry_lag=ENTRY_LAG)
        out.append(row)
        if k % 200 == 0:
            print(f"  {k}/{len(events)}", flush=True)
    return pd.DataFrame(out)


def _col(d: pd.DataFrame, c: str, label: str) -> str:
    m = d[c].notna() if c in d else pd.Series(False, index=d.index)
    return fmt(label, d.loc[m, c], d.loc[m, "week"]) if m.any() else f"  {label:<44} n=   0"


def report(df: pd.DataFrame) -> None:
    ok = df[df["priced"] & ~df["blocked"]]
    print(f"\nevents {len(df)} | usable {len(ok)} | unpriced {int((~df['priced']).sum())} | "
          f"blocked {int((df['priced'] & df['blocked']).sum())}")
    for board in ("mainboard", "sme"):
        d = ok[ok["board"] == board]
        print(f"\n=== {board}: abnormal vs NIFTY 500 ===")
        print(_col(d, "premise", "premise: listing close -> unlock"))
        print(f"  {'':<44} raw price vs listing close at T-1: median "
              f"{d['raw_since_listing'].median()*100:+.1f}%, below issue {d['below_issue'].mean()*100:.0f}%")
        print(_col(d, "react", "unlock T-1 -> T+2"))
        for h in HOLDS:
            print(_col(d, f"t{h}", f"TRADE enter T+2 after unlock, +{h}"))
            print(_col(d, f"m3_{h}", f"  control: same stocks at month 3, +{h}"))
            print(_col(d, f"m9_{h}", f"  control: same stocks at month 9, +{h}"))
        yr = d["year"]
        cuts = {"below issue price at T-1": d["below_issue"] == True,  # noqa: E712
                "above issue price at T-1": d["below_issue"] == False,  # noqa: E712
                "fell since listing (raw)": d["raw_since_listing"] < 0,
                "rose since listing (raw)": d["raw_since_listing"] >= 0,
                "mcap small / small_mid": d["mcap"].isin(["small", "small_mid"]),
                "mcap mid / large": d["mcap"].isin(["mid", "large"]),
                "unlock 2020-22": yr.between(2020, 2022), "unlock 2023-26": yr.between(2023, 2026),
                "listing pop <= 0": d["pop"] <= 0, "listing pop > 30%": d["pop"] > 0.30}
        print(f"  --- {board} SEGMENTS (pre-specified) — trade +125 | +250 ---")
        for label, m in cuts.items():
            m = m.fillna(False).astype(bool)
            print(_col(d[m], "t125", f"{label} [+125]"))
            print(_col(d[m], "t250", f"{label} [+250]"))
    print("\nA buy signal needs a positive MEDIAN at +125/+250 that beats the month-3 and month-9 entries in "
          "both eras. Costs ~0.3% round trip (more for SME spreads).")


def _study(args) -> dict:
    df = build()
    OUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUT, index=False)
    report(df)
    return {"results": df}


if __name__ == "__main__":
    run("ipo_unlock", _study)
