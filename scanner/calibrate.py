"""Report what realized tender outcomes suggest for the acceptance prior.

    python -m scanner.calibrate

Empty until you log tenders + outcomes (the P2 feedback loop). It reads
outcomes → tenders → buybacks(symbol, record date), looks up each name's market cap AS OF
the record date (scanner.pointintime — no lookahead), pairs it
with the realized acceptance, and prints per-bucket means vs the current hardcoded
prior. It does NOT mutate the constants — once n is large enough, copy the
suggested values into `_MCAP_ACCEPTANCE_PRIOR` in buyback.py.
"""
from __future__ import annotations

from scanner import db
from scanner.buyback import calibrate_from_outcomes, mcap_bucket, _MCAP_ACCEPTANCE_PRIOR

_LABELS = ["small", "small_mid", "mid", "large"]


def main():
    try:
        outcomes = db.select("outcomes", {
            "select": "realized_acceptance,tenders(buybacks(symbol,record_date))",
        })
        # every tender's published response table (scripts/refresh_buyback_results.py) — the
        # market-wide sample; your own outcomes are a subset of the same numbers
        results = db.select_all("buyback_results", {
            "select": "ss_acceptance,buybacks(symbol,record_date)", "ss_acceptance": "not.is.null"})
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
    print(f"\n{'bucket':<12}{'n':>4}{'realized~':>11}{'prior':>9}")
    for b, v in cal.items():
        print(f"{b:<12}{v['n']:>4}{v['acceptance']*100:>10.1f}%{prior.get(b, 0)*100:>8.1f}%")
    print("\nWhen n per bucket is large enough, copy realized~ into "
          "_MCAP_ACCEPTANCE_PRIOR (scanner/buyback.py).")


if __name__ == "__main__":
    main()
