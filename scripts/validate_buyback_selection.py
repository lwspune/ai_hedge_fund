"""Can high-acceptance buyback tenders be picked BEFORE the record date?

The 2026-09-27 downgrade of `buyback_arb` (thin / watch) said: re-promote only if realized
acceptance shows high-acceptance tenders can be chosen in advance. The one predictor known
before the record date is the offer premium over the last cum-entitlement close (chittorgarh's
entitlement ratio arrives after it). This study uses every tender with a published
small-shareholder response table (`buyback_results.ss_acceptance`, parsed + hand-entered) and
asks, per PRE-REGISTERED premium band (<=5 / 5-10 / 10-20 / 20-40 / >40%):

  * what acceptance the band realized,
  * what a Rs 2 lakh tender in that band actually returned - gross and after tax under today's
    rule (capital gains on the net gain, Finance Act 2026) - entered at the last cum close,
    residual sold 21 sessions after the close,
  * whether the answer holds in both eras (record date before / from Oct-2024) with a
    cluster-robust t (clusters = record month: tenders bunch around results seasons).

Pass criterion (fixed before running): a low band (<=5% or 5-10%) shows a positive after-tax
MEDIAN in both eras and a pooled cluster-robust t >= 2. Otherwise the acceptance model stays
as it is and the verdict stays thin.

    python scripts/validate_buyback_selection.py [--publish]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, run  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402
from scanner.buyback import (arb_return, after_tax_return, estimate_acceptance,  # noqa: E402
                             last_buy_close, premium_band, tax_regime)
from scanner.eventstudy import summarize  # noqa: E402
from scanner.pointintime import mcap_at_symbol  # noqa: E402

RESIDUAL_LAG = 21
SLAB = 0.30
TODAY = "post_apr2026"
ERA_SPLIT = pd.Timestamp("2024-10-01")
PREMIUM_BOUNDS = (-0.5, 1.5)
DB_FROM = pd.Timestamp("2020-02-01")
BANDS = ("<=5%", "5-10%", "10-20%", "20-40%", ">40%")


def load() -> pd.DataFrame:
    from scanner import db
    rows = db.select_all("buyback_results", {
        "select": "ss_acceptance,parsed_by,buybacks(symbol,record_date,close_date,buyback_price,"
                  "entitlement_small,issue_size_cr)",
        "ss_acceptance": "not.is.null"})
    recs = []
    for r in rows:
        b = r.get("buybacks") or {}
        recs.append({"symbol": b.get("symbol"), "record_date": b.get("record_date"),
                     "close_date": b.get("close_date"), "buyback_price": b.get("buyback_price"),
                     "entitlement_small": b.get("entitlement_small"),
                     "issue_size_cr": b.get("issue_size_cr"),
                     "acceptance": float(r["ss_acceptance"]), "parsed_by": r.get("parsed_by")})
    df = pd.DataFrame(recs).dropna(subset=["symbol", "record_date", "close_date", "buyback_price"])
    for c in ("record_date", "close_date"):
        df[c] = pd.to_datetime(df[c])
    for c in ("buyback_price", "entitlement_small", "issue_size_cr"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def get_prices(symbol: str, record_date) -> pd.Series | None:
    t = pd.Timestamp(record_date)
    return get_closes(symbol, t - pd.Timedelta(days=30), t + pd.Timedelta(days=120),
                      source="db" if t >= DB_FROM else "nse")


def price_after(s, d, lag):
    sub = s[s.index > d]
    return float(sub.iloc[lag]) if len(sub) > lag else None


def _line(label, x, clusters=None):
    x = pd.Series(list(x)).dropna()
    if len(x) == 0:
        print(f"  {label:<26} n=0")
        return
    cl = None if clusters is None else list(clusters)
    st = summarize(list(x), clusters=cl)
    tc = st.get("t_cluster")
    extra = f"  t_cl={tc:+5.1f} ({st['n_clusters']} months)" if tc is not None else ""
    print(f"  {label:<26} n={len(x):>3}  mean={x.mean()*100:+6.2f}%  median={x.median()*100:+6.2f}%  "
          f"win={(x > 0).mean()*100:4.0f}%  t={st['t_stat']:+5.1f}{extra}")


def main(args) -> dict | None:
    bb = load()
    print(f"\nTenders with a realized small-shareholder acceptance: {len(bb)} "
          f"({(bb.parsed_by == 'manual').sum()} hand-entered)")
    recs, dropped = [], []
    for _, r in bb.iterrows():
        s = get_prices(r["symbol"], r["record_date"])
        if s is None:
            dropped.append((r["symbol"], "no prices"))
            continue
        cum = last_buy_close(s, r["record_date"])
        post = price_after(s, r["close_date"], RESIDUAL_LAG)
        if not cum or not cum[1] or not post:
            dropped.append((r["symbol"], "no cum/residual close"))
            continue
        entry_date, entry = cum
        bp, acc = float(r["buyback_price"]), float(r["acceptance"])
        prem = bp / entry - 1
        if not PREMIUM_BOUNDS[0] <= prem <= PREMIUM_BOUNDS[1]:
            dropped.append((r["symbol"], f"premium {prem:+.0%}"))
            continue
        ent = float(r["entitlement_small"]) if pd.notna(r["entitlement_small"]) else None
        try:
            mc = mcap_at_symbol(r["symbol"], r["record_date"].date())
        except Exception:
            mc = None
        size = float(r["issue_size_cr"]) if pd.notna(r["issue_size_cr"]) else None
        model_acc = estimate_acceptance(mc, ent, size) if mc else None
        regime_then = tax_regime(r["record_date"], r["close_date"])
        recs.append({
            "symbol": r["symbol"], "record_date": r["record_date"], "entry_date": entry_date,
            "entry": entry, "buyback_price": bp, "premium": prem, "band": premium_band(prem),
            "era": "pre_oct2024" if r["record_date"] < ERA_SPLIT else "from_oct2024",
            "month": r["record_date"].strftime("%Y-%m"),
            "acceptance": acc, "entitlement": ent, "model_acceptance": model_acc,
            "residual_move": post / entry - 1,
            "gross_realized": arb_return(entry, bp, post, acc),
            "gross_floor": arb_return(entry, bp, post, ent) if ent else None,
            "aftertax_realized_now": after_tax_return(entry, bp, post, acc, regime=TODAY),
            "aftertax_realized_then": after_tax_return(entry, bp, post, acc, regime=regime_then, slab=SLAB),
            "aftertax_floor_now": after_tax_return(entry, bp, post, ent, regime=TODAY) if ent else None,
        })
    if dropped:
        print(f"Dropped {len(dropped)}: {dropped}")
    d = exclude_results(pd.DataFrame(recs), "record_date", args.exclude_results_window)
    if d.empty:
        print("No events with usable prices.")
        return None

    rho = d[["premium", "acceptance"]].corr(method="spearman").iloc[0, 1]
    print(f"\n=== BUYBACK SELECTION BY OFFER PREMIUM ({len(d)} tenders, record dates "
          f"{d.record_date.min():%b-%Y} -> {d.record_date.max():%b-%Y}; entry = last cum close, "
          f"residual sold +{RESIDUAL_LAG} sessions after close, Rs 2 lakh) ===")
    print(f"  Spearman(premium, realized acceptance) = {rho:+.2f}")
    e = d.dropna(subset=["model_acceptance"])
    if len(e):
        rho_m = e[["model_acceptance", "acceptance"]].corr(method="spearman").iloc[0, 1]
        print(f"  Current model (flat prior) vs realized: mean abs error "
              f"{(e.model_acceptance - e.acceptance).abs().mean()*100:.0f} pts, Spearman {rho_m:+.2f} (n={len(e)})")

    print(f"\n  {'band':<8}{'n':>4}{'acc med':>9}{'acc mean':>10}{'prem med':>10}{'resid med':>11}"
          f"{'gross med':>11}{'a-tax now med':>15}{'a-tax mean':>12}{'win':>5}{'t_cl':>7}")
    for b in BANDS:
        x = d[d.band == b]
        if x.empty:
            print(f"  {b:<8}{0:>4}")
            continue
        st = summarize(list(x.aftertax_realized_now.dropna()), clusters=list(x.month))
        tc = st.get("t_cluster")
        print(f"  {b:<8}{len(x):>4}{x.acceptance.median()*100:>8.0f}%{x.acceptance.mean()*100:>9.0f}%"
              f"{x.premium.median()*100:>9.1f}%{x.residual_move.median()*100:>10.1f}%"
              f"{x.gross_realized.median()*100:>10.2f}%{x.aftertax_realized_now.median()*100:>14.2f}%"
              f"{x.aftertax_realized_now.mean()*100:>11.2f}%{(x.aftertax_realized_now > 0).mean()*100:>4.0f}%"
              f"{(tc if tc is not None else float('nan')):>7.1f}")

    print("\n  -- after-tax (today's rule) at REALIZED acceptance, by band and era --")
    for era in ("pre_oct2024", "from_oct2024"):
        print(f"  [{era}]")
        for b in BANDS:
            x = d[(d.band == b) & (d.era == era)]
            _line(f"  {b}", x.aftertax_realized_now, x.month)

    print("\n  -- candidate rules vs blind tendering (after-tax, today's rule, realized acceptance) --")
    lo = d[d.band.isin(["<=5%", "5-10%"])]
    hi = d[~d.band.isin(["<=5%", "5-10%"])]
    _line("blind: every tender", d.aftertax_realized_now, d.month)
    _line("rule: premium <= 5%", d[d.band == "<=5%"].aftertax_realized_now, d[d.band == "<=5%"].month)
    _line("rule: premium <= 10%", lo.aftertax_realized_now, lo.month)
    _line("rest: premium > 10%", hi.aftertax_realized_now, hi.month)
    print("  (reference: the same tenders at the ENTITLEMENT floor, the blind case the verdict quotes)")
    _line("blind @ floor", d.aftertax_floor_now, d.month)
    _line("rule <= 10% @ floor", lo.aftertax_floor_now, lo.month)

    print("\n  -- the residual leg alone (post/entry - 1): does the low band just sit at the offer? --")
    for b in BANDS:
        x = d[d.band == b]
        _line(f"  {b}", x.residual_move, x.month)
    return {"results": d}


if __name__ == "__main__":
    run("buyback_arb", main)
