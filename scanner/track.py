"""Feedback-loop CLI: record tender decisions and their realized outcomes.

This is what makes the buyback edge compound — logging the acceptance you actually
got calibrates the selection model over time.

    python -m scanner.track buybacks
    python -m scanner.track tender  --buyback-id 3 --shares 140 --avg-cost 1400 --capital 196000
    python -m scanner.track outcome --tender-id 1 --accepted 130 --acceptance 0.93 \
                                    --residual-price 1360 --return 0.041
    python -m scanner.track tenders
"""
from __future__ import annotations

import argparse
from datetime import date

from scanner import db


def _today() -> str:
    return date.today().isoformat()


def cmd_buybacks(_):
    rows = db.select("buybacks", {"select": "id,symbol,company,buyback_price,record_date,"
                                            "entitlement_small,est_return,status",
                                  "order": "record_date.desc", "limit": "30"})
    if not rows:
        print("No buybacks stored. Run: python -m scanner.run buyback_arb --save")
        return
    print(f"{'ID':>4}  {'SYM':<12}{'BUYBACK':>9}{'RECORD':>12}{'ENTITLE':>9}{'EST':>8}  STATUS")
    for r in rows:
        ent = (r.get("entitlement_small") or 0) * 100
        est = (r.get("est_return") or 0) * 100
        print(f"{r['id']:>4}  {(r.get('symbol') or '?'):<12}{r.get('buyback_price') or 0:>9,.1f}"
              f"{str(r.get('record_date') or '')[:10]:>12}{ent:>8.1f}%{est:>7.1f}%  {r.get('status')}")


def cmd_tender(a):
    t = db.record_tender(a.buyback_id, a.decided_on or _today(), shares_bought=a.shares,
                         avg_cost=a.avg_cost, capital=a.capital,
                         tendered=not a.not_tendered, notes=a.notes)
    print(f"Recorded tender #{t['id']} for buyback {a.buyback_id}.")


def cmd_outcome(a):
    o = db.record_outcome(a.tender_id, accepted_shares=a.accepted,
                          realized_acceptance=a.acceptance,
                          residual_sold_price=a.residual_price, realized_return=a.ret)
    print(f"Recorded outcome #{o['id']} for tender {a.tender_id} "
          f"(realized acceptance {a.acceptance}).")


def cmd_result(a):
    """Hand-entered response table (the post-buyback PDF was a newspaper scan)."""
    from scanner.buyback_results import results_row
    parsed = {"ss_reserved": a.ss_reserved, "ss_tendered": a.ss_tendered, "ss_bids": a.ss_bids,
              "total_reserved": a.total_reserved, "total_tendered": a.total_tendered,
              "ss_response_pct": round(a.ss_tendered / a.ss_reserved * 100, 2) if a.ss_reserved else None}
    row = results_row(a.buyback_id, parsed, url=a.url, parsed_by="manual")
    good, bad = db.upsert_resilient("buyback_results", [row], "buyback_id")
    if bad:
        print(f"rejected: {bad[0][1][-160:]}")
        return
    print(f"Recorded result for buyback {a.buyback_id}: small-shareholder acceptance "
          f"{row['ss_acceptance']:.0%} (reserved {a.ss_reserved:,}, tendered {a.ss_tendered:,}).")


def cmd_results(_):
    rows = db.select("buyback_results", {"select": "buyback_id,ss_acceptance,ss_response_pct,needs_manual,"
                                                   "source_url,buybacks(symbol,record_date)",
                                         "order": "buyback_id.desc", "limit": "40"})
    if not rows:
        print("No results stored. Run: python scripts/refresh_buyback_results.py --all")
        return
    print(f"{'ID':>4}  {'SYM':<12}{'RECORD':>12}{'RESP%':>8}{'ACCEPT':>8}  NOTE")
    for r in rows:
        bb = r.get("buybacks") or {}
        acc = f"{r['ss_acceptance']*100:.0f}%" if r.get("ss_acceptance") is not None else "-"
        resp = f"{r['ss_response_pct']:.1f}" if r.get("ss_response_pct") is not None else "-"
        note = f"MANUAL: {r.get('source_url')}" if r.get("needs_manual") else ""
        print(f"{r['buyback_id']:>4}  {(bb.get('symbol') or '?'):<12}{str(bb.get('record_date') or '')[:10]:>12}"
              f"{resp:>8}{acc:>8}  {note}")


def cmd_tenders(_):
    rows = db.select("tenders", {"select": "id,buyback_id,decided_on,shares_bought,capital,tendered",
                                 "order": "decided_on.desc", "limit": "30"})
    if not rows:
        print("No tenders recorded yet.")
        return
    print(f"{'ID':>4}{'BUYBACK':>9}{'DECIDED':>12}{'SHARES':>8}{'CAPITAL':>10}  TENDERED")
    for r in rows:
        print(f"{r['id']:>4}{r['buyback_id']:>9}{str(r.get('decided_on') or '')[:10]:>12}"
              f"{r.get('shares_bought') or 0:>8}{r.get('capital') or 0:>10,.0f}  {r.get('tendered')}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Track buyback tenders and outcomes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("buybacks", help="list stored buybacks").set_defaults(fn=cmd_buybacks)
    sub.add_parser("tenders", help="list recorded tenders").set_defaults(fn=cmd_tenders)

    t = sub.add_parser("tender", help="record a tender decision")
    t.add_argument("--buyback-id", type=int, required=True)
    t.add_argument("--shares", type=int)
    t.add_argument("--avg-cost", type=float)
    t.add_argument("--capital", type=float)
    t.add_argument("--decided-on", help="YYYY-MM-DD (default today)")
    t.add_argument("--not-tendered", action="store_true", help="bought but did not tender")
    t.add_argument("--notes")
    t.set_defaults(fn=cmd_tender)

    sub.add_parser("results", help="list realized acceptance results").set_defaults(fn=cmd_results)
    rs = sub.add_parser("result", help="hand-enter a post-buyback response table (scanned PDF)")
    rs.add_argument("--buyback-id", type=int, required=True)
    rs.add_argument("--ss-reserved", type=int, required=True, help="shares reserved for small shareholders")
    rs.add_argument("--ss-tendered", type=int, required=True, help="shares validly tendered by them")
    rs.add_argument("--ss-bids", type=int)
    rs.add_argument("--total-reserved", type=int)
    rs.add_argument("--total-tendered", type=int)
    rs.add_argument("--url", help="the announcement PDF")
    rs.set_defaults(fn=cmd_result)

    o = sub.add_parser("outcome", help="record a realized outcome")
    o.add_argument("--tender-id", type=int, required=True)
    o.add_argument("--accepted", type=int, help="shares accepted")
    o.add_argument("--acceptance", type=float, help="accepted/tendered fraction")
    o.add_argument("--residual-price", type=float)
    o.add_argument("--return", dest="ret", type=float, help="realized total return (fraction)")
    o.set_defaults(fn=cmd_outcome)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except Exception as e:
        print(f"[error] {e}")


if __name__ == "__main__":
    main()
