"""Report what realized tender outcomes suggest for the acceptance prior.

    python -m scanner.calibrate

Reads every realized small-shareholder acceptance (published response tables in
`buyback_results` + your own logged outcomes) and prints two comparisons:
  * by offer premium over the last cum-entitlement close vs `PREMIUM_BAND_ACCEPTANCE` — the
    live prior since 2026-09-30;
  * by market cap AS OF the record date (scanner.pointintime — no lookahead) vs the flat
    fallback prior, used only when a premium is unavailable.
It does NOT mutate the constants — update them by hand when a band drifts as n grows.
"""
from __future__ import annotations

from scanner import db
from scanner.buyback import (PREMIUM_BAND_ACCEPTANCE, calibrate_by_premium, calibrate_from_outcomes,
                             mcap_bucket, _MCAP_ACCEPTANCE_PRIOR)

_LABELS = ["small", "small_mid", "mid", "large"]


def main():
    try:
        outcomes = db.select("outcomes", {
            "select": "realized_acceptance,tenders(buybacks(symbol,record_date,buyback_price))",
        })
        # every tender's published response table (scripts/refresh_buyback_results.py) — the
        # market-wide sample; your own outcomes are a subset of the same numbers
        results = db.select_all("buyback_results", {
            "select": "ss_acceptance,buybacks(symbol,record_date,buyback_price)", "ss_acceptance": "not.is.null"})
    except Exception as e:
        print(f"[error] {e}")
        return

    from datetime import date
    from scanner.pointintime import mcap_at_symbol
    pairs = [(((o.get("tenders") or {}).get("buybacks")) or {}, o.get("realized_acceptance")) for o in outcomes]
    pairs += [(r.get("buybacks") or {}, r.get("ss_acceptance")) for r in results]
    recs = []
    for bb, ra in pairs:
        sym, rd = bb.get("symbol"), bb.get("record_date")
        if ra is None or not sym or not rd:
            continue
        try:  # market cap AS OF the record date — today's cap would be lookahead (WP5)
            mc = mcap_at_symbol(sym, date.fromisoformat(rd))
        except Exception:
            mc = None
        recs.append({"symbol": sym, "record_date": rd, "market_cap_cr": mc, "realized_acceptance": float(ra)})

    cal = calibrate_from_outcomes(recs)
    print(f"Tenders with realized small-shareholder acceptance: {len(recs)} "
          f"({len(results)} published results, {len(outcomes)} own outcomes; "
          f"{sum(r['market_cap_cr'] is None for r in recs)} without an as-of market cap)")
    if not cal:
        print("Nothing to calibrate yet — run scripts/refresh_buyback_results.py --all, or log "
              "tenders+outcomes via `scanner.track`, then re-run. The prior stays the heuristic until then.")
        return

    prior = dict(zip(_LABELS, [a for _, a in _MCAP_ACCEPTANCE_PRIOR]))
    print(f"\nBy market cap (fallback prior only; no gradient found 2026-09-24):")
    print(f"{'bucket':<12}{'n':>4}{'realized~':>11}{'prior':>9}")
    for b, v in cal.items():
        print(f"{b:<12}{v['n']:>4}{v['acceptance']*100:>10.1f}%{prior.get(b, 0)*100:>8.1f}%")

    # the live prior: median acceptance by offer premium over the last cum-entitlement close
    band_recs = []
    for bb, ra in pairs:
        if ra is None or not bb.get("symbol") or not bb.get("record_date") or not bb.get("buyback_price"):
            continue
        band_recs.append({"premium": _premium_at_cum(bb), "realized_acceptance": float(ra)})
    by_band = calibrate_by_premium(band_recs)
    print(f"\nBy offer premium over the last cum close (the live prior; "
          f"{sum(r['premium'] is None for r in band_recs)} without prices):")
    print(f"{'band':<12}{'n':>4}{'realized~':>11}{'prior':>9}")
    for b in PREMIUM_BAND_ACCEPTANCE:
        v = by_band.get(b)
        got = f"{v['n']:>4}{v['acceptance']*100:>10.1f}%" if v else f"{0:>4}{'-':>11}"
        print(f"{b:<12}{got}{PREMIUM_BAND_ACCEPTANCE[b]*100:>8.1f}%")
    print("\nIf a band's realized median drifts from the prior as n grows, update "
          "PREMIUM_BAND_ACCEPTANCE (scanner/buyback.py) and re-run validate_buyback_selection.py.")


def _premium_at_cum(bb: dict):
    """Offer premium over the last cum-entitlement close (unadjusted), or None without prices."""
    import pandas as pd
    from scanner.buyback import last_buy_close
    from scanner.pricestore import get_closes
    try:
        rd = pd.Timestamp(bb["record_date"])
        s = get_closes(bb["symbol"], rd - pd.Timedelta(days=30), rd,
                       source="db" if rd >= pd.Timestamp("2020-02-01") else "nse")
        cum = last_buy_close(s, rd)
    except Exception:
        return None
    if not cum or not cum[1]:
        return None
    prem = float(bb["buyback_price"]) / cum[1] - 1
    return prem if -0.5 <= prem <= 1.5 else None   # outside = stale / mis-matched price


if __name__ == "__main__":
    main()
